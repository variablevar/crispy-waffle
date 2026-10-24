"""Detector tests: synthetic LiveState / cache / news fixtures drive the
detectors; every assertion is on events the detector layer publishes."""

from __future__ import annotations

import time

import pytest

from app.core.cache import get_cache
from app.core.state import LiveState
from app.events import detectors
from app.events.bus import EventBus
from app.events.detectors import DetectorEngine
from app.services import iso


class FakeAggregator:
    def __init__(self, items_by_symbol: dict[str, list[dict]] | None = None):
        self._items = items_by_symbol or {}

    def latest_for_asset(self, symbol: str, limit: int = 5) -> list[dict]:
        return self._items.get(symbol.upper(), [])[:limit]


def _engine(state: LiveState | None = None, aggregator=None) -> DetectorEngine:
    return DetectorEngine(
        bus=EventBus(),
        state=state or LiveState(),
        aggregator=aggregator if aggregator is not None else FakeAggregator(),
    )


async def test_funding_extreme_fires_once():
    engine = _engine()
    await get_cache().set(
        "deriv:FND", {"binance_funding": 0.0012, "fetched_at": time.time()}, ttl=300
    )
    first = await engine.run_once(["FND"])
    second = await engine.run_once(["FND"])
    events = [e for e in first + second if e["type"] == "FUNDING_EXTREME"]
    assert len(events) == 1  # deduped on repeat
    ev = events[0]
    assert ev["asset"] == "FND"
    assert ev["venue"] == "binance"
    assert ev["severity"] == "critical"  # |0.12%| >= critical threshold
    assert ev["measurements"]["observed"]["funding_rate"] == 0.0012
    assert ev["idempotency_key"].startswith("funding:binance:FND:")
    assert ev["stream_id"] is not None  # bus persisted it


async def test_cross_exchange_divergence(monkeypatch):
    monkeypatch.setattr(detectors, "CROSS_SUSTAIN_SEC", 0.0)
    state = LiveState()
    state.update_price("binance", "XDV", 50000.0)
    state.update_price("bybit", "XDV", 50060.0)  # ~ -12 bps
    engine = _engine(state)
    events = await engine.run_once(["XDV"])
    xdiv = [e for e in events if e["type"] == "CROSS_EXCHANGE_DIVERGENCE"]
    assert len(xdiv) == 1
    assert xdiv[0]["measurements"]["observed"]["spread_bps"] < 0
    assert xdiv[0]["measurements"]["observed"]["binance_price"] == 50000.0


async def test_data_stale_then_recovered():
    state = LiveState()
    engine = _engine(state)
    await engine.run_once(["BTC"])  # baseline: both feeds down, no events
    state.update_price("binance", "BTC", 50000.0)  # feed comes alive
    events = await engine.run_once(["BTC"])
    rec = [e for e in events if e["type"] == "DATA_RECOVERED"]
    assert len(rec) == 1 and rec[0]["venue"] == "binance"

    state.mark_ws_down("binance")
    events = await engine.run_once(["BTC"])
    stale = [e for e in events if e["type"] == "DATA_STALE"]
    assert len(stale) == 1 and stale[0]["venue"] == "binance"
    assert stale[0]["severity"] == "warning"


async def test_news_breaking_importance_gate():
    now_iso = iso()
    agg = FakeAggregator(
        {
            "NWS": [
                {"id": "abc123", "headline": "Major ETF approval", "source": "rss:coindesk",
                 "published_at": now_iso, "importance": 4},
                {"id": "low1", "headline": "Minor gossip piece", "source": "rss:coinpaprika",
                 "published_at": now_iso, "importance": 2},
            ]
        }
    )
    engine = _engine(aggregator=agg)
    first = await engine.run_once(["NWS"])
    news = [e for e in first if e["type"] == "NEWS_BREAKING"]
    assert len(news) == 1  # only importance >= 4 fires
    assert news[0]["measurements"]["observed"]["headline"] == "Major ETF approval"
    second = await engine.run_once(["NWS"])
    assert not [e for e in second if e["type"] == "NEWS_BREAKING"]  # deduped


async def test_no_events_when_inputs_missing():
    engine = _engine()
    first = await engine.run_once(["ZZZ"])
    second = await engine.run_once(["ZZZ"])
    assert first == []
    assert second == []
    assert engine.bus.depth() == 0


async def test_liquidation_burst_from_observed_feed():
    state = LiveState()
    now_ms = int(time.time() * 1000)
    state.push_trade("binance_perp_liq", "LIQ", {
        "time": now_ms, "side": "long_liquidated", "size_usd": 300_000.0,
    })
    engine = _engine(state)
    events = await engine.run_once(["LIQ"])
    bursts = [e for e in events if e["type"] == "LONG_LIQUIDATION_BURST"]
    assert len(bursts) == 1
    assert bursts[0]["measurements"]["observed"]["long_liquidated_usd"] == 300_000.0


async def test_no_liquidation_burst_without_feed():
    engine = _engine(LiveState())
    events = await engine.run_once(["NOFD"])
    assert not [e for e in events if "LIQUIDATION_BURST" in e["type"]]
