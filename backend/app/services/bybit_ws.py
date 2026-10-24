"""Bybit v5 public websocket worker (spot + linear). Same resilience profile
as the Binance worker: exponential backoff, app-level pings, stale detection."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.core.state import get_live_state

log = logging.getLogger(__name__)

WS_BASE = "wss://stream.bybit.com/v5/public"
MAX_BACKOFF = 60.0
STALE_AFTER_SEC = 90.0


def _topics(symbols: list[str], category: str) -> list[str]:
    topics = []
    for sym in symbols:
        pair = f"{sym}USDT"
        topics.append(f"tickers.{pair}")
        topics.append(f"publicTrade.{pair}")
        topics.append(f"orderbook.50.{pair}")
        if category == "linear":
            topics.append(f"liquidation.{pair}")
    return topics


async def _handle(message: dict[str, Any], category: str) -> None:
    state = get_live_state()
    topic = message.get("topic", "")
    data = message.get("data")
    if not topic or data is None:
        return
    sym = topic.split(".")[-1].replace("USDT", "")
    if topic.startswith("tickers."):
        price = float(data.get("lastPrice") or 0)
        if sym and price:
            instrument = "usdt_perp" if category == "linear" else "spot"
            state.update_price("bybit", sym, price, instrument=instrument)
            state.update_ticker(
                "bybit",
                sym,
                {
                    "price": price,
                    "volume_24h": float(data.get("turnover24h") or 0),
                    "funding_rate": _f(data.get("fundingRate")),
                    "open_interest": _f(data.get("openInterest")),
                    "instrument": instrument,
                },
            )
            state.broadcast(
                {"topic": "price", "data": {"exchange": "bybit", "instrument": instrument, "symbol": sym, "price": price, "ts": time.time()}}
            )
    elif topic.startswith("publicTrade."):
        for t in data if isinstance(data, list) else [data]:
            state.push_trade(
                "bybit",
                sym,
                {
                    "time": t.get("T"),
                    "price": float(t.get("p") or 0),
                    "qty": float(t.get("v") or 0),
                    "is_buyer_maker": t.get("S") == "Sell",
                },
            )
    elif topic.startswith("orderbook."):
        bids = data.get("b") or []
        asks = data.get("a") or []
        if sym and (bids or asks):
            state.push_depth("bybit", sym, bids, asks)
    elif topic.startswith("liquidation."):
        entries = data if isinstance(data, list) else [data]
        for liq in entries:
            price = float(liq.get("p") or 0)
            qty = float(liq.get("v") or 0)
            state.push_trade(
                "bybit_perp_liq",
                sym,
                {
                    "time": liq.get("T"),
                    "side": "long_liquidated" if liq.get("S") == "Sell" else "short_liquidated",
                    "size_usd": price * qty,
                },
            )


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def _ws_loop(category: str, symbols: list[str]) -> None:
    import websockets

    state = get_live_state()
    url = f"{WS_BASE}/{category}"
    topics = _topics(symbols, category)
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(url, ping_interval=None, close_timeout=5) as ws:
                # subscribe in chunks of 10 topics
                for i in range(0, len(topics), 10):
                    await ws.send(json.dumps({"op": "subscribe", "args": topics[i : i + 10]}))
                log.info("bybit ws connected (%s, %d topics)", category, len(topics))
                state.ws_health["bybit"] = True
                backoff = 1.0
                last_msg = time.time()

                async def pinger():
                    while True:
                        await asyncio.sleep(20)
                        try:
                            await ws.send(json.dumps({"op": "ping"}))
                        except Exception:
                            return

                ping_task = asyncio.create_task(pinger())
                try:
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=STALE_AFTER_SEC)
                            last_msg = time.time()
                            message = json.loads(raw)
                            if message.get("op") in ("ping", "pong", "subscribe"):
                                continue
                            await _handle(message, category)
                        except asyncio.TimeoutError:
                            if time.time() - last_msg > STALE_AFTER_SEC:
                                log.warning("bybit ws (%s) stale — reconnecting", category)
                                state.mark_ws_down("bybit")
                                break
                finally:
                    ping_task.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.mark_ws_down("bybit")
            log.info("bybit ws (%s) error: %s; reconnect in %.0fs", category, exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(MAX_BACKOFF, backoff * 2)


async def run(symbols: list[str]) -> None:
    if not symbols:
        return
    await asyncio.gather(_ws_loop("spot", symbols), _ws_loop("linear", symbols))
