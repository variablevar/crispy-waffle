"""Bybit v5 public REST: spot + linear tickers, kline, orderbook, funding
history, open interest, long-short ratio, recent trades."""

from __future__ import annotations

import logging
from typing import Any, Literal

from app.services import FetchResult, cached_fetch_fast
from app.services.http import get_json

log = logging.getLogger(__name__)

BASE = "https://api.bybit.com"
SOURCE = "bybit_rest"

Category = Literal["spot", "linear"]


async def tickers(symbol: str, category: Category = "spot") -> FetchResult:
    async def fetch() -> Any:
        data = await get_json(
            f"{BASE}/v5/market/tickers", params={"category": category, "symbol": symbol}
        )
        if data.get("retCode") != 0:
            raise RuntimeError(f"bybit retCode={data.get('retCode')}: {data.get('retMsg')}")
        return data["result"]["list"]

    return await cached_fetch_fast(
        f"bb:tickers:{category}:{symbol}", ttl=15, fetcher=fetch, source=SOURCE
    )


async def kline(symbol: str, interval: str, limit: int = 200, category: Category = "spot") -> FetchResult:
    async def fetch() -> Any:
        data = await get_json(
            f"{BASE}/v5/market/kline",
            params={
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )
        if data.get("retCode") != 0:
            raise RuntimeError(f"bybit retCode={data.get('retCode')}: {data.get('retMsg')}")
        return data["result"]["list"]

    return await cached_fetch_fast(
        f"bb:kline:{category}:{symbol}:{interval}:{limit}", ttl=30, fetcher=fetch, source=SOURCE
    )


async def orderbook(symbol: str, limit: int = 50, category: Category = "spot") -> FetchResult:
    async def fetch() -> Any:
        data = await get_json(
            f"{BASE}/v5/market/orderbook",
            params={"category": category, "symbol": symbol, "limit": limit},
        )
        if data.get("retCode") != 0:
            raise RuntimeError(f"bybit retCode={data.get('retCode')}: {data.get('retMsg')}")
        return data["result"]

    return await cached_fetch_fast(
        f"bb:orderbook:{category}:{symbol}:{limit}", ttl=10, fetcher=fetch, source=SOURCE
    )


async def funding_history(symbol: str, limit: int = 30) -> FetchResult:
    async def fetch() -> Any:
        data = await get_json(
            f"{BASE}/v5/market/funding/history",
            params={"category": "linear", "symbol": symbol, "limit": limit},
        )
        if data.get("retCode") != 0:
            raise RuntimeError(f"bybit retCode={data.get('retCode')}: {data.get('retMsg')}")
        return data["result"]["list"]

    return await cached_fetch_fast(f"bb:funding:{symbol}", ttl=120, fetcher=fetch, source=SOURCE)


async def open_interest(symbol: str, interval: str = "5min", limit: int = 30) -> FetchResult:
    async def fetch() -> Any:
        data = await get_json(
            f"{BASE}/v5/market/open-interest",
            params={
                "category": "linear",
                "symbol": symbol,
                "intervalTime": interval,
                "limit": limit,
            },
        )
        if data.get("retCode") != 0:
            raise RuntimeError(f"bybit retCode={data.get('retCode')}: {data.get('retMsg')}")
        return data["result"]["list"]

    return await cached_fetch_fast(
        f"bb:oi:{symbol}:{interval}", ttl=60, fetcher=fetch, source=SOURCE
    )


async def long_short_ratio(symbol: str, period: str = "5min", limit: int = 30) -> FetchResult:
    async def fetch() -> Any:
        data = await get_json(
            f"{BASE}/v5/market/long-short-ratio",
            params={"category": "linear", "symbol": symbol, "period": period, "limit": limit},
        )
        if data.get("retCode") != 0:
            raise RuntimeError(f"bybit retCode={data.get('retCode')}: {data.get('retMsg')}")
        return data["result"]["list"]

    return await cached_fetch_fast(
        f"bb:lsratio:{symbol}:{period}", ttl=60, fetcher=fetch, source=SOURCE
    )


async def recent_trades(symbol: str, limit: int = 500, category: Category = "spot") -> FetchResult:
    async def fetch() -> Any:
        data = await get_json(
            f"{BASE}/v5/market/recent-trade",
            params={"category": category, "symbol": symbol, "limit": limit},
        )
        if data.get("retCode") != 0:
            raise RuntimeError(f"bybit retCode={data.get('retCode')}: {data.get('retMsg')}")
        return data["result"]["list"]

    return await cached_fetch_fast(
        f"bb:trades:{category}:{symbol}:{limit}", ttl=30, fetcher=fetch, source=SOURCE
    )
