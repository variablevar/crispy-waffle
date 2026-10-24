"""DEX Screener public API: pair search per chain, liquidity pools."""

from __future__ import annotations

import logging
from typing import Any

from app.services import FetchResult, cached_fetch_fast
from app.services.http import get_json

log = logging.getLogger(__name__)

BASE = "https://api.dexscreener.com"
SOURCE = "dexscreener"


async def search_pairs(query: str) -> FetchResult:
    async def fetch() -> Any:
        return await get_json(f"{BASE}/latest/dex/search", params={"q": query})

    return await cached_fetch_fast(f"dex:search:{query.lower()}", ttl=120, fetcher=fetch, source=SOURCE)


async def token_profiles() -> FetchResult:
    async def fetch() -> Any:
        return await get_json(f"{BASE}/token-profiles/latest/v1")

    return await cached_fetch_fast("dex:profiles", ttl=300, fetcher=fetch, source=SOURCE)


async def token_pairs(chain: str, token_address: str) -> FetchResult:
    async def fetch() -> Any:
        return await get_json(f"{BASE}/token-pairs/v1/{chain}/{token_address}")

    return await cached_fetch_fast(
        f"dex:pairs:{chain}:{token_address}", ttl=120, fetcher=fetch, source=SOURCE
    )
