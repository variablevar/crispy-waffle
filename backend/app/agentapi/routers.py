"""Agent REST API — /api/v1/agent. Contract: docs/AGENT_CONTRACT.md."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.agentapi.auth import Consumer, require_scope
from app.agentapi.errors import error_response
from app.api import deps
from app.engines import crossproduct
from app.intelligence import assets as intel
from app.services import iso
from app.services.news import get_aggregator

router = APIRouter(tags=["agent"])

_READ = Depends(require_scope("read"))


# ---------------------------------------------------------------------------
# envelope + cursor helpers
# ---------------------------------------------------------------------------


def envelope(
    request: Request,
    data: Any,
    *,
    observed_at: Optional[str] = None,
    stale: bool = False,
    available: bool = True,
    provenance: Optional[list[str]] = None,
    methodology_version: Optional[str] = None,
) -> dict[str, Any]:
    processed = iso()
    freshness = None
    if observed_at:
        try:
            from datetime import datetime, timezone

            obs = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            freshness = round(
                (datetime.now(timezone.utc) - obs).total_seconds(), 2
            )
        except ValueError:
            freshness = None
    return {
        "schema_version": "agent.v1",
        "request_id": getattr(request.state, "request_id", ""),
        "observed_at": observed_at,
        "processed_at": processed,
        "freshness_sec": freshness,
        "stale": stale,
        "available": available,
        "provenance": provenance or [],
        "methodology_version": methodology_version,
        "data": data,
    }


def _encode_cursor(ts: str, item_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([ts, item_id]).encode()).decode()


def _decode_cursor(cursor: str) -> Optional[list[str]]:
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if isinstance(value, list) and len(value) == 2:
            return [str(value[0]), str(value[1])]
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@router.get("/market/overview")
async def agent_market_overview(request: Request, _c: Consumer = _READ) -> dict[str, Any]:
    from app.api.routers.market import market_fear_greed, market_overview

    overview, fng = await asyncio.gather(market_overview(), market_fear_greed())
    fear_greed = None
    if fng.get("available"):
        fear_greed = {
            "value": fng.get("value"),
            "classification": fng.get("classification"),
            "source": fng.get("source"),
            "attribution": fng.get("attribution"),
        }
    data = {
        "total_market_cap": overview.get("total_market_cap"),
        "total_volume_24h": overview.get("total_volume_24h"),
        "btc_dominance": overview.get("btc_dominance"),
        "eth_dominance": overview.get("eth_dominance"),
        "market_cap_change_24h_pct": overview.get("market_cap_change_24h_pct"),
        "fear_greed": fear_greed,
    }
    return envelope(
        request,
        data,
        observed_at=overview.get("updated_at"),
        stale=bool(overview.get("stale")),
        available=bool(overview.get("available")),
        provenance=["coingecko", "alternative.me"],
    )


@router.get("/assets/{asset}/snapshot")
async def agent_snapshot(
    request: Request,
    asset: str,
    venue: Optional[Literal["binance", "bybit"]] = None,
    instrument: Optional[Literal["spot", "usdt_perp"]] = None,
    _c: Consumer = _READ,
) -> dict[str, Any]:
    try:
        detail, tickers, pressure, derivatives = await asyncio.gather(
            intel.get_coin_detail(asset),
            intel.get_tickers(asset),
            intel.get_pressure(asset),
            intel.get_derivatives(asset),
        )
    except Exception as exc:
        if "unknown symbol" in str(exc):
            return _not_found(asset, request)
        raise

    prices = tickers.get("items", [])
    if venue:
        prices = [p for p in prices if p.get("exchange") == venue]
    if instrument:
        prices = [p for p in prices if p.get("instrument") == instrument]

    data = {
        "asset": asset.upper(),
        "prices": [
            {
                "venue": p.get("exchange"),
                "instrument": p.get("instrument"),
                "symbol": p.get("symbol"),
                "price": p.get("price"),
                "bid": p.get("bid"),
                "ask": p.get("ask"),
                "spread_bps": p.get("spread_bps"),
                "volume_24h": p.get("volume_24h"),
                "funding_rate": p.get("funding_rate"),
                "open_interest": p.get("open_interest"),
                "stale": p.get("stale", False),
            }
            for p in prices
        ],
        "trend": detail.get("trend", "neutral"),
        "change_1h": detail.get("change_1h"),
        "change_24h": detail.get("change_24h"),
        "change_7d": detail.get("change_7d"),
        "taker_ratio": pressure.get("taker_ratio"),
        "book_imbalance": pressure.get("book_imbalance"),
        "basis": derivatives.get("basis"),
        "funding": {
            "binance": (derivatives.get("funding") or {}).get("binance"),
            "bybit": (derivatives.get("funding") or {}).get("bybit"),
        },
        "open_interest": {
            "binance": (derivatives.get("open_interest") or {}).get("binance"),
            "bybit": (derivatives.get("open_interest") or {}).get("bybit"),
        },
    }
    updated_candidates = [
        tickers.get("meta", {}).get("updated_at"),
        pressure.get("updated_at"),
        derivatives.get("updated_at"),
    ]
    observed = max((u for u in updated_candidates if u), default=None)
    available = bool(prices) or bool(pressure.get("available"))
    return envelope(
        request,
        data,
        observed_at=observed,
        stale=any(
            [tickers.get("meta", {}).get("stale"), pressure.get("stale"), derivatives.get("stale")]
        ),
        available=available,
        provenance=["binance", "bybit", "coingecko"],
        methodology_version="snapshot.v1",
    )


def _news_page(items: list[dict[str, Any]], limit: int, cursor: Optional[str]) -> dict[str, Any]:
    """Cursor pagination over newest-first items keyed by (published_at, id)."""
    start = 0
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            cursor_key = (decoded[0], decoded[1])
            start = next(
                (
                    i
                    for i, it in enumerate(items)
                    if (str(it.get("published_at") or ""), str(it.get("id") or "")) < cursor_key
                ),
                len(items),
            )
    page = items[start : start + limit]
    next_cursor = None
    if start + limit < len(items) and page:
        last = page[-1]
        next_cursor = _encode_cursor(str(last.get("published_at") or ""), str(last.get("id") or ""))
    return {"items": page, "next_cursor": next_cursor}


async def _agent_news(
    request: Request,
    asset: Optional[str],
    limit: int,
    cursor: Optional[str],
    category: Optional[str],
    kind: Optional[str],
) -> dict[str, Any]:
    agg = get_aggregator()
    # fetch a bounded window wider than the page for cursor slicing
    items, meta = await agg.get_items(
        category=category, asset=asset, kind=kind, limit=min(500, max(limit * 4, 100))
    )
    data = _news_page(items, limit, cursor)
    return envelope(
        request,
        data,
        observed_at=meta.get("updated_at"),
        stale=bool(meta.get("stale")),
        available=bool(meta.get("available")),
        provenance=meta.get("source") or [],
    )


@router.get("/assets/{asset}/news")
async def agent_asset_news(
    request: Request,
    asset: str,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    category: Optional[str] = None,
    kind: Optional[str] = None,
    _c: Consumer = _READ,
) -> dict[str, Any]:
    try:
        deps.symbol_or_404(asset)
    except Exception:
        return _not_found(asset, request)
    return await _agent_news(request, asset.upper(), limit, cursor, category, kind)


@router.get("/news")
async def agent_news(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    category: Optional[str] = None,
    kind: Optional[str] = None,
    _c: Consumer = _READ,
) -> dict[str, Any]:
    return await _agent_news(request, None, limit, cursor, category, kind)


@router.get("/assets/{asset}/pressure")
async def agent_pressure(
    request: Request,
    asset: str,
    timeframe: Optional[str] = None,
    _c: Consumer = _READ,
) -> dict[str, Any]:
    try:
        report = await intel.get_pressure(asset)
    except Exception as exc:
        if "unknown symbol" in str(exc):
            return _not_found(asset, request)
        raise
    return envelope(
        request,
        report,
        observed_at=report.get("updated_at"),
        stale=bool(report.get("stale")),
        available=bool(report.get("available")),
        provenance=["binance"],
        methodology_version="pressure.v1",
    )


@router.get("/assets/{asset}/derivatives")
async def agent_derivatives(request: Request, asset: str, _c: Consumer = _READ) -> dict[str, Any]:
    try:
        report = await intel.get_derivatives(asset)
    except Exception as exc:
        if "unknown symbol" in str(exc):
            return _not_found(asset, request)
        raise
    return envelope(
        request,
        report,
        observed_at=report.get("updated_at"),
        stale=bool(report.get("stale")),
        available=bool(report.get("available")),
        provenance=["binance", "bybit"],
        methodology_version="derivatives.v1",
    )


@router.get("/assets/{asset}/liquidity")
async def agent_liquidity(request: Request, asset: str, _c: Consumer = _READ) -> dict[str, Any]:
    try:
        report = await intel.get_liquidity(asset)
    except Exception as exc:
        if "unknown symbol" in str(exc):
            return _not_found(asset, request)
        raise
    return envelope(
        request,
        report,
        observed_at=report.get("updated_at"),
        stale=bool(report.get("stale")),
        available=bool(report.get("available")),
        provenance=["binance_orderbook", "bybit_orderbook", "estimation_model"],
        methodology_version="liquidity.v1",
    )


@router.get("/assets/{asset}/sentiment")
async def agent_sentiment(request: Request, asset: str, _c: Consumer = _READ) -> dict[str, Any]:
    try:
        report = await intel.get_sentiment(asset)
    except Exception as exc:
        if "unknown symbol" in str(exc):
            return _not_found(asset, request)
        raise
    return envelope(
        request,
        report,
        observed_at=report.get("updated_at"),
        stale=bool(report.get("stale")),
        available=report.get("asset_score") is not None,
        provenance=["news_lexicon", "coingecko", "binance", "alternative.me"],
        methodology_version="sentiment.v1",
    )


@router.get("/assets/{asset}/scenarios")
async def agent_scenarios(request: Request, asset: str, _c: Consumer = _READ) -> dict[str, Any]:
    try:
        report = await intel.get_scenarios_v2(asset)
    except Exception as exc:
        if "unknown symbol" in str(exc):
            return _not_found(asset, request)
        raise
    return envelope(
        request,
        {"scenarios": report.get("scenarios", []), "market_state": report.get("market_state", {})},
        observed_at=report.get("updated_at"),
        stale=bool(report.get("stale")),
        available=bool(report.get("available")),
        provenance=["binance", "bybit"],
        methodology_version="scenarios.v2",
    )


@router.get("/assets/{asset}/cross-exchange")
async def agent_cross_exchange(request: Request, asset: str, _c: Consumer = _READ) -> dict[str, Any]:
    try:
        tickers, pressure = await asyncio.gather(
            intel.get_tickers(asset), intel.get_pressure(asset)
        )
    except Exception as exc:
        if "unknown symbol" in str(exc):
            return _not_found(asset, request)
        raise

    items = tickers.get("items", [])
    mapped = [{**t, "venue": t.get("exchange")} for t in items]
    venue_cmp = crossproduct.compare_venues(mapped)

    perp_ratio = (pressure.get("spot_vs_futures") or {}).get("futures_ratio")
    svp = crossproduct.spot_vs_perp_pressure(pressure, perp_ratio)

    btc_eth = None
    if asset.upper() == "ETH":
        try:
            btc_detail, eth_detail = await asyncio.gather(
                intel.get_coin_detail("BTC"), intel.get_coin_detail("ETH")
            )
            btc_eth = crossproduct.btc_eth_divergence(
                btc_detail.get("change_24h"), eth_detail.get("change_24h")
            )
        except Exception:
            btc_eth = None

    data = {**venue_cmp, "btc_eth": btc_eth, "spot_vs_perp": svp}
    return envelope(
        request,
        data,
        observed_at=tickers.get("meta", {}).get("updated_at"),
        stale=bool(tickers.get("meta", {}).get("stale")),
        available=bool(items),
        provenance=["binance", "bybit"],
        methodology_version="crossproduct.v1",
    )


@router.get("/events")
async def agent_events(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    type: Optional[str] = None,
    asset: Optional[str] = None,
    severity: Optional[str] = None,
    since: Optional[str] = None,
    _c: Consumer = _READ,
) -> dict[str, Any]:
    try:
        from app.events.bus import get_event_bus

        bus = get_event_bus()
        # bus.replay(since_id) is gap-recovery (newer-than). REST cursors page
        # backwards (older-than), so fetch a bounded newest-first window and
        # slice it at the cursor position.
        events = await bus.replay(
            since_id=None,
            limit=min(1000, limit * 4 + 50),
            event_types=[type] if type else None,
            asset=asset.upper() if asset else None,
            severities=[severity] if severity else None,
        )
        if since:
            events = [e for e in events if str(e.get("time") or "") >= since]
        start = 0
        if cursor:
            start = next(
                (i + 1 for i, e in enumerate(events) if e.get("stream_id") == cursor),
                len(events),
            )
        page = events[start : start + limit]
        next_cursor = (
            page[-1].get("stream_id") if start + limit < len(events) and page else None
        )
        data = {"items": page, "next_cursor": next_cursor}
        return envelope(
            request,
            data,
            observed_at=iso(),
            stale=False,
            available=True,
            provenance=[f"event_bus:{bus.backend_name()}"],
            methodology_version="detectors.v1",
        )
    except Exception as exc:
        log_warning = f"event bus unavailable: {exc}"
        return envelope(
            request,
            {"items": [], "next_cursor": None, "note": log_warning},
            observed_at=None,
            available=False,
            provenance=[],
            methodology_version="detectors.v1",
        )


@router.get("/system/health")
async def agent_health(request: Request, _c: Consumer = _READ) -> dict[str, Any]:
    from app.api.routers.system import health

    base = await health()
    try:
        from app.events.bus import get_event_bus

        bus = get_event_bus()
        stream = {"backend": bus.backend_name(), "depth": bus.depth()}
    except Exception:
        stream = {"backend": "unavailable", "depth": 0}
    data = {**base, "event_stream": stream}
    return envelope(
        request,
        data,
        observed_at=iso(),
        available=True,
        provenance=["skybus"],
    )


def _not_found(asset: str, request: Request) -> Any:
    raise HTTPException(status_code=404, detail=f"unknown asset: {asset}")
