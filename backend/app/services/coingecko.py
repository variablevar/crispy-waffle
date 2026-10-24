"""CoinGecko client: global overview, top markets, coin detail, market chart.

Free tier is ~10 req/min without a demo key, so everything is cached
aggressively (>=60s) and the per-host rate limiter throttles calls.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.services import FetchResult, cached_fetch_fast
from app.services.http import get_json

log = logging.getLogger(__name__)

SOURCE = "coingecko"


def _headers() -> dict[str, str]:
    settings = get_settings()
    if settings.coingecko_api_key:
        return {"x-cg-demo-api-key": settings.coingecko_api_key}
    return {}


def _url(path: str) -> str:
    return f"{get_settings().coingecko_base_url.rstrip('/')}/{path.lstrip('/')}"


async def global_overview() -> FetchResult:
    async def fetch() -> Any:
        return await get_json(_url("/global"), headers=_headers(), rate_per_min=10.0)

    return await cached_fetch_fast("cg:global", ttl=60, fetcher=fetch, source=SOURCE)


async def top_markets(limit: int = 100, page: int = 1) -> FetchResult:
    per_page = max(1, min(limit, 250))

    async def fetch() -> Any:
        return await get_json(
            _url("/coins/markets"),
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": "true",
                "price_change_percentage": "1h,24h,7d",
            },
            headers=_headers(),
            rate_per_min=10.0,
        )

    return await cached_fetch_fast(f"cg:markets:{per_page}:{page}", ttl=60, fetcher=fetch, source=SOURCE)


async def coin_detail(coingecko_id: str) -> FetchResult:
    async def fetch() -> Any:
        return await get_json(
            _url(f"/coins/{coingecko_id}"),
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "true",
            },
            headers=_headers(),
            rate_per_min=10.0,
        )

    return await cached_fetch_fast(f"cg:coin:{coingecko_id}", ttl=120, fetcher=fetch, source=SOURCE)


async def market_chart(coingecko_id: str, days: int | float) -> FetchResult:
    async def fetch() -> Any:
        return await get_json(
            _url(f"/coins/{coingecko_id}/market_chart"),
            params={"vs_currency": "usd", "days": days},
            headers=_headers(),
            rate_per_min=10.0,
        )

    return await cached_fetch_fast(
        f"cg:chart:{coingecko_id}:{days}", ttl=300, fetcher=fetch, source=SOURCE
    )


def last_ok(max_age_sec: float = 600) -> bool:
    """Health probe: did coingecko succeed recently?"""
    from app.services import get_source_status

    st = get_source_status(SOURCE)
    if not st.last_success:
        return False
    from datetime import datetime, timezone

    try:
        ts = datetime.fromisoformat(st.last_success.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds() <= max_age_sec
    except Exception:
        return False
