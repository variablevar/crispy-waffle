"""News routes: aggregated feed, categories, per-source status."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from app.engines.categorizer import CATEGORY_KEYWORDS
from app.services.news import get_aggregator

router = APIRouter(prefix="/news", tags=["news"])


@router.get("")
async def list_news(
    category: Optional[str] = None,
    asset: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    agg = get_aggregator()
    items, meta = await agg.get_items(
        category=category, asset=asset, kind=kind, limit=limit, offset=offset
    )
    return {"items": items, "meta": meta}


@router.get("/categories")
async def news_categories() -> dict[str, Any]:
    return {"categories": sorted(CATEGORY_KEYWORDS.keys())}


@router.get("/sources")
async def news_sources() -> dict[str, Any]:
    return {"sources": get_aggregator().sources_status()}
