"""Agent API tests: auth, envelope shape, cursor pagination, events, 404.

Offline: upstreams fail gracefully (available:false), the event bus runs on
its in-memory fallback (REDIS_URL="" in conftest).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

KEY = "testkey-agent-123"

ENVELOPE_KEYS = {
    "schema_version", "request_id", "observed_at", "processed_at",
    "freshness_sec", "stale", "available", "provenance",
    "methodology_version", "data",
}


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def agent_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_api_keys", f"gtquant:{KEY}")
    return KEY


def test_unauthorized_without_key(client):
    res = client.get("/api/v1/agent/system/health")
    assert res.status_code == 401
    body = res.json()
    assert body["error"]["code"] == "unauthorized"
    assert "request_id" in body["error"]


def test_health_with_key(client, agent_key):
    res = client.get("/api/v1/agent/system/health", headers={"X-API-Key": agent_key})
    assert res.status_code == 200
    body = res.json()
    assert ENVELOPE_KEYS <= set(body.keys())
    assert body["schema_version"] == "agent.v1"
    assert body["request_id"]
    assert res.headers.get("X-Request-ID") == body["request_id"]
    data = body["data"]
    assert "services" in data
    assert data["event_stream"]["backend"] in ("redis_streams", "memory", "unavailable")


def test_snapshot_envelope(client, agent_key):
    res = client.get("/api/v1/agent/assets/BTC/snapshot", headers={"X-API-Key": agent_key})
    assert res.status_code == 200
    body = res.json()
    assert ENVELOPE_KEYS <= set(body.keys())
    data = body["data"]
    assert data["asset"] == "BTC"
    assert "prices" in data and "taker_ratio" in data and "funding" in data
    # offline: upstreams unreachable -> never fabricated
    if not body["available"]:
        assert data["prices"] == []


def test_unknown_asset_404(client, agent_key):
    res = client.get("/api/v1/agent/assets/NOTACOIN/snapshot", headers={"X-API-Key": agent_key})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_news_cursor_pagination_unit():
    from app.agentapi.routers import _news_page

    items = [
        {"id": f"n{i}", "published_at": f"2026-10-2{3-i}T00:00:00Z", "headline": f"h{i}"}
        for i in range(5)
    ]
    page1 = _news_page(items, 2, None)
    assert [i["id"] for i in page1["items"]] == ["n0", "n1"]
    assert page1["next_cursor"]
    page2 = _news_page(items, 2, page1["next_cursor"])
    assert [i["id"] for i in page2["items"]] == ["n2", "n3"]
    page3 = _news_page(items, 2, page2["next_cursor"])
    assert [i["id"] for i in page3["items"]] == ["n4"]
    assert page3["next_cursor"] is None


def test_events_endpoint_and_replay(client, agent_key):
    import asyncio

    from app.events.bus import get_event_bus
    from app.events.model import make_event

    bus = get_event_bus()

    async def _publish():
        await bus.publish(
            make_event(
                type="FUNDING_EXTREME", source="skybus://detectors/test",
                asset="ZZTEST", severity="warning",
                summary="test funding extreme", idempotency_key="test:funding:1",
            )
        )
        await bus.publish(
            make_event(
                type="OPEN_INTEREST_SPIKE", source="skybus://detectors/test",
                asset="ZZTEST", severity="critical",
                summary="test oi spike", idempotency_key="test:oi:1",
            )
        )

    asyncio.run(_publish())

    res = client.get("/api/v1/agent/events?asset=ZZTEST", headers={"X-API-Key": agent_key})
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    items = body["data"]["items"]
    assert len(items) == 2
    assert items[0]["type"] == "OPEN_INTEREST_SPIKE"  # newest first
    ev = items[0]
    for key in ("specversion", "id", "type", "time", "published_at", "severity",
                "idempotency_key", "stream_id", "measurements"):
        assert key in ev, key
    assert ev["specversion"] == "1.0"

    # cursor = stream_id of the newest -> replay yields only the older one
    cursor = items[0]["stream_id"]
    res2 = client.get(
        f"/api/v1/agent/events?asset=ZZTEST&cursor={cursor}",
        headers={"X-API-Key": agent_key},
    )
    older = res2.json()["data"]["items"]
    assert [e["type"] for e in older] == ["FUNDING_EXTREME"]

    # type filter
    res3 = client.get(
        "/api/v1/agent/events?asset=ZZTEST&type=FUNDING_EXTREME",
        headers={"X-API-Key": agent_key},
    )
    assert [e["type"] for e in res3.json()["data"]["items"]] == ["FUNDING_EXTREME"]


def test_ws_stream_requires_auth(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/agent/stream") as ws:
            ws.receive_json()  # server accepts, then closes with 4401
    assert exc_info.value.code == 4401
