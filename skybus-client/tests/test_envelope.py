"""Envelope parsing, including the available:false (never fabricated) case."""

from __future__ import annotations

import respx
from httpx import Response

from skybus_client import SkybusClient
from skybus_client.models import MarketOverview

from conftest import BASE_URL, make_envelope

OVERVIEW = {
    "total_market_cap": 2_500_000_000_000.0,
    "total_volume_24h": 95_000_000_000.0,
    "btc_dominance": 54.2,
    "eth_dominance": 17.1,
    "market_cap_change_24h_pct": 1.8,
    "fear_greed": {
        "value": 61,
        "classification": "Greed",
        "source": "alternative.me",
        "attribution": "https://alternative.me/crypto/fear-and-greed-index/",
    },
}


async def test_envelope_parsing_market_overview():
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/market/overview").mock(
            return_value=Response(200, json=make_envelope(OVERVIEW, freshness_sec=4.2))
        )
        async with SkybusClient(BASE_URL, api_key="k") as client:
            env = await client.get_market_overview()

    assert env.schema_version == "agent.v1"
    assert env.request_id == "01JTESTREQUESTID000000000"
    assert env.freshness_sec == 4.2
    assert env.stale is False
    assert env.available is True
    assert env.provenance == ["test"]
    assert isinstance(env.data, MarketOverview)
    assert env.data.total_market_cap == 2_500_000_000_000.0
    assert env.data.fear_greed is not None
    assert env.data.fear_greed.classification == "Greed"
    assert env.is_fresh(60)


async def test_envelope_available_false_means_no_fabricated_data():
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/market/overview").mock(
            return_value=Response(
                200,
                json=make_envelope(None, available=False, observed_at=None, freshness_sec=None),
            )
        )
        async with SkybusClient(BASE_URL, api_key="k") as client:
            env = await client.get_market_overview()

    assert env.available is False
    assert env.data is None  # missing data surfaces as None, never fabricated


async def test_envelope_tolerates_unknown_extra_fields():
    payload = make_envelope({**OVERVIEW, "brand_new_field": {"nested": True}})
    payload["future_envelope_field"] = 123
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/market/overview").mock(
            return_value=Response(200, json=payload)
        )
        async with SkybusClient(BASE_URL, api_key="k") as client:
            env = await client.get_market_overview()

    assert env.data.btc_dominance == 54.2
    assert env.data.brand_new_field == {"nested": True}
