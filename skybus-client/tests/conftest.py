"""Shared test helpers. All tests are offline (respx for HTTP, a fake WS)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

BASE_URL = "http://testserver"


def make_envelope(
    data: Any,
    *,
    available: bool = True,
    stale: bool = False,
    observed_at: Optional[str] = None,
    processed_at: Optional[str] = None,
    freshness_sec: Optional[float] = 1.0,
    request_id: str = "01JTESTREQUESTID000000000",
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "agent.v1",
        "request_id": request_id,
        "observed_at": observed_at if observed_at is not None else now,
        "processed_at": processed_at if processed_at is not None else now,
        "freshness_sec": freshness_sec,
        "stale": stale,
        "available": available,
        "provenance": ["test"],
        "methodology_version": None,
        "data": data,
    }


def make_error(code: str, message: str, request_id: str = "01JERR00000000000000000") -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def make_event(
    event_id: str,
    *,
    idempotency_key: Optional[str] = None,
    stream_id: Optional[str] = None,
    type: str = "FUNDING_EXTREME",
    asset: Optional[str] = "BTC",
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "specversion": "1.0",
        "id": event_id,
        "type": type,
        "source": "skybus://detectors/funding",
        "time": now,
        "published_at": now,
        "asset": asset,
        "venue": "binance",
        "instrument": "usdt_perp",
        "severity": "warning",
        "confidence": 0.8,
        "summary": f"event {event_id}",
        "evidence": [{"indicator": "funding", "value": "0.05%", "supports": True}],
        "measurements": {"observed": {"funding": 0.0005}, "estimated": {}},
        "methodology_version": "detectors.v1",
        "idempotency_key": idempotency_key,
        "scenario_id": None,
        "stream_id": stream_id,
    }
