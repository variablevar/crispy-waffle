"""Agent event-stream WebSocket per AGENT_CONTRACT.md.

Protocol: client connects with `X-API-Key` header (preferred) or `?api_key=`
query param, sends a JSON subscribe message
`{action, assets, venues, event_types, severities, last_event_id}`, receives
`subscribed`, then optional replay (oldest-first) followed by live events and
25s heartbeats.

Auth delegates to `app.agentapi.auth.authenticate` (built in parallel); the
import is guarded so this module always imports — without auth available the
socket is rejected with close code 4401.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

import ulid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events.bus import EventBus, get_event_bus

log = logging.getLogger(__name__)

try:  # auth module is being built in parallel to this interface
    from app.agentapi.auth import authenticate
except Exception:  # pragma: no cover - depends on parallel workstream
    authenticate = None  # type: ignore[assignment]

router = APIRouter()

HEARTBEAT_SEC = 25.0
SUBSCRIBE_TIMEOUT_SEC = 15.0

CLOSE_UNAUTHORIZED = 4401
CLOSE_BAD_SUBSCRIBE = 4400


def _matches(event: dict[str, Any], sub: dict[str, Any]) -> bool:
    if sub["event_types"] and event.get("type") not in sub["event_types"]:
        return False
    if sub["assets"] and (event.get("asset") or "").upper() not in sub["assets"]:
        return False
    if sub["venues"] and (event.get("venue") or "") not in sub["venues"]:
        return False
    if sub["severities"] and event.get("severity") not in sub["severities"]:
        return False
    return True


def _parse_subscribe(raw: str) -> Optional[dict[str, Any]]:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("action") != "subscribe":
        return None

    def _list(key: str) -> list[str]:
        v = msg.get(key)
        if isinstance(v, list):
            return [str(x).upper() if key == "assets" else str(x) for x in v]
        return []

    return {
        "assets": _list("assets"),
        "venues": _list("venues"),
        "event_types": _list("event_types"),
        "severities": _list("severities"),
        "last_event_id": msg.get("last_event_id"),
    }


@router.websocket("/stream")
async def stream(ws: WebSocket) -> None:
    # accept first so auth failures can carry a real WS close code (close
    # before accept is downgraded to a plain HTTP 403 by the server)
    await ws.accept()
    api_key = ws.headers.get("x-api-key") or ws.query_params.get("api_key")
    consumer = None
    if authenticate is not None:
        try:
            consumer = await authenticate(api_key)
        except Exception as exc:
            log.warning("stream auth error: %s", exc)
            consumer = None
    if consumer is None:
        await ws.close(code=CLOSE_UNAUTHORIZED)
        return
    scopes = set(getattr(consumer, "scopes", []) or [])
    if "stream" not in scopes:
        await ws.close(code=CLOSE_UNAUTHORIZED)
        return

    bus: EventBus = get_event_bus()
    queue = bus.subscribe()
    subscription_id = str(ulid.new())
    try:
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=SUBSCRIBE_TIMEOUT_SEC)
        except (asyncio.TimeoutError, WebSocketDisconnect):
            await ws.close(code=CLOSE_BAD_SUBSCRIBE)
            return
        sub = _parse_subscribe(raw)
        if sub is None:
            await ws.close(code=CLOSE_BAD_SUBSCRIBE)
            return

        last_event_id = sub["last_event_id"]
        await ws.send_json(
            {
                "kind": "subscribed",
                "subscription_id": subscription_id,
                "replay_from": last_event_id,
            }
        )

        # gap recovery: replay durable events after last_event_id, oldest-first
        if last_event_id:
            missed = await bus.replay(
                since_id=last_event_id,
                limit=500,
                event_types=sub["event_types"] or None,
                asset=None,
                severities=sub["severities"] or None,
            )
            for event in reversed(missed):  # replay() is newest-first
                if not _matches(event, sub):
                    continue
                await ws.send_json({"kind": "event", "event": event})

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SEC)
            except asyncio.TimeoutError:
                await ws.send_json({"kind": "heartbeat", "ts": time.time()})
                continue
            if _matches(event, sub):
                await ws.send_json({"kind": "event", "event": event})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.info("stream %s closed: %s", subscription_id, exc)
    finally:
        bus.unsubscribe(queue)
