"""Shared API helpers: symbol resolution, list-wrapper meta, CoinSummary
builder mapping CoinGecko payloads to the contract shape."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.core import symbols as symbol_registry
from app.core.symbols import SymbolInfo
from app.services import iso
from app.services.news import get_aggregator


def symbol_or_404(symbol: str) -> SymbolInfo:
    info = symbol_registry.resolve(symbol)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}")
    return info


def list_meta(
    sources: list[str], updated_at: str | None, stale: bool, available: bool
) -> dict[str, Any]:
    return {
        "source": sources,
        "updated_at": updated_at,
        "stale": stale,
        "available": available,
    }


def list_wrapper(items: list[dict], sources: list[str], updated_at: str | None, stale: bool, available: bool = True) -> dict:
    return {"items": items, "meta": list_meta(sources, updated_at, stale, available)}


def trend_from_change(change_24h: Optional[float]) -> str:
    if change_24h is None:
        return "neutral"
    if change_24h > 1.0:
        return "bullish"
    if change_24h < -1.0:
        return "bearish"
    return "neutral"


def quick_sentiment(change_1h: float | None, change_24h: float | None, change_7d: float | None, news_component: float | None) -> dict | None:
    """Cheap proprietary sentiment for list payloads; None when no inputs."""
    from app.engines import sentiment as sentiment_engine

    components = {
        "news": news_component,
        "momentum": sentiment_engine.momentum_component(change_1h, change_24h, change_7d),
        "volume": None,
        "funding": None,
    }
    score = sentiment_engine.combine(components)
    if score is None:
        return None
    return {"score": score, "label": sentiment_engine.label_for(score)}


def coin_summary_from_market(
    coin: dict[str, Any],
    *,
    total_mcap: float | None = None,
    dominance_map: dict[str, float] | None = None,
    updated_at: str | None = None,
    stale: bool = False,
    with_sentiment: bool = True,
) -> dict[str, Any]:
    agg = get_aggregator()
    sym = (coin.get("symbol") or "").upper()
    change_1h = coin.get("price_change_percentage_1h_in_currency")
    change_24h = coin.get("price_change_percentage_24h_in_currency")
    if change_24h is None:
        change_24h = coin.get("price_change_percentage_24h")
    change_7d = coin.get("price_change_percentage_7d_in_currency")
    market_cap = coin.get("market_cap")

    dominance = None
    if dominance_map and sym in dominance_map:
        dominance = dominance_map[sym]
    elif market_cap and total_mcap:
        dominance = round(market_cap / total_mcap * 100, 3)

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    news_items = [i for i in agg._items if sym in i["assets"] and i["published_at"] >= since]
    news_count = len(news_items)
    news_component = None
    if news_items:
        vals = [i["sentiment"] for i in news_items if i.get("sentiment") is not None]
        if vals:
            news_component = round(sum(vals) / len(vals), 3)

    sparkline = ((coin.get("sparkline_in_7d") or {}).get("price")) or []

    return {
        "id": coin.get("id") or "",
        "symbol": sym,
        "name": coin.get("name") or sym,
        "image": coin.get("image"),
        "price": coin.get("current_price"),
        "change_1h": change_1h,
        "change_24h": change_24h,
        "change_7d": change_7d,
        "market_cap": market_cap,
        "volume_24h": coin.get("total_volume"),
        "circulating_supply": coin.get("circulating_supply"),
        "dominance": dominance,
        "sparkline": [p for p in sparkline if p is not None],
        "trend": trend_from_change(change_24h),
        "sentiment": (
            quick_sentiment(change_1h, change_24h, change_7d, news_component)
            if with_sentiment
            else None
        ),
        "news_count_24h": news_count,
        "updated_at": updated_at or iso(),
        "stale": stale,
    }
