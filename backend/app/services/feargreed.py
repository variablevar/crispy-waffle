"""Alternative.me Fear & Greed index (with attribution per their ToS)."""

from __future__ import annotations

import logging
from typing import Any

from app.services import FetchResult, cached_fetch_fast
from app.services.http import get_json

log = logging.getLogger(__name__)

URL = "https://api.alternative.me/fng/"
SOURCE = "fear_greed"
ATTRIBUTION = "Data provided by alternative.me — https://alternative.me/crypto/fear-and-greed-index/"


async def fear_greed(limit: int = 30) -> FetchResult:
    async def fetch() -> Any:
        return await get_json(URL, params={"limit": limit}, rate_per_min=10.0)

    return await cached_fetch_fast("fng:index", ttl=600, fetcher=fetch, source=SOURCE)
