"""Agent API authentication, authorization, rate limiting and audit.

Keys are configured via AGENT_API_KEYS ("name:key,...") and are looked up
through constant-time comparison. Keys are never logged or returned.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.cache import get_cache
from app.core.config import get_settings

log = logging.getLogger(__name__)

_AUDIT_LIST = "skybus:audit"
_AUDIT_MAX = 1000


@dataclass
class Consumer:
    name: str
    scopes: list[str] = field(default_factory=lambda: ["read", "stream"])


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def authenticate(api_key: Optional[str]) -> Optional[Consumer]:
    """Validate an API key. Returns a Consumer or None. Never raises."""
    if not api_key:
        return None
    settings = get_settings()
    key_map = settings.agent_key_map
    if not key_map:
        return None
    candidate = _hash(api_key)
    for name, configured in key_map.items():
        if hmac.compare_digest(candidate, _hash(configured)):
            return Consumer(name=name)
    return None


# ---------------------------------------------------------------------------
# rate limiting (token bucket per consumer, in-process)
# ---------------------------------------------------------------------------


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, capacity: float) -> None:
        self.tokens = capacity
        self.updated = time.monotonic()


_buckets: dict[str, _Bucket] = {}


def check_rate_limit(consumer: str, per_min: int) -> tuple[bool, float]:
    """Returns (allowed, retry_after_sec)."""
    rate = per_min / 60.0
    now = time.monotonic()
    bucket = _buckets.get(consumer)
    if bucket is None:
        bucket = _buckets[consumer] = _Bucket(float(per_min))
    bucket.tokens = min(float(per_min), bucket.tokens + (now - bucket.updated) * rate)
    bucket.updated = now
    if bucket.tokens >= 1.0:
        bucket.tokens -= 1.0
        return True, 0.0
    return False, (1.0 - bucket.tokens) / rate


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


async def audit(entry: dict[str, Any]) -> None:
    """Best-effort request audit: Redis list + DB table. Never raises."""
    entry = {**entry, "ts": entry.get("ts") or time.time()}
    try:
        cache = get_cache()
        client = getattr(cache, "_client", None) or getattr(cache, "client", None)
        if client is not None:
            import json

            await client.lpush(_AUDIT_LIST, json.dumps(entry, default=str))
            await client.ltrim(_AUDIT_LIST, 0, _AUDIT_MAX - 1)
    except Exception as exc:
        log.info("audit redis write skipped: %s", exc)
    try:
        from app.core import db as core_db

        if core_db.db_available():
            from app.models import AgentAuditRow

            async with core_db.session() as session:
                if session is None:
                    return
                session.add(
                    AgentAuditRow(
                        consumer=str(entry.get("consumer") or "anonymous"),
                        method=str(entry.get("method") or ""),
                        path=str(entry.get("path") or "")[:500],
                        status=int(entry.get("status") or 0),
                        request_id=str(entry.get("request_id") or ""),
                        latency_ms=float(entry.get("latency_ms") or 0.0),
                    )
                )
                await session.commit()
    except Exception as exc:
        log.info("audit db write skipped: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def require_scope(scope: str):
    """Dependency factory enforcing a valid key + scope + rate limit."""

    async def dependency(request: Request) -> Consumer:
        from app.agentapi.errors import error_response

        request_id = getattr(request.state, "request_id", "")
        api_key = request.headers.get("x-api-key")
        consumer = await authenticate(api_key)
        if consumer is None:
            raise _HTTPErrorResponse(
                error_response(401, "unauthorized", "missing or invalid API key", request_id)
            )
        if scope not in consumer.scopes:
            raise _HTTPErrorResponse(
                error_response(403, "forbidden", f"scope '{scope}' required", request_id)
            )
        settings = get_settings()
        allowed, retry_after = check_rate_limit(consumer.name, settings.agent_rate_limit_per_min)
        if not allowed:
            raise _HTTPErrorResponse(
                error_response(429, "rate_limited", "rate limit exceeded", request_id),
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )
        request.state.consumer = consumer.name
        return consumer

    return dependency


class _HTTPErrorResponse(Exception):
    """Carries a JSONResponse out of a dependency (handled in errors.py)."""

    def __init__(self, response: JSONResponse, headers: dict[str, str] | None = None) -> None:
        self.response = response
        if headers:
            for k, v in headers.items():
                self.response.headers[k] = v
