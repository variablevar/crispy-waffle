"""System routes: /health and the realtime fan-out WebSocket /ws."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import db as core_db
from app.core.cache import get_cache
from app.core.state import get_live_state
from app.services import all_source_status

log = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

_STARTED_AT = time.time()


@router.get("/health")
async def health() -> dict[str, Any]:
    state = get_live_state()
    cache = get_cache()
    cg = all_source_status().get("coingecko")
    coingecko_ok = bool(cg and cg.last_success and not cg.error)
    services = {
        "redis": bool(getattr(cache, "is_redis", False)),
        "database": core_db.db_available(),
        "binance_ws": state.ws_health.get("binance", False),
        "bybit_ws": state.ws_health.get("bybit", False),
        "coingecko": coingecko_ok,
    }
    degraded = not (services["redis"] and services["database"])
    return {
        "status": "degraded" if degraded else "ok",
        "services": services,
        "uptime_sec": round(time.time() - _STARTED_AT, 1),
    }


@router.websocket("/ws")
async def ws_fanout(websocket: WebSocket) -> None:
    """Push live price ticks, alert events and news to clients.

    Optional channel: the frontend falls back to polling when this is absent.
    """
    await websocket.accept()
    state = get_live_state()
    queue = state.subscribe()
    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=25.0)
                await websocket.send_json(message)
            except asyncio.TimeoutError:
                await websocket.send_json({"topic": "heartbeat", "data": {"ts": time.time()}})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - network dependent
        log.info("ws client disconnected: %s", exc)
    finally:
        state.unsubscribe(queue)
