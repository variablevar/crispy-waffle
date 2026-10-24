"""Typed error mapping: 401/403 -> auth, 404 -> not found, 429 -> rate limit
(honoring Retry-After), 5xx/network -> unavailable after retries."""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response

from skybus_client import (
    SkybusAuthError,
    SkybusClient,
    SkybusNotFoundError,
    SkybusRateLimitError,
    SkybusUnavailableError,
)

from conftest import BASE_URL, make_error

ROUTE = "/api/v1/agent/system/health"


async def test_401_raises_auth_error():
    with respx.mock(base_url=BASE_URL) as router:
        router.get(ROUTE).mock(
            return_value=Response(401, json=make_error("unauthorized", "missing or invalid API key"))
        )
        async with SkybusClient(BASE_URL, api_key="bad") as client:
            with pytest.raises(SkybusAuthError) as excinfo:
                await client.get_health()

    err = excinfo.value
    assert err.status == 401
    assert err.code == "unauthorized"
    assert err.request_id == "01JERR00000000000000000"


async def test_403_raises_auth_error():
    with respx.mock(base_url=BASE_URL) as router:
        router.get(ROUTE).mock(
            return_value=Response(403, json=make_error("forbidden", "scope 'read' required"))
        )
        async with SkybusClient(BASE_URL, api_key="k") as client:
            with pytest.raises(SkybusAuthError) as excinfo:
                await client.get_health()
    assert excinfo.value.status == 403
    assert excinfo.value.code == "forbidden"


async def test_404_raises_not_found():
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/assets/NOPE/snapshot").mock(
            return_value=Response(404, json=make_error("not_found", "unknown asset NOPE"))
        )
        async with SkybusClient(BASE_URL, api_key="k") as client:
            with pytest.raises(SkybusNotFoundError) as excinfo:
                await client.get_snapshot("NOPE")
    assert excinfo.value.status == 404
    assert excinfo.value.code == "not_found"


async def test_429_raises_rate_limit_with_retry_after():
    with respx.mock(base_url=BASE_URL) as router:
        router.get(ROUTE).mock(
            return_value=Response(
                429,
                json=make_error("rate_limited", "token bucket exhausted"),
                headers={"Retry-After": "2"},
            )
        )
        async with SkybusClient(BASE_URL, api_key="k", max_retries=0) as client:
            with pytest.raises(SkybusRateLimitError) as excinfo:
                await client.get_health()

    err = excinfo.value
    assert err.status == 429
    assert err.code == "rate_limited"
    assert err.retry_after == 2.0
    assert err.request_id == "01JERR00000000000000000"


async def test_429_honors_retry_after_before_retrying(monkeypatch):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("skybus_client.client._sleep", fake_sleep)

    ok_payload = {
        "schema_version": "agent.v1",
        "request_id": "r1",
        "observed_at": None,
        "processed_at": "2026-10-24T00:00:00Z",
        "freshness_sec": None,
        "stale": False,
        "available": True,
        "provenance": [],
        "methodology_version": None,
        "data": {"status": "ok", "services": {}, "event_stream": {"backend": "memory", "depth": 0}, "uptime_sec": 1},
    }
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get(ROUTE)
        route.side_effect = [
            Response(
                429,
                json=make_error("rate_limited", "slow down"),
                headers={"Retry-After": "0.25"},
            ),
            Response(200, json=ok_payload),
        ]
        async with SkybusClient(BASE_URL, api_key="k", max_retries=1) as client:
            env = await client.get_health()

    assert sleeps == [0.25]  # slept exactly the Retry-After value, then retried
    assert env.data.status == "ok"


async def test_500_retries_then_raises_unavailable(monkeypatch):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("skybus_client.client._sleep", fake_sleep)

    with respx.mock(base_url=BASE_URL) as router:
        router.get(ROUTE).mock(
            return_value=Response(500, json=make_error("upstream_unavailable", "redis down"))
        )
        async with SkybusClient(BASE_URL, api_key="k", max_retries=2) as client:
            with pytest.raises(SkybusUnavailableError) as excinfo:
                await client.get_health()

    assert excinfo.value.status == 500
    assert excinfo.value.code == "upstream_unavailable"
    assert len(sleeps) == 2  # retried twice before giving up


async def test_network_error_raises_unavailable(monkeypatch):
    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("skybus_client.client._sleep", fake_sleep)

    with respx.mock(base_url=BASE_URL) as router:
        router.get(ROUTE).mock(side_effect=httpx.ConnectError("connection refused"))
        async with SkybusClient(BASE_URL, api_key="k", max_retries=1) as client:
            with pytest.raises(SkybusUnavailableError) as excinfo:
                await client.get_health()

    assert excinfo.value.status is None
    assert excinfo.value.code == "network_error"


async def test_api_key_header_sent():
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get(ROUTE).mock(
            return_value=Response(401, json=make_error("unauthorized", "nope"))
        )
        async with SkybusClient(BASE_URL, api_key="secret-key") as client:
            with pytest.raises(SkybusAuthError):
                await client.get_health()

    assert route.calls[0].request.headers["X-API-Key"] == "secret-key"
