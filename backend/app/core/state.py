"""Shared in-process live state: latest WS ticks, depth snapshots, health
flags, and a fan-out broadcaster for websocket clients."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Any

log = logging.getLogger(__name__)


class LiveState:
    def __init__(self, depth_history: int = 60) -> None:
        # live:price:{exch}:{SYM} -> {price, ts}
        self.prices: dict[str, dict[str, Any]] = {}
        # live:ticker:{exch}:{SYM} -> latest miniTicker payload
        self.tickers: dict[str, dict[str, Any]] = {}
        # depth snapshot history per exch:symbol -> deque of (ts, bids, asks)
        self.depth_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=depth_history))
        # recent agg trades per exch:symbol -> deque of trade dicts
        self.trades: dict[str, deque] = defaultdict(lambda: deque(maxlen=2000))
        # ws health flags
        self.ws_health: dict[str, bool] = {"binance": False, "bybit": False}
        self.ws_last_msg: dict[str, float] = {"binance": 0.0, "bybit": 0.0}
        # alert event fan-out
        self._subscribers: set[asyncio.Queue] = set()

    # -- prices / tickers -------------------------------------------------
    def update_price(self, exchange: str, symbol: str, price: float, **extra: Any) -> None:
        key = f"{exchange}:{symbol.upper()}"
        self.prices[key] = {"price": price, "ts": time.time(), **extra}
        self.ws_last_msg[exchange] = time.time()
        self.ws_health[exchange] = True

    def get_price(self, exchange: str, symbol: str) -> dict[str, Any] | None:
        return self.prices.get(f"{exchange}:{symbol.upper()}")

    def update_ticker(self, exchange: str, symbol: str, data: dict[str, Any]) -> None:
        self.tickers[f"{exchange}:{symbol.upper()}"] = {"ts": time.time(), **data}

    def get_ticker(self, exchange: str, symbol: str) -> dict[str, Any] | None:
        return self.tickers.get(f"{exchange}:{symbol.upper()}")

    # -- depth / trades ----------------------------------------------------
    def push_depth(self, exchange: str, symbol: str, bids: list, asks: list) -> None:
        self.depth_history[f"{exchange}:{symbol.upper()}"].append((time.time(), bids, asks))
        self.ws_last_msg[exchange] = time.time()
        self.ws_health[exchange] = True

    def latest_depth(self, exchange: str, symbol: str):
        dq = self.depth_history.get(f"{exchange}:{symbol.upper()}")
        return dq[-1] if dq else None

    def push_trade(self, exchange: str, symbol: str, trade: dict[str, Any]) -> None:
        self.trades[f"{exchange}:{symbol.upper()}"].append(trade)

    def recent_trades(self, exchange: str, symbol: str, since: float | None = None) -> list[dict]:
        trades = list(self.trades.get(f"{exchange}:{symbol.upper()}", []))
        if since is None:
            return trades
        return [t for t in trades if t.get("time", 0) >= since]

    # -- ws fan-out ---------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def broadcast(self, message: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                self._subscribers.discard(q)

    def mark_ws_down(self, exchange: str) -> None:
        self.ws_health[exchange] = False


_state = LiveState()


def get_live_state() -> LiveState:
    return _state
