import respx

from skybus_mcp import tools
from tests.conftest import API, envelope, mock_get

SNAPSHOT_DATA = {
    "asset": "BTC",
    "venues": {
        "binance": {"spot": {"price": 67250.5, "change_24h_pct": 1.8}},
        "bybit": {"usdt_perp": {"price": 67255.0, "funding": 0.0001, "open_interest": 123456.0}},
    },
    "taker_ratio": 1.04,
    "book_imbalance": 0.12,
    "trend": "up",
}


@respx.mock
async def test_get_asset_snapshot_returns_parsed_typed_data():
    route = mock_get(f"{API}/assets/BTC/snapshot", envelope(SNAPSHOT_DATA))
    result = await tools.get_asset_snapshot("BTC")
    assert "error" not in result
    assert result["available"] is True
    assert result["stale"] is False
    assert result["observed_at"] == "2026-10-23T16:00:00Z"
    assert result["data"]["asset"] == "BTC"
    assert result["data"]["taker_ratio"] == 1.04
    assert result["data"]["venues"]["bybit"]["usdt_perp"]["funding"] == 0.0001
    # Auth header sent, asset uppercased in path.
    assert route.calls[0].request.headers["X-API-Key"] == "test-key"
    assert route.calls[0].request.url.path == "/api/v1/agent/assets/BTC/snapshot"


@respx.mock
async def test_get_asset_snapshot_lowercase_asset_is_normalized():
    route = mock_get(f"{API}/assets/BTC/snapshot", envelope(SNAPSHOT_DATA))
    result = await tools.get_asset_snapshot("btc")
    assert "error" not in result
    assert route.called


async def test_get_asset_snapshot_invalid_asset_returns_structured_error():
    result = await tools.get_asset_snapshot("not a ticker!")
    assert result["error"]["code"] == "bad_request"


async def test_missing_api_key_returns_structured_error(monkeypatch):
    monkeypatch.delenv("SKYBUS_API_KEY")
    result = await tools.get_market_overview()
    assert result["error"]["code"] == "missing_api_key"
    assert "SKYBUS_API_KEY" in result["error"]["message"]
    # The key is never echoed back.
    assert "test-key" not in str(result)


@respx.mock
async def test_http_error_maps_to_structured_error():
    mock_get(
        f"{API}/market/overview",
        {"error": {"code": "unauthorized", "message": "invalid key", "request_id": "r1"}},
        status=401,
    )
    result = await tools.get_market_overview()
    assert result["error"]["code"] == "unauthorized"
    assert result["error"]["status"] == 401
    assert result["error"]["request_id"] == "r1"


@respx.mock
async def test_get_latest_news_scoped_and_clamped():
    items = [
        {
            "title": "BTC ETF inflows hit record",
            "source": "coindesk",
            "kind": "article",
            "category": "etf",
            "sentiment": "positive",
            "importance": "high",
        }
    ]
    route = mock_get(f"{API}/assets/BTC/news", envelope({"items": items, "next_cursor": None}))
    result = await tools.get_latest_news(asset="BTC", limit=5000)
    assert "error" not in result
    assert result["data"]["items"][0]["sentiment"] == "positive"
    # limit clamped to 100
    assert route.calls[0].request.url.params["limit"] == "100"


@respx.mock
async def test_get_liquidity_zones_preserves_labels_and_adds_note():
    data = {
        "asset": "BTC",
        "zones": [
            {"type": "observed_bid_wall", "label": "observed bid wall", "price": 66000, "strength": 0.9},
            {"type": "estimated_liquidation", "label": "ESTIMATED liquidation cluster", "price": 64500},
        ],
        "sweeps": [],
    }
    mock_get(f"{API}/assets/BTC/liquidity", envelope(data))
    result = await tools.get_liquidity_zones("BTC")
    assert "error" not in result
    labels = [z["label"] for z in result["data"]["zones"]]
    assert labels == ["observed bid wall", "ESTIMATED liquidation cluster"]
    assert "model outputs" in result["zone_note"]


