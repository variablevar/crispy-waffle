"""Market routes: overview, top, top-volume, movers, fear-greed."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Query

from app.api import deps
from app.core.symbols import STABLES
from app.services import coingecko, feargreed, iso

router = APIRouter(prefix="/market", tags=["market"])


def _dominance_map(global_data: dict | None) -> dict[str, float]:
    pct = ((global_data or {}).get("data") or {}).get("market_cap_percentage") or {}
    return {k.upper(): v for k, v in pct.items() if isinstance(v, (int, float))}


def _total_mcap(global_data: dict | None) -> Optional[float]:
    try:
        return float(((global_data or {}).get("data") or {}).get("total_market_cap", {}).get("usd"))
    except (TypeError, ValueError):
        return None


@router.get("/overview")
async def market_overview() -> dict[str, Any]:
    res = await coingecko.global_overview()
    if not res.available or not isinstance(res.value, dict):
        return {
            "total_market_cap": None,
            "total_volume_24h": None,
            "btc_dominance": None,
            "eth_dominance": None,
            "market_cap_change_24h_pct": None,
            "active_cryptocurrencies": None,
            "available": False,
            "updated_at": None,
            "stale": False,
        }
    data = res.value.get("data") or {}
    return {
        "total_market_cap": (data.get("total_market_cap") or {}).get("usd"),
        "total_volume_24h": (data.get("total_volume") or {}).get("usd"),
        "btc_dominance": (data.get("market_cap_percentage") or {}).get("btc"),
        "eth_dominance": (data.get("market_cap_percentage") or {}).get("eth"),
        "market_cap_change_24h_pct": data.get("market_cap_change_percentage_24h_usd"),
        "active_cryptocurrencies": data.get("active_cryptocurrencies"),
        "available": True,
        "updated_at": res.updated_at,
        "stale": res.stale,
    }


async def _markets_payload(
    coins: list[dict[str, Any]], global_res, markets_res, limit: int
) -> dict[str, Any]:
    dominance = _dominance_map(global_res.value if global_res else None)
    total_mcap = _total_mcap(global_res.value if global_res else None)
    items = [
        deps.coin_summary_from_market(
            c,
            total_mcap=total_mcap,
            dominance_map=dominance,
            updated_at=markets_res.updated_at,
            stale=markets_res.stale,
        )
        for c in coins[:limit]
    ]
    return deps.list_wrapper(
        items, ["coingecko"], markets_res.updated_at, markets_res.stale, markets_res.available
    )


@router.get("/top")
async def market_top(limit: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
    markets_res, global_res = await _markets_and_global(limit)
    if not markets_res.available or not isinstance(markets_res.value, list):
        return deps.list_wrapper([], ["coingecko"], None, False, available=False)
    return await _markets_payload(markets_res.value, global_res, markets_res, limit)


async def _markets_and_global(limit: int):
    markets_res, global_res = await asyncio.gather(
        coingecko.top_markets(limit=max(limit, 100)), coingecko.global_overview()
    )
    return markets_res, global_res


@router.get("/top-volume")
async def market_top_volume(limit: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
    markets_res, global_res = await _markets_and_global(250)
    if not markets_res.available or not isinstance(markets_res.value, list):
        return deps.list_wrapper([], ["coingecko"], None, False, available=False)
    coins = [
        c
        for c in markets_res.value
        if (c.get("symbol") or "").upper() not in STABLES and c.get("total_volume")
    ]
    coins.sort(key=lambda c: c.get("total_volume") or 0, reverse=True)
    return await _markets_payload(coins, global_res, markets_res, limit)


@router.get("/movers")
async def market_movers(
    type: Literal["gainers", "losers", "volume"] = "gainers",
    limit: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    if type == "volume":
        return await market_top_volume(limit=limit)
    markets_res, global_res = await _markets_and_global(250)
    if not markets_res.available or not isinstance(markets_res.value, list):
        return deps.list_wrapper([], ["coingecko"], None, False, available=False)
    coins = [
        c for c in markets_res.value if c.get("price_change_percentage_24h_in_currency") is not None
    ]
    coins.sort(
        key=lambda c: c["price_change_percentage_24h_in_currency"], reverse=(type == "gainers")
    )
    return await _markets_payload(coins, global_res, markets_res, limit)


@router.get("/fear-greed")
async def market_fear_greed() -> dict[str, Any]:
    res = await feargreed.fear_greed(limit=30)
    if not res.available or not isinstance(res.value, dict) or not res.value.get("data"):
        return {
            "value": None,
            "classification": "unavailable",
            "source": "alternative.me",
            "attribution": feargreed.ATTRIBUTION,
            "history": [],
            "available": False,
            "updated_at": None,
            "stale": False,
        }
    entries = res.value.get("data") or []
    current = entries[0]
    history = [
        {
            "value": float(e["value"]),
            "timestamp": iso(datetime.fromtimestamp(int(e["timestamp"]), tz=timezone.utc)),
        }
        for e in reversed(entries)
        if e.get("value") is not None and e.get("timestamp")
    ]
    return {
        "value": float(current["value"]),
        "classification": current.get("value_classification", "unknown"),
        "source": "alternative.me",
        "attribution": feargreed.ATTRIBUTION,
        "history": history,
        "available": True,
        "updated_at": res.updated_at,
        "stale": res.stale,
    }
