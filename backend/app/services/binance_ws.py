"""Binance combined-stream websocket worker (spot miniTicker/aggTrade/depth20
+ futures forceOrder). Reconnects with exponential backoff, pings, and marks
itself stale when no message arrives for a while. Never raises out of run()."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.core.state import get_live_state

log = logging.getLogger(__name__)

SPOT_WS = "wss://stream.binance.com:9443/stream"
FUTURES_WS = "wss://fstream.binance.com/stream"

MAX_BACKOFF = 60.0
STALE_AFTER_SEC = 90.0


def _spot_streams(symbols: list[str]) -> str:
    parts = []
    for sym in symbols:
        s = sym.lower()
        parts += [f"{s}usdt@miniTicker", f"{s}usdt@aggTrade", f"{s}usdt@depth20@100ms"]
    return "/".join(parts)


def _futures_streams(symbols: list[str]) -> str:
    parts = [f"{sym.lower()}usdt@forceOrder" for sym in symbols]
    parts.append("!forceOrder@arr")
    return "/".join(parts)


async def _handle_spot_message(data: dict[str, Any]) -> None:
    state = get_live_state()
    stream = data.get("stream", "")
    payload = data.get("data") or {}
    if "@miniTicker" in stream:
        sym = payload.get("s", "").replace("USDT", "")
        close = float(payload.get("c") or 0)
        if sym and close:
            state.update_price("binance", sym, close, instrument="spot")
            state.update_ticker(
                "binance",
                sym,
                {
                    "price": close,
                    "volume_24h": float(payload.get("q") or 0),
                    "high": float(payload.get("h") or 0),
                    "low": float(payload.get("l") or 0),
                    "instrument": "spot",
                },
            )
            state.broadcast(
                {"topic": "price", "data": {"exchange": "binance", "instrument": "spot", "symbol": sym, "price": close, "ts": time.time()}}
            )
    elif "@aggTrade" in stream:
        sym = payload.get("s", "").replace("USDT", "")
        if sym:
            state.push_trade(
                "binance",
                sym,
                {
                    "time": payload.get("T"),
                    "price": float(payload.get("p") or 0),
                    "qty": float(payload.get("q") or 0),
                    "is_buyer_maker": payload.get("m"),
                },
            )
    elif "@depth20" in stream:
        sym = stream.split("@")[0].replace("usdt", "").upper()
        bids = payload.get("bids") or payload.get("b") or []
        asks = payload.get("asks") or payload.get("a") or []
        if sym and (bids or asks):
            state.push_depth("binance", sym, bids, asks)


async def _handle_futures_message(data: dict[str, Any]) -> None:
    state = get_live_state()
    payload = data.get("data") or {}
    order = payload.get("o") or payload
    sym = (order.get("s") or "").replace("USDT", "")
    if not sym:
        return
    side = order.get("S")  # SELL force order => long liquidated
    price = float(order.get("p") or order.get("ap") or 0)
    qty = float(order.get("q") or 0)
    state.push_trade(
        "binance_perp_liq",
        sym,
        {
            "time": order.get("T") or payload.get("E"),
            "side": "long_liquidated" if side == "SELL" else "short_liquidated",
            "size_usd": price * qty,
        },
    )


async def _ws_loop(url: str, handler, label: str) -> None:
    import websockets

    state = get_live_state()
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=15, close_timeout=5) as ws:
                log.info("binance ws connected (%s)", label)
                state.ws_health["binance"] = True
                state.ws_last_msg["binance"] = time.time()
                backoff = 1.0
                last_msg = time.time()
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=STALE_AFTER_SEC)
                        last_msg = time.time()
                        message = json.loads(raw)
                        await handler(message)
                    except asyncio.TimeoutError:
                        if time.time() - last_msg > STALE_AFTER_SEC:
                            log.warning("binance ws (%s) stale — reconnecting", label)
                            state.mark_ws_down("binance")
                            break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.mark_ws_down("binance")
            log.info("binance ws (%s) error: %s; reconnect in %.0fs", label, exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(MAX_BACKOFF, backoff * 2)


async def run(symbols: list[str]) -> None:
    """Run both stream loops until cancelled."""
    if not symbols:
        return
    spot_url = f"{SPOT_WS}?streams={_spot_streams(symbols)}"
    fut_url = f"{FUTURES_WS}?streams={_futures_streams(symbols)}"
    await asyncio.gather(
        _ws_loop(spot_url, _handle_spot_message, "spot"),
        _ws_loop(fut_url, _handle_futures_message, "futures"),
    )
