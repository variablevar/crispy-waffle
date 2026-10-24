"""DefiLlama public API: protocol TVL for mapped assets."""

from __future__ import annotations

import logging
from typing import Any

from app.services import FetchResult, cached_fetch_fast
from app.services.http import get_json

log = logging.getLogger(__name__)

BASE = "https://api.llama.fi"
SOURCE = "defillama"


async def protocols() -> FetchResult:
    async def fetch() -> Any:
        return await get_json(f"{BASE}/protocols")

    return await cached_fetch_fast("llama:protocols", ttl=600, fetcher=fetch, source=SOURCE)


async def tvl_for_symbol(symbol: str) -> FetchResult:
    """Aggregate current TVL across protocols whose `symbol` matches.

    Returns {"tvl_usd": float|None, "protocols": [...]} — None when no
    protocol maps to the symbol (never fabricated).
    """

    async def fetch() -> Any:
        data = await protocols()
        if not data.available or not isinstance(data.value, list):
            raise RuntimeError("defillama protocols unavailable")
        sym = symbol.upper()
        matched = [
            {
                "name": p.get("name"),
                "tvl": p.get("tvl"),
                "chain": p.get("chain"),
                "category": p.get("category"),
            }
            for p in data.value
            if (p.get("symbol") or "").upper() == sym and p.get("tvl")
        ]
        total = sum(float(m["tvl"]) for m in matched if m.get("tvl"))
        return {
            "tvl_usd": total if matched else None,
            "protocols": sorted(matched, key=lambda m: -(m["tvl"] or 0))[:10],
        }

    return await cached_fetch_fast(
        f"llama:tvl:{symbol.upper()}", ttl=600, fetcher=fetch, source=SOURCE
    )
