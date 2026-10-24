"""The eight read-only SkyBus MCP tools.

Each tool is a pure async function returning a JSON-serializable dict.
Errors are returned as ``{"error": {...}}`` — tools never raise across the
MCP boundary and never fabricate data. All intelligence comes from the
SkyBus agent REST API (see docs/AGENT_CONTRACT.md); nothing is
recalculated here.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

from . import client

_ASSET_RE = re.compile(r"^[A-Za-z0-9]{2,15}$")

ESTIMATED_ZONE_NOTE = (
    "Zones whose type starts with 'estimated_' or whose label starts with "
    "'ESTIMATED' are model outputs (estimated liquidation/support/resistance "
    "levels), NOT observed exchange orders. Only 'observed_bid_wall' and "
    "'observed_ask_wall' zones are directly observed."
)


def _bad_request(message: str) -> dict[str, Any]:
    return {"error": {"code": "bad_request", "message": message}}


def _validate_asset(asset: str) -> Optional[str]:
    """Return the normalized asset ticker, or None if invalid."""
    if not isinstance(asset, str):
        return None
    asset = asset.strip().upper()
    return asset if _ASSET_RE.match(asset) else None


def _clamp_limit(limit: int, default: int = 20, lo: int = 1, hi: int = 100) -> int:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, limit))


async def get_market_overview() -> dict[str, Any]:
    """Global crypto market overview from SkyBus.

    Returns total market cap, 24h volume, BTC/ETH dominance, 24h market-cap
    change, and the Fear & Greed index (value, classification, source and
    attribution, passed through verbatim from the upstream provider).
    Envelope metadata (available/stale/observed_at/provenance) is included.
    """
    try:
        return await client.fetch_market_overview()
    except client.SkybusApiError as exc:
        return exc.to_dict()


async def get_asset_snapshot(asset: str) -> dict[str, Any]:
    """Composite snapshot for one asset (base ticker, e.g. 'BTC').

    Returns price per venue/instrument, 1h/24h/7d change, taker buy/sell
    ratio, order-book imbalance, funding, open interest, basis and trend —
    computed by SkyBus, proxied verbatim. Envelope metadata included.
    """
    asset = _validate_asset(asset) if isinstance(asset, str) else None
    if not asset:
        return _bad_request("asset must be a base ticker like 'BTC' or 'ETH'.")
    try:
        return await client.fetch_snapshot(asset)
    except client.SkybusApiError as exc:
        return exc.to_dict()


async def get_latest_news(asset: Optional[str] = None, limit: int = 20) -> dict[str, Any]:
    """Latest categorized, deduplicated news items.

    Each item carries source, kind, category, sentiment and importance as
    classified by SkyBus. Pass an asset ticker to scope the feed; omit it
    for the global feed (requires server support). limit is clamped to
    1..100 (default 20).
    """
    limit = _clamp_limit(limit)
    if asset is not None:
        asset = _validate_asset(asset)
        if not asset:
            return _bad_request("asset must be a base ticker like 'BTC' or 'ETH'.")
    try:
        return await client.fetch_news(asset, limit)
    except client.SkybusApiError as exc:
        return exc.to_dict()


async def get_liquidity_zones(asset: str) -> dict[str, Any]:
    """Liquidity zones for one asset: observed walls vs ESTIMATED zones.

    IMPORTANT: zone labels are preserved verbatim. Zones typed
    'observed_bid_wall'/'observed_ask_wall' are directly observed resting
    orders. Zones typed 'estimated_liquidation'/'estimated_support'/
    'estimated_resistance' (label prefix 'ESTIMATED') are model outputs —
    estimates, not observed orders. Also includes detected liquidity sweeps
    (may be empty).
    """
    asset = _validate_asset(asset) if isinstance(asset, str) else None
    if not asset:
        return _bad_request("asset must be a base ticker like 'BTC' or 'ETH'.")
    try:
        result = await client.fetch_liquidity(asset)
    except client.SkybusApiError as exc:
        return exc.to_dict()
    result["zone_note"] = ESTIMATED_ZONE_NOTE
    return result


async def get_derivatives_context(asset: str) -> dict[str, Any]:
    """Derivatives context for one asset.

    Returns funding rate, open interest (plus 1h OI/funding change), basis,
    perp premium and long/short ratios as computed by SkyBus. Liquidation
    data availability is reported by the API — when unavailable the response
    says so explicitly (available=false / null fields); it is never
    fabricated.
    """
    asset = _validate_asset(asset) if isinstance(asset, str) else None
    if not asset:
        return _bad_request("asset must be a base ticker like 'BTC' or 'ETH'.")
    try:
        return await client.fetch_derivatives(asset)
    except client.SkybusApiError as exc:
        return exc.to_dict()


async def get_market_scenarios(asset: str) -> dict[str, Any]:
    """ScenarioV2 list for one asset from the SkyBus scenario engine.

    Each scenario carries type, bias, market regime, status,
    trigger_conditions, confirmation_signals, invalidation_conditions,
    evidence, target_zones, risks, confidence and confidence_note. NOTE:
    confidence is a rule-vote fraction, NOT a calibrated probability (the
    API's confidence_note is passed through verbatim).
    """
    asset = _validate_asset(asset) if isinstance(asset, str) else None
    if not asset:
        return _bad_request("asset must be a base ticker like 'BTC' or 'ETH'.")
    try:
        return await client.fetch_scenarios(asset)
    except client.SkybusApiError as exc:
        return exc.to_dict()


async def compare_exchange_signals(asset: str) -> dict[str, Any]:
    """Cross-exchange comparison for one asset (e.g. Binance vs Bybit).

    Returns per-pair venue spreads (bps), funding gaps, OI gaps and whether
    venues agree on direction, plus BTC/ETH correlation and spot-vs-perp
    context when available. All values computed by SkyBus.
    """
    asset = _validate_asset(asset) if isinstance(asset, str) else None
    if not asset:
        return _bad_request("asset must be a base ticker like 'BTC' or 'ETH'.")
    try:
        return await client.fetch_cross_exchange(asset)
    except client.SkybusApiError as exc:
        return exc.to_dict()


# ---------------------------------------------------------------------------
# explain_market_event — deterministic composer
# ---------------------------------------------------------------------------


def _flatten_scalars(value: Any, prefix: str = "", depth: int = 0, out: Optional[list] = None) -> list[str]:
    """Flatten nested dicts into 'a.b=value' lines (bounded, deterministic)."""
    if out is None:
        out = []
    if len(out) >= 60 or depth > 2:
        return out
    if isinstance(value, dict):
        for key in sorted(value):
            sub = f"{prefix}{key}"
            item = value[key]
            if isinstance(item, dict):
                _flatten_scalars(item, sub + ".", depth + 1, out)
            elif isinstance(item, (str, int, float, bool)) or item is None:
                out.append(f"{sub}={item}")
    return out


def _zone_lines(zones: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(zones, list):
        return lines
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        label = str(zone.get("label", ""))
        ztype = str(zone.get("type", ""))
        estimated = ztype.startswith("estimated_") or label.upper().startswith("ESTIMATED")
        tag = (
            "[ESTIMATED — model output, not observed orders]"
            if estimated
            else "[observed]"
        )
        price_bits = []
        for key in ("price", "price_low", "price_high", "strength"):
            if zone.get(key) is not None:
                price_bits.append(f"{key}={zone[key]}")
        lines.append(f"- {tag} {label} (type={ztype}) " + " ".join(price_bits))
    return lines


def _news_items(data: Any) -> list:
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return items
    if isinstance(data, list):
        return data
    return []


def _render_explanation(
    asset: str,
    question: str,
    sections: dict[str, dict[str, Any]],
    unavailable: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append(f"SkyBus market explanation for {asset}")
    lines.append(f"Question: {question}")
    lines.append(
        "Method: deterministic composition of SkyBus agent API outputs "
        "(snapshot + liquidity + scenarios + recent news). No LLM inference, "
        "no recomputation, no fabrication."
    )
    lines.append("")

    snap = sections.get("snapshot")
    if snap:
        lines.append(f"== Snapshot (observed_at={snap.get('observed_at')}, stale={snap.get('stale')}, provenance={snap.get('provenance')}) ==")
        for line in _flatten_scalars(snap.get("data")):
            lines.append(f"- {line}")
        lines.append("")

    liq = sections.get("liquidity")
    if liq:
        lines.append(f"== Liquidity zones (observed_at={liq.get('observed_at')}, stale={liq.get('stale')}) ==")
        lines.append(ESTIMATED_ZONE_NOTE)
        data = liq.get("data") or {}
        zones = data.get("zones") if isinstance(data, dict) else None
        zone_lines = _zone_lines(zones)
        lines.extend(zone_lines or ["- (no zones reported)"])
        sweeps = data.get("sweeps") if isinstance(data, dict) else None
        if sweeps:
            lines.append("Detected sweeps:")
            for sweep in sweeps:
                if isinstance(sweep, dict):
                    lines.append(
                        f"- {sweep.get('time')} {sweep.get('direction')} @ {sweep.get('price')} ({sweep.get('source')})"
                    )
        lines.append("")

    sc = sections.get("scenarios")
    if sc:
        lines.append("== Scenarios (ScenarioV2; confidence is a rule-vote fraction, not a calibrated probability) ==")
        data = sc.get("data") or {}
        scenarios = data.get("scenarios") if isinstance(data, dict) else None
        if isinstance(scenarios, list) and scenarios:
            for s in scenarios:
                if not isinstance(s, dict):
                    continue
                lines.append(
                    f"- {s.get('title')} [type={s.get('type')}, bias={s.get('bias')}, "
                    f"regime={s.get('market_regime')}, status={s.get('status')}, "
                    f"confidence={s.get('confidence')}]"
                )
                if s.get("confidence_note"):
                    lines.append(f"  confidence_note: {s['confidence_note']}")
                for field, name in (
                    ("trigger_conditions", "triggers"),
                    ("confirmation_signals", "confirmations"),
                    ("invalidation_conditions", "invalidations"),
                ):
                    vals = s.get(field) or []
                    if vals:
                        lines.append(f"  {name}: " + "; ".join(str(v) for v in vals))
        else:
            lines.append("- (no active scenarios reported)")
        lines.append("")

    news = sections.get("news")
    if news:
        lines.append(f"== Recent news (observed_at={news.get('observed_at')}, stale={news.get('stale')}) ==")
        items = _news_items(news.get("data"))
        if items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"- {item.get('title')} [source={item.get('source')}, kind={item.get('kind')}, "
                    f"sentiment={item.get('sentiment')}, importance={item.get('importance')}]"
                )
        else:
            lines.append("- (no recent news items)")
        lines.append("")

    if unavailable:
        lines.append("== Data unavailable (not fabricated) ==")
        for name in sorted(unavailable):
            err = unavailable[name]
            lines.append(f"- {name}: {err.get('code')} — {err.get('message')}")
        lines.append("")

    lines.append(
        "Interpretation guidance: only 'observed' liquidity zones reflect real "
        "resting orders; 'ESTIMATED' zones and scenario confidence are model "
        "outputs. Stale=true or available=false sections should not be traded on."
    )
    return "\n".join(lines)


async def explain_market_event(asset: str, question: str) -> dict[str, Any]:
    """Deterministic explanation of current market conditions for an asset.

    Gathers snapshot + liquidity + scenarios + recent news from the SkyBus
    agent API and composes a structured textual explanation. No LLM calls,
    no recomputation, no fabrication: every claim traces to an API response,
    ESTIMATED liquidity zones are explicitly marked as model outputs, and
    any endpoint that fails is listed under 'unavailable' instead of being
    guessed. The 'question' is echoed and used to frame the answer; it does
    not trigger any generative inference.
    """
    asset = _validate_asset(asset) if isinstance(asset, str) else None
    if not asset:
        return _bad_request("asset must be a base ticker like 'BTC' or 'ETH'.")
    if not isinstance(question, str) or not question.strip():
        return _bad_request("question must be a non-empty string.")
    question = question.strip()

    if not client.get_api_key():
        return client.MissingApiKeyError().to_dict()

    names = ("snapshot", "liquidity", "scenarios", "news")
    results = await asyncio.gather(
        client.fetch_snapshot(asset),
        client.fetch_liquidity(asset),
        client.fetch_scenarios(asset),
        client.fetch_news(asset, 5),
        return_exceptions=True,
    )
    sections: dict[str, dict[str, Any]] = {}
    unavailable: dict[str, dict[str, Any]] = {}
    for name, res in zip(names, results):
        if isinstance(res, client.SkybusApiError):
            unavailable[name] = res.to_dict()["error"]
        elif isinstance(res, Exception):
            unavailable[name] = {"code": "internal", "message": str(res)}
        else:
            sections[name] = res

    explanation = _render_explanation(asset, question, sections, unavailable)
    return {
        "asset": asset,
        "question": question,
        "generated_from": [n for n in names if n in sections],
        "sections": sections,
        "unavailable": unavailable,
        "explanation": explanation,
        "note": (
            "Deterministic composition of SkyBus agent API outputs. "
            "ESTIMATED liquidity zones are model outputs, not observed "
            "orders. Scenario confidence is a rule-vote fraction, not a "
            "calibrated probability."
        ),
    }
