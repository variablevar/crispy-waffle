"""Stream tests: parsing, dedupe, backoff schedule, reconnect + resume.

The WebSocket is faked — no real network. The fake replays frames, then
raises ConnectionClosedOK to exercise the client's reconnect path.
"""

from __future__ import annotations

import asyncio
import json

from websockets.exceptions import ConnectionClosedOK

from skybus_client import SkybusClient
from skybus_client._streaming import (
    Backoff,
    DedupeSet,
    build_stream_url,
    build_subscribe_message,
    parse_stream_message,
)
from skybus_client.models import AgentEvent

from conftest import BASE_URL, make_event

_CLOSE = object()


class FakeWS:
    """Minimal fake websocket: replays queued frames, then 'drops'."""

    def __init__(self, frames):
        self._queue = asyncio.Queue()
        for frame in frames:
            self._queue.put_nowait(frame)
        self._queue.put_nowait(_CLOSE)
        self.sent: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue.get()
        if item is _CLOSE:
            raise ConnectionClosedOK(None, None)
        return item


# -- URL / subscribe message -------------------------------------------------


def test_build_stream_url_schemes():
    assert (
        build_stream_url("http://localhost:8123")
        == "ws://localhost:8123/api/v1/agent/stream"
    )
    assert (
        build_stream_url("https://skybus.example.com/")
        == "wss://skybus.example.com/api/v1/agent/stream"
    )


def test_build_subscribe_message_omits_unset_filters():
    msg = json.loads(build_subscribe_message(assets=["BTC", "ETH"], last_event_id="169-0"))
    assert msg == {
        "action": "subscribe",
        "assets": ["BTC", "ETH"],
        "last_event_id": "169-0",
    }
    minimal = json.loads(build_subscribe_message())
    assert minimal == {"action": "subscribe"}


# -- parsing ------------------------------------------------------------------


def test_parse_event_frame():
    frame = json.dumps({"kind": "event", "event": make_event("01JA", idempotency_key="k1")})
    event = parse_stream_message(frame)
    assert isinstance(event, AgentEvent)
    assert event.id == "01JA"
    assert event.idempotency_key == "k1"


def test_parse_heartbeat_and_subscribed_are_internal():
    assert parse_stream_message(json.dumps({"kind": "heartbeat", "ts": 1.0})) is None
    assert (
        parse_stream_message(
            json.dumps({"kind": "subscribed", "subscription_id": "s1", "replay_from": None})
        )
        is None
    )
    assert parse_stream_message(json.dumps({"kind": "future_kind"})) is None


# -- dedupe ---------------------------------------------------------------------


def _evt(event_id, key=None):
    return AgentEvent.model_validate(make_event(event_id, idempotency_key=key))


def test_dedupe_by_idempotency_key_and_id():
    dedupe = DedupeSet()
    assert dedupe.seen(_evt("id-1", "key-1")) is False
    assert dedupe.seen(_evt("id-2", "key-1")) is True  # same idempotency key
    assert dedupe.seen(_evt("id-1", "key-2")) is True  # same event id
    assert dedupe.seen(_evt("id-3", "key-3")) is False


def test_dedupe_bounded_eviction():
    dedupe = DedupeSet(maxsize=4)
    dedupe.seen(_evt("a"))
    dedupe.seen(_evt("b"))
    dedupe.seen(_evt("c"))  # 3 keys; next insert pushes past maxsize=4? no -> 4 max
    dedupe.seen(_evt("d"))  # 4 keys
    dedupe.seen(_evt("e"))  # evicts "a"
    assert len(dedupe) == 4
    assert dedupe.seen(_evt("a")) is False  # evicted, counts as new
    assert dedupe.seen(_evt("e")) is True


# -- backoff --------------------------------------------------------------------


def test_backoff_schedule_doubles_and_caps():
    backoff = Backoff(base=0.5, cap=30.0)
    schedule = [backoff.base_delay(n) for n in range(9)]
    assert schedule == [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


def test_backoff_jitter_bounds_and_reset():
    backoff = Backoff(base=0.5, cap=30.0, rng=lambda: 0.0)
    assert backoff.next_delay() == 0.25  # 0.5 * (0.5 + 0.5*0)
    assert backoff.attempt == 1
    backoff.reset()
    assert backoff.attempt == 0


# -- reconnect / resume ---------------------------------------------------------


async def test_stream_reconnects_resumes_and_dedupes(monkeypatch):
    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("skybus_client.client._sleep", fake_sleep)

    event_a = make_event("01JA", idempotency_key="funding:BTC:t1", stream_id="1700-0")
    dup_by_key = make_event("01JA2", idempotency_key="funding:BTC:t1", stream_id="1701-0")
    dup_by_id = make_event("01JA", idempotency_key="funding:BTC:t2", stream_id="1702-0")
    event_b = make_event("01JB", idempotency_key="oi:BTC:t1", stream_id="1703-0")

    connections: list[FakeWS] = []
    scripts = [
        [
            json.dumps({"kind": "subscribed", "subscription_id": "s1", "replay_from": "1600-0"}),
            json.dumps({"kind": "heartbeat", "ts": 1.0}),
            json.dumps({"kind": "event", "event": event_a}),
            json.dumps({"kind": "event", "event": dup_by_key}),
            json.dumps({"kind": "event", "event": dup_by_id}),
        ],
        [
            json.dumps({"kind": "event", "event": event_b}),
        ],
    ]

    def fake_connect(url, additional_headers=None):
        ws = FakeWS(scripts[len(connections)])
        connections.append(ws)
        assert additional_headers == {"X-API-Key": "k"}
        assert url == "ws://testserver/api/v1/agent/stream"
        return ws

    monkeypatch.setattr("skybus_client.client._ws_connect", fake_connect)

    async with SkybusClient(BASE_URL, api_key="k") as client:
        gen = client.stream(assets=["BTC"], last_event_id="1600-0")
        first = await gen.__anext__()
        second = await gen.__anext__()
        await gen.aclose()

    assert first.id == "01JA"
    assert second.id == "01JB"

    # first frame on each connection is the subscribe message
    assert connections[0].sent[0]["action"] == "subscribe"
    assert connections[0].sent[0]["assets"] == ["BTC"]
    assert connections[0].sent[0]["last_event_id"] == "1600-0"

    # reconnect resumes from the last *yielded* event's stream_id
    assert connections[1].sent[0]["last_event_id"] == "1700-0"
