"""Durable event bus: Redis Stream primary, in-process ring buffer fallback.

Events are XADD-ed to `settings.event_stream_name` with approximate MAXLEN
trimming (`settings.event_stream_maxlen`). When Redis is unreachable the bus
degrades to a `collections.deque` ring (`settings.event_ring_fallback`) and
`backend_name()` reports "memory" — replay then covers only process lifetime.
publish() never raises on redis failure.

A small subscribe()/unsubscribe() fan-out (asyncio.Queue, like LiveState's)
lets WebSocket clients receive freshly published events live.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Optional

from app.core.config import get_settings

log = logging.getLogger(__name__)

_FETCH_BATCH = 500


def _parse_stream_id(stream_id: str) -> tuple[int, int]:
    try:
        ms, _, seq = stream_id.partition("-")
        return int(ms), int(seq or 0)
    except (TypeError, ValueError):
        return (0, 0)


class EventBus:
    def __init__(self) -> None:
        self._redis: Any = None
        self._redis_tried = False
        self._ring: deque[dict[str, Any]] = deque(maxlen=get_settings().event_ring_fallback)
        self._mem_seq = 0
        self._redis_depth = 0
        self._subscribers: set[asyncio.Queue] = set()

    # -- redis lifecycle -----------------------------------------------------
    async def _ensure_redis(self) -> Any:
        if self._redis is not None:
            return self._redis
        if self._redis_tried and self._redis is None:
            # retry cheaply on every publish — redis may come back
            pass
        self._redis_tried = True
        url = get_settings().redis_url
        if not url:
            return None
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
            await client.ping()
            self._redis = client
            log.info("event bus: redis streams at %s", url)
            return client
        except Exception as exc:
            log.info("event bus: redis unavailable (%s); using memory ring", exc)
            self._redis = None
            return None

    # -- publish ---------------------------------------------------------------
    async def publish(self, event: dict[str, Any]) -> str:
        settings = get_settings()
        client = await self._ensure_redis()
        if client is not None:
            try:
                stream_id = await client.xadd(
                    settings.event_stream_name,
                    {"event": json.dumps(event, default=str)},
                    maxlen=settings.event_stream_maxlen,
                    approximate=True,
                )
                if isinstance(stream_id, bytes):
                    stream_id = stream_id.decode()
                event["stream_id"] = stream_id
                self._redis_depth = min(self._redis_depth + 1, settings.event_stream_maxlen)
                self._fanout(event)
                return stream_id
            except Exception as exc:
                log.warning("event bus: redis XADD failed (%s); falling back to memory", exc)
                self._redis = None
        stream_id = self._memory_append(event)
        self._fanout(event)
        return stream_id

    def _memory_append(self, event: dict[str, Any]) -> str:
        now_ms = int(time.time() * 1000)
        last_ms, last_seq = _parse_stream_id(self._ring[-1]["stream_id"]) if self._ring else (0, 0)
        if now_ms <= last_ms:
            now_ms, self._mem_seq = last_ms, last_seq + 1
        else:
            self._mem_seq = 0
        stream_id = f"{now_ms}-{self._mem_seq}"
        event["stream_id"] = stream_id
        self._ring.append(event)
        return stream_id

    # -- replay ----------------------------------------------------------------
    async def replay(
        self,
        since_id: Optional[str] = None,
        limit: int = 100,
        event_types: Optional[list[str]] = None,
        asset: Optional[str] = None,
        severities: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Newest-first filtered replay of durable events after `since_id`
        (exclusive; None = from the beginning of what is retained)."""
        if self._redis is not None:
            events = await self._replay_redis(since_id, limit)
        else:
            events = self._replay_memory(since_id, limit)
        return self._filter(events, event_types, asset, severities)[:limit]

    async def _replay_redis(self, since_id: Optional[str], limit: int) -> list[dict[str, Any]]:
        settings = get_settings()
        out: list[dict[str, Any]] = []
        max_id = "+"
        min_id = f"({since_id}" if since_id else "-"
        try:
            for _ in range(5):  # bounded batch loop
                rows = await self._redis.xrevrange(
                    settings.event_stream_name, max=max_id, min=min_id, count=_FETCH_BATCH
                )
                if not rows:
                    break
                for raw_id, fields in rows:
                    if isinstance(raw_id, bytes):
                        raw_id = raw_id.decode()
                    raw = fields.get(b"event") or fields.get("event")
                    try:
                        event = json.loads(raw)
                    except Exception:
                        continue
                    event["stream_id"] = raw_id
                    out.append(event)
                    if len(out) >= limit:
                        return out
                last_ms, last_seq = _parse_stream_id(raw_id)
                if len(rows) < _FETCH_BATCH:
                    break
                max_id = f"{last_ms}-{last_seq - 1}" if last_seq > 0 else f"{last_ms - 1}-9999999"
        except Exception as exc:
            log.warning("event bus: redis replay failed (%s); falling back to memory", exc)
            self._redis = None
            return self._replay_memory(since_id, limit)
        return out

    def _replay_memory(self, since_id: Optional[str], limit: int) -> list[dict[str, Any]]:
        threshold = _parse_stream_id(since_id) if since_id else None
        out: list[dict[str, Any]] = []
        for event in reversed(self._ring):
            if threshold is not None and _parse_stream_id(event["stream_id"]) <= threshold:
                continue
            out.append(event)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _filter(
        events: list[dict[str, Any]],
        event_types: Optional[list[str]],
        asset: Optional[str],
        severities: Optional[list[str]],
    ) -> list[dict[str, Any]]:
        out = []
        for e in events:
            if event_types and e.get("type") not in event_types:
                continue
            if asset and (e.get("asset") or "").upper() != asset.upper():
                continue
            if severities and e.get("severity") not in severities:
                continue
            out.append(e)
        return out

    # -- live fan-out ------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _fanout(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                self._subscribers.discard(q)

    # -- introspection -----------------------------------------------------------
    def backend_name(self) -> str:
        return "redis_streams" if self._redis is not None else "memory"

    def depth(self) -> int:
        if self._redis is not None:
            return self._redis_depth
        return len(self._ring)


_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
