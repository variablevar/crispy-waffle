"""Shared service helpers: cached fetch with stale/available semantics and
per-source status tracking (powers /health and /news/sources)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from app.core.cache import get_cache

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).isoformat().replace("+00:00", "Z")


@dataclass
class FetchResult:
    value: Any
    fetched_at: Optional[datetime]
    stale: bool
    available: bool

    @property
    def updated_at(self) -> str | None:
        return iso(self.fetched_at) if self.fetched_at else None


@dataclass
class SourceStatus:
    name: str
    configured: bool = True
    last_fetch: Optional[str] = None
    last_success: Optional[str] = None
    error: Optional[str] = None
    consecutive_failures: int = 0


_source_status: dict[str, SourceStatus] = {}


def get_source_status(name: str) -> SourceStatus:
    if name not in _source_status:
        _source_status[name] = SourceStatus(name=name)
    return _source_status[name]


def all_source_status() -> dict[str, SourceStatus]:
    return _source_status


def mark_success(source: str) -> None:
    st = get_source_status(source)
    st.last_fetch = iso()
    st.last_success = st.last_fetch
    st.error = None
    st.consecutive_failures = 0


def mark_failure(source: str, error: str) -> None:
    st = get_source_status(source)
    st.last_fetch = iso()
    st.error = error[:300]
    st.consecutive_failures += 1


async def cached_fetch(
    key: str,
    ttl: float,
    fetcher: Callable[[], Awaitable[Any]],
    *,
    source: str | None = None,
) -> FetchResult:
    """Fetch through the TTL cache with contract stale/available semantics.

    - success -> fresh value, stale=False, available=True
    - failure + any cached entry (even expired) -> cached value, stale=True
    - failure + nothing cached -> value=None, available=False (never fabricate)
    """
    cache = get_cache()
    try:
        value = await fetcher()
    except Exception as exc:
        log.info("cached_fetch %s failed: %s", key, exc)
        if source:
            mark_failure(source, str(exc))
        entry = await cache.get_entry(key)
        if entry is not None:
            return FetchResult(
                value=entry.value,
                fetched_at=datetime.fromtimestamp(entry.fetched_at, tz=timezone.utc),
                stale=True,
                available=True,
            )
        return FetchResult(value=None, fetched_at=None, stale=False, available=False)
    if source:
        mark_success(source)
    await cache.set(key, value, ttl)
    return FetchResult(value=value, fetched_at=utc_now(), stale=False, available=True)


async def cached_fetch_fast(
    key: str,
    ttl: float,
    fetcher: Callable[[], Awaitable[Any]],
    *,
    source: str | None = None,
) -> FetchResult:
    """Like cached_fetch but returns a fresh cached value without calling the
    upstream (avoids thundering herd from concurrent pollers + requests)."""
    cache = get_cache()
    fresh = await cache.get_fresh(key)
    if fresh is not None:
        entry = await cache.get_entry(key)
        return FetchResult(
            value=fresh,
            fetched_at=datetime.fromtimestamp(entry.fetched_at, tz=timezone.utc) if entry else utc_now(),
            stale=False,
            available=True,
        )
    return await cached_fetch(key, ttl, fetcher, source=source)
