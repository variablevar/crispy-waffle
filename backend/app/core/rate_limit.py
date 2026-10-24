"""Simple per-host token-bucket rate limiter for upstream API calls."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    rate_per_min: float
    _tokens: float = field(init=False)
    _last: float = field(init=False, default_factory=time.monotonic)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self._tokens = self.rate_per_min

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.rate_per_min, self._tokens + elapsed * (self.rate_per_min / 60.0))
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / (self.rate_per_min / 60.0)
                await asyncio.sleep(min(wait, 5.0))


_buckets: dict[str, TokenBucket] = {}

# conservative defaults per upstream host (free tiers)
_DEFAULT_RATES = {
    "api.coingecko.com": 10.0,
    "api.binance.com": 60.0,
    "fapi.binance.com": 60.0,
    "api.bybit.com": 60.0,
    "api.alternative.me": 10.0,
    "api.dexscreener.com": 30.0,
    "api.llama.fi": 30.0,
    "newsdata.io": 10.0,
    "gnews.io": 10.0,
}


def bucket_for(host: str, rate_per_min: float | None = None) -> TokenBucket:
    if host not in _buckets:
        rate = rate_per_min or _DEFAULT_RATES.get(host, 30.0)
        _buckets[host] = TokenBucket(rate_per_min=rate)
    return _buckets[host]


async def throttle(host: str, rate_per_min: float | None = None) -> None:
    await bucket_for(host, rate_per_min).acquire()


def _reset() -> None:
    """Test hook: clear all buckets."""
    _buckets.clear()