LIQUIDITY_DATA = {
    "asset": "BTC",
    "zones": [
        {"type": "observed_ask_wall", "label": "observed ask wall", "price": 69000, "strength": 0.7},
        {"type": "estimated_support", "label": "ESTIMATED support band", "price_low": 65000, "price_high": 65500},
    ],
    "sweeps": [{"time": "2026-10-23T15:55:00Z", "direction": "down", "price": 66800, "source": "binance_ws"}],
}

SCENARIOS_DATA = {
    "scenarios": [
        {
            "id": "scn-1",
            "type": "bullish_continuation",
            "asset": "BTC",
            "instrument": "usdt_perp",
            "title": "Bullish continuation above 67k",
            "bias": "long",
            "market_regime": "trending_up",
            "status": "active",
            "trigger_conditions": ["hold above 67000"],
            "confirmation_signals": ["rising OI with positive funding"],
            "invalidation_conditions": ["4h close below 66000"],
            "evidence": [{"indicator": "trend", "value": "up", "supports": True}],
            "contradicting_evidence": [],
            "target_zones": [{"price_low": 69000, "price_high": 70000, "label": "prior high"}],
            "risks": ["funding flips negative"],
            "confidence": 0.62,
            "confidence_note": "rule-vote fraction, NOT a calibrated probability",
            "methodology": "scenario-engine",
            "methodology_version": "scenarios.v2",
            "generated_at": "2026-10-23T16:00:00Z",
            "stale": False,
        }
    ],
    "market_state": {"regime": "trending_up"},
}

NEWS_DATA = {
    "items": [
        {
            "title": "Whale moves 10k BTC to exchange",
            "source": "arkham",
            "kind": "onchain",
            "category": "flows",
            "sentiment": "negative",
            "importance": "medium",
        }
    ],
    "next_cursor": None,
}


@respx.mock
async def test_explain_market_event_composes_and_marks_estimated_labels():
    mock_get(f"{API}/assets/BTC/snapshot", envelope(SNAPSHOT_DATA))
    mock_get(f"{API}/assets/BTC/liquidity", envelope(LIQUIDITY_DATA))
    mock_get(f"{API}/assets/BTC/scenarios", envelope(SCENARIOS_DATA))
    mock_get(f"{API}/assets/BTC/news", envelope(NEWS_DATA))

    result = await tools.explain_market_event("BTC", "why is price stalling?")

    assert "error" not in result
    assert result["asset"] == "BTC"
    assert result["question"] == "why is price stalling?"
    assert result["generated_from"] == ["snapshot", "liquidity", "scenarios", "news"]
    assert result["unavailable"] == {}

    text = result["explanation"]
    # Verbatim estimated label preserved and explicitly marked as model output.
    assert "ESTIMATED support band" in text
    assert "[ESTIMATED — model output, not observed orders]" in text
    assert "[observed] observed ask wall" in text
    # Scenario details composed.
    assert "Bullish continuation above 67k" in text
    assert "hold above 67000" in text
    assert "4h close below 66000" in text
    assert "rule-vote fraction, NOT a calibrated probability" in text
    # News composed.
    assert "Whale moves 10k BTC to exchange" in text
    # No API key leakage.
    assert "test-key" not in str(result)


@respx.mock
async def test_explain_market_event_marks_unavailable_sections():
    mock_get(f"{API}/assets/BTC/snapshot", envelope(SNAPSHOT_DATA))
    mock_get(
        f"{API}/assets/BTC/liquidity",
        {"error": {"code": "upstream_unavailable", "message": "bybit feed down", "request_id": "r2"}},
        status=503,
    )
    mock_get(f"{API}/assets/BTC/scenarios", envelope(SCENARIOS_DATA))
    mock_get(f"{API}/assets/BTC/news", envelope(NEWS_DATA))

    result = await tools.explain_market_event("BTC", "what changed?")
    assert result["unavailable"]["liquidity"]["code"] == "upstream_unavailable"
    assert "liquidity: upstream_unavailable" in result["explanation"]
    assert "not fabricated" in result["explanation"]


async def test_explain_market_event_missing_key(monkeypatch):
    monkeypatch.delenv("SKYBUS_API_KEY")
    result = await tools.explain_market_event("BTC", "why up?")
    assert result["error"]["code"] == "missing_api_key"
