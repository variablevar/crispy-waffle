"""Alert routes: rule CRUD and event history.

Backed by the AlertStore (in-memory with best-effort DB persistence), so the
API stays fully functional without Postgres.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import AlertCreate
from app.workers.alerts import get_alert_store

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", status_code=201)
async def create_alert(body: AlertCreate) -> dict[str, Any]:
    store = get_alert_store()
    await store.load_from_db()
    return await store.create_rule(
        type=body.type,
        symbol=body.symbol,
        params=body.params,
        severity=body.severity,
        cooldown_sec=body.cooldown_sec,
    )


@router.get("")
async def list_alerts() -> dict[str, Any]:
    store = get_alert_store()
    await store.load_from_db()
    rules = await store.list_rules()
    return {"items": rules, "meta": {"source": ["alert_store"], "updated_at": None, "stale": False, "available": True}}


@router.delete("/{rule_id}")
async def delete_alert(rule_id: str) -> dict[str, Any]:
    store = get_alert_store()
    deleted = await store.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="alert rule not found")
    return {"deleted": True}


@router.get("/events")
async def list_alert_events(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    store = get_alert_store()
    events = await store.list_events(limit=limit)
    return {"items": events, "meta": {"source": ["alert_store"], "updated_at": None, "stale": False, "available": True}}
