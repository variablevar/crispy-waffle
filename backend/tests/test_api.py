"""API shape tests — offline; upstream calls are monkeypatched.

Verifies contract shapes, the unavailable-source behaviour (available:false,
never fabricated numbers) and the alerts CRUD roundtrip on the in-memory store.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import FetchResult, coingecko


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


COIN_SUMMARY_KEYS = {
    "id", "symbol", "name", "image", "price", "change_1h", "change_24h",
    "change_7d", "market_cap", "volume_24h", "circulating_supply",
    "dominance", "sparkline", "trend", "sentiment", "news_count_24h",
    "updated_at", "stale",
}


def _ok(value):
    return FetchResult(
        value=value, fetched_at=datetime.now(timezone.utc), stale=False, available=True
    )


def _unavailable():
    return FetchResult(value=None, fetched_at=None, stale=False, available=False)


def test_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in ("ok", "degraded")
    for svc in ("redis", "database", "binance_ws", "bybit_ws", "coingecko"):
        assert svc in body["services"]


def test_market_top_shape(client, monkeypatch, coingecko_market_row, coingecko_global):
    async def fake_markets(limit=100, page=1):
        return _ok([coingecko_market_row])

    async def fake_global():
        return _ok(coingecko_global)

    monkeypatch.setattr(coingecko, "top_markets", fake_markets)
    monkeypatch.setattr(coingecko, "global_overview", fake_global)

    res = client.get("/api/v1/market/top?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["available"] is True
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert COIN_SUMMARY_KEYS <= set(item.keys())
    assert item["symbol"] == "BTC"
    assert item["price"] == 67000.0
    assert item["dominance"] == 55.0
    assert item["trend"] in ("bullish", "bearish", "neutral")


def test_market_top_unavailable_not_fabricated(client, monkeypatch):
    async def fake_markets(*a, **k):
        return _unavailable()

    async def fake_global():
        return _unavailable()

    monkeypatch.setattr(coingecko, "top_markets", fake_markets)
    monkeypatch.setattr(coingecko, "global_overview", fake_global)

    res = client.get("/api/v1/market/top?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["meta"]["available"] is False


def test_unknown_coin_404(client):
    res = client.get("/api/v1/coins/NOTACOIN")
    assert res.status_code == 404


def test_news_feed_shape_offline(client, monkeypatch):
    from app.services.news import gnews, newsdata, rss

    async def _empty():
        return []

    async def _empty_all():
        return []

    monkeypatch.setattr(newsdata, "safe_fetch", _empty)
    monkeypatch.setattr(gnews, "safe_fetch", _empty)
    monkeypatch.setattr(rss, "safe_fetch_all", _empty_all)

    res = client.get("/api/v1/news?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert "available" in body["meta"]

    res = client.get("/api/v1/news/categories")
    assert res.status_code == 200
    cats = res.json()["categories"]
    for expected in ("halving", "token_unlock", "exchange_listing", "etf", "hack", "macro"):
        assert expected in cats

    res = client.get("/api/v1/news/sources")
    assert res.status_code == 200
    sources = res.json()["sources"]
    assert any(s["name"] == "newsdata" and s["configured"] is False for s in sources)


def test_alerts_crud_roundtrip(client):
    res = client.post(
        "/api/v1/alerts",
        json={
            "type": "price_cross",
            "symbol": "BTC",
            "params": {"threshold": 70000, "direction": "above"},
            "severity": "warning",
            "cooldown_sec": 300,
        },
    )
    assert res.status_code == 201
    rule = res.json()
    assert rule["type"] == "price_cross"
    assert rule["symbol"] == "BTC"
    assert rule["active"] is True

    res = client.get("/api/v1/alerts")
    assert res.status_code == 200
    ids = [r["id"] for r in res.json()["items"]]
    assert rule["id"] in ids

    res = client.delete(f"/api/v1/alerts/{rule['id']}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True

    res = client.delete(f"/api/v1/alerts/{rule['id']}")
    assert res.status_code == 404

    res = client.get("/api/v1/alerts/events")
    assert res.status_code == 200
    assert isinstance(res.json()["items"], list)


def test_alert_validation_rejects_bad_type(client):
    res = client.post("/api/v1/alerts", json={"type": "not_a_type", "params": {}})
    assert res.status_code == 422
