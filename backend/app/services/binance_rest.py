"""Binance public REST: spot + USDT-M perp tickers, klines, depth, aggTrades,
premium index (funding), open interest, long/short ratios, taker volume."""

from __future__ import annotations

import logging
from typing import Any, Literal

from app.services import FetchResult, cached_fetch_fast
from app.services.http import get_json

log = logging.getLogger(__name__)

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"
SOURCE = "binance_rest"

Market = Literal["spot", "perp"]


def _base(market: Market) -> str:
    return SPOT_BASE if market == "spot" else FUTURES_BASE


async def ticker_24h(symbol: str, market: Market = "spot") -> FetchResult:
    base = _base(market)
    path = "/api/v3/ticker/24hr" if market == "spot" else "/fapi/v1/ticker/24hr"

    async def fetch() -> Any:
        return await get_json(f"{base}{path}", params={"symbol": symbol})

    return await cached_fetch_fast(f"bn:ticker:{market}:{symbol}", ttl=15, fetcher=fetch, source=SOURCE)


async def book_ticker(symbol: str, market: Market = "spot") -> FetchResult:
    base = _base(market)
    path = "/api/v3/ticker/bookTicker" if market == "spot" else "/fapi/v1/ticker/bookTicker"

    async def fetch() -> Any:
        return await get_json(f"{base}{path}", params={"symbol": symbol})

    return await cached_fetch_fast(f"bn:book:{market}:{symbol}", ttl=10, fetcher=fetch, source=SOURCE)


async def klines(symbol: str, interval: str, limit: int = 200, market: Market = "spot") -> FetchResult:
    base = _base(market)
    path = "/api/v3/klines" if market == "spot" else "/fapi/v1/klines"

    async def fetch() -> Any:
        return await get_json(
            f"{base}{path}", params={"symbol": symbol, "interval": interval, "limit": limit}
        )

    return await cached_fetch_fast(
        f"bn:klines:{market}:{symbol}:{interval}:{limit}", ttl=30, fetcher=fetch, source=SOURCE
    )


async def depth(symbol: str, limit: int = 100, market: Market = "spot") -> FetchResult:
    base = _base(market)
    path = "/api/v3/depth" if market == "spot" else "/fapi/v1/depth"

    async def fetch() -> Any:
        return await get_json(f"{base}{path}", params={"symbol": symbol, "limit": limit})

    return await cached_fetch_fast(
        f"bn:depth:{market}:{symbol}:{limit}", ttl=10, fetcher=fetch, source=SOURCE
    )


async def agg_trades(symbol: str, limit: int = 1000, market: Market = "spot") -> FetchResult:
    base = _base(market)
    path = "/api/v3/aggTrades" if market == "spot" else "/fapi/v1/aggTrades"

    async def fetch() -> Any:
        return await get_json(f"{base}{path}", params={"symbol": symbol, "limit": limit})

    return await cached_fetch_fast(
        f"bn:aggtrades:{market}:{symbol}:{limit}", ttl=30, fetcher=fetch, source=SOURCE
    )


async def premium_index(symbol: str) -> FetchResult:
    async def fetch() -> Any:
        return await get_json(f"{FUTURES_BASE}/fapi/v1/premiumIndex", params={"symbol": symbol})

    return await cached_fetch_fast(f"bn:premium:{symbol}", ttl=30, fetcher=fetch, source=SOURCE)


async def open_interest(symbol: str) -> FetchResult:
    async def fetch() -> Any:
        return await get_json(f"{FUTURES_BASE}/fapi/v1/openInterest", params={"symbol": symbol})

    return await cached_fetch_fast(f"bn:oi:{symbol}", ttl=30, fetcher=fetch, source=SOURCE)


async def global_long_short_ratio(symbol: str, period: str = "5m") -> FetchResult:
    async def fetch() -> Any:
        return await get_json(
            f"{FUTURES_BASE}/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": period, "limit": 30},
        )

    return await cached_fetch_fast(
        f"bn:lsratio:{symbol}:{period}", ttl=60, fetcher=fetch, source=SOURCE
    )


async def taker_long_short_ratio(symbol: str, period: str = "5m") -> FetchResult:
    async def fetch() -> Any:
        return await get_json(
            f"{FUTURES_BASE}/futures/data/takerlongshortRatio",
            params={"symbol": symbol, "period": period, "limit": 30},
        )

    return await cached_fetch_fast(
        f"bn:takerratio:{symbol}:{period}", ttl=60, fetcher=fetch, source=SOURCE
    )


async def funding_history(symbol: str, limit: int = 30) -> FetchResult:
    async def fetch() -> Any:
        return await get_json(
            f"{FUTURES_BASE}/fapi/v1/fundingRate", params={"symbol": symbol, "limit": limit}
        )

    return await cached_fetch_fast(f"bn:funding:{symbol}", ttl=120, fetcher=fetch, source=SOURCE)


async def force_orders(symbol: str, limit: int = 50) -> FetchResult:
    """Recent public liquidation/force orders.

    Binance made /fapi/v1/allForceOrders authenticated; without credentials it
    returns 401 — in that case we report available=False rather than
    fabricating liquidation data.
    """

    async def fetch() -> Any:
        return await get_json(
            f"{FUTURES_BASE}/fapi/v1/allForceOrders", params={"symbol": symbol, "limit": limit}
        )

    return await cached_fetch_fast(f"bn:force:{symbol}", ttl=60, fetcher=fetch, source=SOURCE)
