"""Stream helpers for the SkyBus agent WebSocket protocol.

Factored out of the client so parsing, dedupe and backoff logic can be unit
tested without a real network connection.
"""

from __future__ import annotations

import json
import random
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Sequence

from .exceptions import SkybusError
from .models import AgentEvent

__all__ = [
    "Backoff",
    "DedupeSet",
    "build_stream_url",
    "build_subscribe_message",
    "parse_stream_message",
]


class Backoff:
    """Exponential backoff with jitter: ``base`` doubling up to ``cap``.

    Delays are ``min(cap, base * 2**attempt)`` multiplied by a jitter factor
    in ``[0.5, 1.0)``. ``rng`` is injectable for deterministic tests.
    """

    def __init__(
        self,
        base: float = 0.5,
        cap: float = 30.0,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self.base = base
        self.cap = cap
        self._rng = rng
        self.attempt = 0

    def base_delay(self, attempt: Optional[int] = None) -> float:
        """Pre-jitter delay for a given attempt (defaults to the current one)."""
        n = self.attempt if attempt is None else attempt
        return min(self.cap, self.base * (2**n))

    def next_delay(self) -> float:
        delay = self.base_delay()
        self.attempt += 1
        return delay * (0.5 + 0.5 * self._rng())

    def reset(self) -> None:
        self.attempt = 0


class DedupeSet:
    """Bounded in-memory dedupe over event id AND idempotency_key.

    The server uses ``idempotency_key`` as the dedupe key (contract advises
    consumers keep it for >=24h); the unique event ``id`` is tracked too so
    replays that repeat an id with a fresh key are still filtered. Bounded
    FIFO eviction at ``maxsize`` keys (~10k by default).
    """

    def __init__(self, maxsize: int = 10_000) -> None:
        self.maxsize = maxsize
        self._keys: "OrderedDict[str, None]" = OrderedDict()

    def seen(self, event: AgentEvent) -> bool:
        """Return True if the event was already seen; otherwise record it."""
        keys = [k for k in (event.id, event.idempotency_key) if k]
        if any(k in self._keys for k in keys):
            return True
        for k in keys:
            self._keys[k] = None
        while len(self._keys) > self.maxsize:
            self._keys.popitem(last=False)
        return False

    def __len__(self) -> int:
        return len(self._keys)


def build_stream_url(base_url: str) -> str:
    """``http(s)://host`` -> ``ws(s)://host/api/v1/agent/stream``."""
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    elif base.startswith(("ws://", "wss://")):
        pass
    else:
        raise SkybusError(
            f"cannot derive WebSocket URL from base_url {base_url!r}",
            code="invalid_base_url",
        )
    return base + "/api/v1/agent/stream"


def build_subscribe_message(
    assets: Optional[Sequence[str]] = None,
    venues: Optional[Sequence[str]] = None,
    event_types: Optional[Sequence[str]] = None,
    severities: Optional[Sequence[str]] = None,
    last_event_id: Optional[str] = None,
) -> str:
    """First-frame subscribe message per contract; only set fields are sent."""
    msg: Dict[str, Any] = {"action": "subscribe"}
    if assets is not None:
        msg["assets"] = list(assets)
    if venues is not None:
        msg["venues"] = list(venues)
    if event_types is not None:
        msg["event_types"] = list(event_types)
    if severities is not None:
        msg["severities"] = list(severities)
    if last_event_id is not None:
        msg["last_event_id"] = last_event_id
    return json.dumps(msg)


def parse_stream_message(raw: Any) -> Optional[AgentEvent]:
    """Parse one server frame.

    Returns the :class:`AgentEvent` for ``{"kind": "event"}`` frames and
    ``None`` for ``subscribed``/``heartbeat`` frames and unknown kinds
    (ignored for forward compatibility). Malformed JSON raises
    :class:`SkybusError` with ``code="protocol_error"``.
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    try:
        msg = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SkybusError(
            f"invalid JSON in stream message: {exc}", code="protocol_error"
        ) from exc
    if not isinstance(msg, dict):
        raise SkybusError("stream message is not a JSON object", code="protocol_error")
    if msg.get("kind") == "event":
        return AgentEvent.model_validate(msg["event"])
    return None
