"""Coin routes: detail, chart, tickers, pressure, derivatives, liquidity,
scenarios, sentiment, defi, news.

Thin wrappers over app.intelligence.assets — the shared calculation path used
by both this dashboard API and the agent API. Response shapes are unchanged.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query

from app.api import deps
from app.intelligence import assets as intel

router = APIRouter(prefix="/coins", tags=["coins"])


@router.get("/{symbol}")
async def coin_detail(symbol: str) -> dict[str, Any]:
    return await intel.get_coin_detail(symbol)


@router.get("/{symbol}/chart")
async def coin_chart(
    symbol: str,
    timeframe: Literal["15m", "1h", "4h", "1d", "1w"] = "1h",
    source: Literal["auto", "binance", "coingecko"] = "auto",
) -> dict[str, Any]:
    return await intel.get_chart(symbol, timeframe, source)


@router.get("/{symbol}/tickers")
async def coin_tickers(symbol: str) -> dict[str, Any]:
    return await intel.get_tickers(symbol)


@router.get("/{symbol}/pressure")
async def coin_pressure(symbol: str) -> dict[str, Any]:
    return await intel.get_pressure(symbol)


@router.get("/{symbol}/derivatives")
async def coin_derivatives(symbol: str) -> dict[str, Any]:
    return await intel.get_derivatives(symbol)


@router.get("/{symbol}/liquidity")
async def coin_liquidity(symbol: str) -> dict[str, Any]:
    return await intel.get_liquidity(symbol)


@router.get("/{symbol}/scenarios")
async def coin_scenarios(symbol: str) -> dict[str, Any]:
    return await intel.get_scenarios(symbol)


@router.get("/{symbol}/sentiment")
async def coin_sentiment(symbol: str) -> dict[str, Any]:
    return await intel.get_sentiment(symbol)


@router.get("/{symbol}/defi")
async def coin_defi(symbol: str) -> dict[str, Any]:
    return await intel.get_defi(symbol)


@router.get("/{symbol}/news")
async def coin_news(symbol: str, limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    deps.symbol_or_404(symbol)
    return await intel.get_news(symbol, limit=limit)
