"""Freshness helper + opt-in staleness guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import respx
from httpx import Response

from skybus_client import SkybusClient, SkybusStaleDataError

from conftest import BASE_URL, make_envelope

OVERVIEW = {
    "total_market_cap": 1.0,
    "total_volume_24h": 1.0,
    "btc_dominance": 50.0,
    "eth_dominance": 18.0,
    "market_cap_change_24h_pct": 0.5,
    "fear_greed": None,
}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def test_is_fresh_uses_observed_at():
    now = datetime.now(timezone.utc)
    fresh = make_envelope(OVERVIEW, observed_at=_iso(now - timedelta(seconds=5)))
    old = make_envelope(OVERVIEW, observed_at=_iso(now - timedelta(hours=1)))

    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/api/v1/agent/market/overview")
        route.side_effect = [Response(200, json=fresh), Response(200, json=old)]
        async with SkybusClient(BASE_URL, api_key="k") as client:
            env_fresh = await client.get_market_overview()
            env_old = await client.get_market_overview()

    assert env_fresh.is_fresh(60) is True
    assert env_old.is_fresh(60) is False


async def test_is_fresh_false_when_server_marks_stale():
    payload = make_envelope(OVERVIEW, stale=True)
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/market/overview").mock(return_value=Response(200, json=payload))
        async with SkybusClient(BASE_URL, api_key="k") as client:
            env = await client.get_market_overview()
    assert env.is_fresh(3600) is False  # server-asserted stale wins


async def test_staleness_guard_raises_when_opted_in():
    old = make_envelope(
        OVERVIEW,
        observed_at=_iso(datetime.now(timezone.utc) - timedelta(hours=2)),
    )
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/market/overview").mock(return_value=Response(200, json=old))
        async with SkybusClient(
            BASE_URL, api_key="k", max_acceptable_staleness_sec=60
        ) as client:
            with pytest.raises(SkybusStaleDataError) as excinfo:
                await client.get_market_overview()

    assert excinfo.value.code == "stale_data"
    assert excinfo.value.request_id == "01JTESTREQUESTID000000000"


async def test_staleness_guard_off_by_default():
    old = make_envelope(
        OVERVIEW,
        stale=True,
        observed_at=_iso(datetime.now(timezone.utc) - timedelta(days=7)),
    )
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/market/overview").mock(return_value=Response(200, json=old))
        async with SkybusClient(BASE_URL, api_key="k") as client:
            env = await client.get_market_overview()  # no raise; caller inspects
    assert env.stale is True
