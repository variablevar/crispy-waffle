"""OPTIONAL CoinGlass premium integration.

Without COINGLASS_API_KEY this module reports available=False and engines
fall back to the labelled estimation model — no fabricated numbers.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.services import FetchResult, cached_fetch_fast
from app.services.http import get_json

log = logging.getLogger(__name__)

BASE = "https://open-api.coinglass.com/public/v2"
SOURCE = "coinglass"


def available() -> bool:
    return bool(get_settings().coinglass_api_key)


def _headers() -> dict[str, str]:
    return {"coinglassSecret": get_settings().coinglass_api_key}


async def liquidation_history(symbol: str) -> FetchResult:
    if not available():
        from app.services import FetchResult as FR

        return FR(value=None, fetched_at=None, stale=False, available=False)

    async def fetch() -> Any:
        return await get_json(
            f"{BASE}/liquidation_history", params={"symbol": symbol.upper()}, headers=_headers()
        )

    return await cached_fetch_fast(
        f"cgls:liq:{symbol.upper()}", ttl=120, fetcher=fetch, source=SOURCE
    )
