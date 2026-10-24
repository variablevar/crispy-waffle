"""AgentEvent builder — CloudEvents-inspired envelope per AGENT_CONTRACT.md.

Detectors only ever fire on observed inputs; `measurements.observed` holds
directly observed exchange data while `measurements.estimated` holds model
outputs, always separately labelled.
"""

from __future__ import annotations

from typing import Any, Optional

import ulid

from app.services import iso

EVENT_TYPES = frozenset(
    {
        "PRICE_LEVEL_CROSSED",
        "LIQUIDITY_ZONE_APPROACH",
        "LIQUIDITY_ZONE_BREACHED",
        "LIQUIDITY_SWEEP_DETECTED",
        "CVD_DIVERGENCE",
        "OPEN_INTEREST_SPIKE",
        "FUNDING_EXTREME",
        "LONG_LIQUIDATION_BURST",
        "SHORT_LIQUIDATION_BURST",
        "CROSS_EXCHANGE_DIVERGENCE",
        "NEWS_BREAKING",
        "MARKET_REGIME_CHANGED",
        "SCENARIO_CREATED",
        "SCENARIO_INVALIDATED",
        "DATA_STALE",
        "DATA_RECOVERED",
    }
)

SEVERITIES = frozenset({"info", "warning", "critical"})

METHODOLOGY_VERSION = "detectors.v1"


def make_event(
    *,
    type: str,
    source: str,
    summary: str,
    idempotency_key: str,
    asset: Optional[str] = None,
    venue: Optional[str] = None,
    instrument: Optional[str] = None,
    severity: str = "info",
    confidence: Optional[float] = None,
    evidence: Optional[list[dict[str, Any]]] = None,
    observed: Optional[dict[str, Any]] = None,
    estimated: Optional[dict[str, Any]] = None,
    scenario_id: Optional[str] = None,
    event_time: Optional[float] = None,
) -> dict[str, Any]:
    """Build a contract AgentEvent dict.

    `stream_id` is left None here and set by the event bus when the event is
    persisted. `event_time` (unix seconds) defaults to now.
    """
    if type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {type!r}")
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity: {severity!r}")
    time_iso = iso()
    if event_time is not None:
        from datetime import datetime, timezone

        time_iso = iso(datetime.fromtimestamp(event_time, tz=timezone.utc))
    return {
        "specversion": "1.0",
        "id": str(ulid.new()),
        "type": type,
        "source": source,
        "time": time_iso,
        "published_at": iso(),
        "asset": asset.upper() if asset else None,
        "venue": venue,
        "instrument": instrument,
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "evidence": evidence or [],
        "measurements": {"observed": observed or {}, "estimated": estimated or {}},
        "methodology_version": METHODOLOGY_VERSION,
        "idempotency_key": idempotency_key,
        "scenario_id": scenario_id,
        "stream_id": None,
    }
