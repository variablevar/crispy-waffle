"""TTL cache abstraction: Redis when reachable, in-process dict otherwise.

Every entry records `fetched_at` and a TTL. Callers may request expired
entries to implement the contract's stale-serving rule: when an upstream
fails but a (possibly expired) cached value exists, it is served with
`stale: true`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    fetched_at: float  # unix seconds
    ttl: float  # seconds

    @property
    def expired(self) -> bool:
        return (time.time() - self.fetched_at) > self.ttl


class BaseCache:
    is_redis: bool = False

    async def get_entry(self, key: str) -> Optional[CacheEntry]: ...
    async def set(self, key: str, value: Any, ttl: float) -> None: ...

    async def get_fresh(self, key: str) -> Optional[Any]:
        entry = await self.get_entry(key)
        if entry is not None and not entry.expired:
            return entry.value
        return None


class MemoryCache(BaseCache):
    def __init__(self, max_keys: int = 10_000) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._max_keys = max_keys

    async def get_entry(self, key: str) -> Optional[CacheEntry]:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ttl: float) -> None:
        if len(self._store) >= self._max_keys and key not in self._store:
            # evict oldest
            oldest = min(self._store, key=lambda k: self._store[k].fetched_at)
            self._store.pop(oldest, None)
        self._store[key] = CacheEntry(value=value, fetched_at=time.time(), ttl=ttl)


class RedisCache(BaseCache):
    is_redis = True

    def __init__(self, client: Any) -> None:
        self._client = client
        self._fallback = MemoryCache()

    async def get_entry(self, key: str) -> Optional[CacheEntry]:
        try:
            raw = await self._client.get(f"skybus:{key}")
        except Exception as exc:  # redis went away — degrade to memory
            log.warning("redis get failed, using memory fallback: %s", exc)
            return await self._fallback.get_entry(key)
        if raw is None:
            return await self._fallback.get_entry(key)
        try:
            payload = json.loads(raw)
            return CacheEntry(
                value=payload["value"], fetched_at=payload["fetched_at"], ttl=payload["ttl"]
            )
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: float) -> None:
        entry = CacheEntry(value=value, fetched_at=time.time(), ttl=ttl)
        await self._fallback.set(key, value, ttl)
        try:
            payload = json.dumps(
                {"value": value, "fetched_at": entry.fetched_at, "ttl": ttl}, default=str
            )
            # keep redis copy a bit longer than the ttl so stale-serving works
            await self._client.set(f"skybus:{key}", payload, ex=int(max(ttl * 10, ttl + 3600)))
        except Exception as exc:
            log.warning("redis set failed (memory fallback still updated): %s", exc)


@dataclass
class _CacheHolder:
    cache: BaseCache = field(default_factory=MemoryCache)


_holder = _CacheHolder()


async def init_cache(redis_url: str | None) -> BaseCache:
    """Try Redis; fall back to in-process cache when unreachable."""
    if redis_url:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            await client.ping()
            _holder.cache = RedisCache(client)
            log.info("cache: using redis at %s", redis_url)
            return _holder.cache
        except Exception as exc:
            log.info("cache: redis unavailable (%s); using in-memory cache", exc)
    _holder.cache = MemoryCache()
    return _holder.cache


def get_cache() -> BaseCache:
    return _holder.cache
