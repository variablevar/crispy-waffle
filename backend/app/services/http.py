"""Shared async HTTP layer: one httpx.AsyncClient, timeouts, per-host token
bucket, retry with exponential backoff honouring Retry-After."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.core import rate_limit

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_client: Optional[httpx.AsyncClient] = None


class UpstreamError(Exception):
    """Raised when an upstream call ultimately fails."""

    def __init__(self, message: str, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "SkyBus/1.0 (+https://github.com/skybus)"},
        )
    return _client


def set_client(client: httpx.AsyncClient | None) -> None:
    """Test hook: inject a mocked transport client."""
    global _client
    _client = client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def request(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 2,
    rate_per_min: float | None = None,
    timeout: httpx.Timeout | None = None,
) -> httpx.Response:
    host = urlparse(url).netloc
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        await rate_limit.throttle(host, rate_per_min)
        try:
            resp = await get_client().request(
                method, url, params=params, headers=headers, timeout=timeout or DEFAULT_TIMEOUT
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else 1.5 ** attempt
                last_exc = UpstreamError(f"HTTP {resp.status_code}", status=resp.status_code, url=url)
                if attempt < retries:
                    log.warning("upstream %s -> %s, retrying in %.1fs", url, resp.status_code, wait)
                    await asyncio.sleep(min(wait, 30.0))
                    continue
                raise last_exc
            resp.raise_for_status()
            return resp
        except UpstreamError:
            raise
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(1.5 ** attempt)
                continue
            raise UpstreamError(f"transport error: {exc}", url=url) from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamError(
                f"HTTP {exc.response.status_code}", status=exc.response.status_code, url=url
            ) from exc
    raise UpstreamError(f"request failed: {last_exc}", url=url)


async def get_json(url: str, **kwargs: Any) -> Any:
    resp = await request("GET", url, **kwargs)
    try:
        return resp.json()
    except Exception as exc:
        raise UpstreamError(f"invalid JSON from {url}: {exc}", url=url) from exc


async def get_text(url: str, **kwargs: Any) -> str:
    resp = await request("GET", url, **kwargs)
    return resp.text
