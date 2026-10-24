"""Event model + bus tests: envelope completeness, memory-fallback
publish/replay, newest-first ordering, filters, backend/depth reporting."""

from __future__ import annotations

import pytest

from app.events.bus import EventBus
from app.events.model import EVENT_TYPES, make_event

CONTRACT_KEYS = {
    "specversion", "id", "type", "source", "time", "published_at", "asset",
    "venue", "instrument", "severity", "confidence", "summary", "evidence",
    "measurements", "methodology_version", "idempotency_key", "scenario_id",
    "stream_id",
}


def _event(**over):
    kwargs = dict(
        type="FUNDING_EXTREME",
        source="skybus://detectors/funding",
        summary="test event",
        idempotency_key="test:1",
        asset="BTC",
        venue="binance",
        severity="warning",
        observed={"funding_rate": 0.001},
        estimated={"model_note": "x"},
    )
    kwargs.update(over)
    return make_event(**kwargs)


def test_envelope_completeness():
    ev = _event()
    assert CONTRACT_KEYS <= set(ev.keys())
    assert ev["specversion"] == "1.0"
    assert ev["methodology_version"] == "detectors.v1"
    assert ev["measurements"]["observed"] == {"funding_rate": 0.001}
    assert ev["measurements"]["estimated"] == {"model_note": "x"}
    assert ev["stream_id"] is None  # set by the bus on publish
    assert len(ev["id"]) == 26  # ULID


def test_event_types_enum_has_16():
    assert len(EVENT_TYPES) == 16
    for t in ("FUNDING_EXTREME", "DATA_STALE", "SCENARIO_CREATED", "NEWS_BREAKING"):
        assert t in EVENT_TYPES


def test_unknown_type_rejected():
    with pytest.raises(ValueError):
        make_event(type="NOT_A_TYPE", source="x", summary="x", idempotency_key="k")


def test_unknown_severity_rejected():
    with pytest.raises(ValueError):
        make_event(
            type="FUNDING_EXTREME", source="x", summary="x",
            idempotency_key="k", severity="fatal",
        )


async def test_publish_replay_memory_fallback():
    bus = EventBus()  # tests run with REDIS_URL="" => memory backend
    assert bus.backend_name() == "memory"
    e1 = await bus.publish(_event(idempotency_key="t:1"))
    e2 = await bus.publish(_event(idempotency_key="t:2", type="NEWS_BREAKING", severity="info"))
    assert e1 and e2 and e1 != e2
    assert bus.depth() == 2
    events = await bus.replay()
    assert len(events) == 2
    assert all(ev["stream_id"] for ev in events)


async def test_replay_newest_first_and_since_id():
    bus = EventBus()
    ids = [await bus.publish(_event(idempotency_key=f"o:{i}")) for i in range(5)]
    events = await bus.replay()
    got = [e["stream_id"] for e in events]
    assert got == list(reversed(ids))  # newest first
    # since_id is exclusive
    events = await bus.replay(since_id=ids[1])
    got = [e["stream_id"] for e in events]
    assert got == list(reversed(ids[2:]))


async def test_replay_filters_and_limit():
    bus = EventBus()
    await bus.publish(_event(idempotency_key="f:1", type="FUNDING_EXTREME", asset="BTC"))
    await bus.publish(_event(idempotency_key="f:2", type="NEWS_BREAKING", asset="ETH", severity="info"))
    await bus.publish(_event(idempotency_key="f:3", type="FUNDING_EXTREME", asset="ETH", severity="critical"))

    by_type = await bus.replay(event_types=["FUNDING_EXTREME"])
    assert {e["idempotency_key"] for e in by_type} == {"f:1", "f:3"}

    by_asset = await bus.replay(asset="ETH")
    assert {e["idempotency_key"] for e in by_asset} == {"f:2", "f:3"}

    by_sev = await bus.replay(severities=["critical"])
    assert [e["idempotency_key"] for e in by_sev] == ["f:3"]

    limited = await bus.replay(limit=1)
    assert len(limited) == 1
    assert limited[0]["idempotency_key"] == "f:3"  # newest first


async def test_subscribe_receives_live_events():
    bus = EventBus()
    q = bus.subscribe()
    await bus.publish(_event(idempotency_key="s:1"))
    event = q.get_nowait()
    assert event["idempotency_key"] == "s:1"
    bus.unsubscribe(q)
    await bus.publish(_event(idempotency_key="s:2"))
    assert q.empty()


async def test_redis_failure_falls_back_to_memory():
    bus = EventBus()
    # point at an unreachable redis; publish must not raise
    from app.core.config import get_settings

    settings = get_settings()
    try:
        object.__setattr__(settings, "redis_url", "redis://127.0.0.1:1/0")
        sid = await bus.publish(_event(idempotency_key="r:1"))
        assert sid
        assert bus.backend_name() == "memory"
        assert bus.depth() == 1
    finally:
        object.__setattr__(settings, "redis_url", "")
