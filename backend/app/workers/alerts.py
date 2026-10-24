"""Alert store + evaluator loop.

In-memory authoritative store with best-effort write-through persistence to
Postgres when available (alerts keep working without a DB). The evaluator
polls cached/live metrics every few seconds, applies per-rule cooldown +
dedupe, and emits AlertEvents to the store and the websocket broadcast.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core import db as core_db
from app.core.cache import get_cache
from app.core.state import get_live_state
from app.services import iso

log = logging.getLogger(__name__)

EVAL_INTERVAL_SEC = 5


def _now_iso() -> str:
    return iso()


class AlertStore:
    """CRUD for alert rules and events. Memory-first, DB write-through."""

    def __init__(self, max_events: int = 500) -> None:
        self._rules: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._runtime: dict[str, dict[str, Any]] = {}  # per-rule runtime state
        self._max_events = max_events
        self._lock = asyncio.Lock()
        self._loaded_from_db = False

    # -- CRUD ---------------------------------------------------------------
    async def create_rule(
        self,
        type: str,
        symbol: str | None,
        params: dict[str, Any],
        severity: str = "info",
        cooldown_sec: int = 300,
        user_key: str = "anon",
    ) -> dict[str, Any]:
        rule = {
            "id": uuid.uuid4().hex,
            "user_key": user_key,
            "type": type,
            "symbol": symbol.upper() if symbol else None,
            "params": params or {},
            "severity": severity,
            "cooldown_sec": int(cooldown_sec or 300),
            "active": True,
            "created_at": _now_iso(),
        }
        async with self._lock:
            self._rules[rule["id"]] = rule
            self._runtime[rule["id"]] = {"last_fired": 0.0, "prev": {}, "seen_news": []}
        await self._persist_rule(rule)
        return rule

    async def list_rules(self) -> list[dict[str, Any]]:
        async with self._lock:
            return sorted(self._rules.values(), key=lambda r: r["created_at"], reverse=True)

    async def delete_rule(self, rule_id: str) -> bool:
        async with self._lock:
            existed = self._rules.pop(rule_id, None) is not None
            self._runtime.pop(rule_id, None)
        if existed:
            await self._delete_rule_db(rule_id)
        return existed

    async def list_events(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._events[:limit])

    async def add_event(
        self,
        *,
        rule_id: str | None,
        type: str,
        symbol: str | None,
        severity: str,
        message: str,
    ) -> dict[str, Any]:
        event = {
            "id": uuid.uuid4().hex,
            "rule_id": rule_id,
            "type": type,
            "symbol": symbol.upper() if symbol else None,
            "severity": severity,
            "message": message,
            "triggered_at": _now_iso(),
            "acknowledged": False,
        }
        async with self._lock:
            self._events.insert(0, event)
            del self._events[self._max_events :]
        await self._persist_event(event)
        get_live_state().broadcast({"topic": "alert", "data": event})
        return event

    # -- persistence (best-effort) -------------------------------------------
    async def load_from_db(self) -> None:
        if self._loaded_from_db or not core_db.db_available():
            return
        self._loaded_from_db = True
        try:
            from sqlalchemy import select

            from app.models import AlertRuleRow

            async with core_db.session() as session:
                if session is None:
                    return
                rows = (await session.execute(select(AlertRuleRow))).scalars().all()
                async with self._lock:
                    for row in rows:
                        rid = str(row.id).replace("-", "")
                        if rid in self._rules:
                            continue
                        self._rules[rid] = {
                            "id": rid,
                            "user_key": row.user_key,
                            "type": row.type,
                            "symbol": row.symbol,
                            "params": dict(row.params or {}),
                            "severity": row.severity,
                            "cooldown_sec": row.cooldown_sec,
                            "active": row.active,
                            "created_at": row.created_at.isoformat().replace("+00:00", "Z")
                            if row.created_at
                            else _now_iso(),
                        }
                        self._runtime.setdefault(
                            rid, {"last_fired": 0.0, "prev": {}, "seen_news": []}
                        )
            log.info("loaded %d alert rules from db", len(rows))
        except Exception as exc:
            log.info("alert rule load from db skipped: %s", exc)

    async def _persist_rule(self, rule: dict[str, Any]) -> None:
        if not core_db.db_available():
            return
        try:
            from app.models import AlertRuleRow

            async with core_db.session() as session:
                if session is None:
                    return
                session.add(
                    AlertRuleRow(
                        id=uuid.UUID(rule["id"]) if len(rule["id"]) == 32 else uuid.uuid4(),
                        user_key=rule["user_key"],
                        type=rule["type"],
                        symbol=rule["symbol"],
                        params=rule["params"],
                        severity=rule["severity"],
                        cooldown_sec=rule["cooldown_sec"],
                        active=rule["active"],
                    )
                )
                await session.commit()
        except Exception as exc:
            log.info("alert rule persistence skipped: %s", exc)

    async def _persist_event(self, event: dict[str, Any]) -> None:
        if not core_db.db_available():
            return
        try:
            from app.models import AlertEventRow

            async with core_db.session() as session:
                if session is None:
                    return
                rule_uuid = None
                if event.get("rule_id") and len(event["rule_id"]) == 32:
                    rule_uuid = uuid.UUID(event["rule_id"])
                session.add(
                    AlertEventRow(
                        id=uuid.UUID(event["id"]),
                        rule_id=rule_uuid,
                        type=event["type"],
                        symbol=event["symbol"],
                        severity=event["severity"],
                        message=event["message"],
                    )
                )
                await session.commit()
        except Exception as exc:
            log.info("alert event persistence skipped: %s", exc)

    async def _delete_rule_db(self, rule_id: str) -> None:
        if not core_db.db_available() or len(rule_id) != 32:
            return
        try:
            from sqlalchemy import delete

            from app.models import AlertRuleRow

            async with core_db.session() as session:
                if session is None:
                    return
                await session.execute(
                    delete(AlertRuleRow).where(AlertRuleRow.id == uuid.UUID(rule_id))
                )
                await session.commit()
        except Exception as exc:
            log.info("alert rule db delete skipped: %s", exc)


_store = AlertStore()


def get_alert_store() -> AlertStore:
    return _store


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


async def _current_price(symbol: str) -> Optional[float]:
    state = get_live_state()
    for exch in ("binance", "bybit"):
        live = state.get_price(exch, symbol)
        if live and time.time() - live.get("ts", 0) < 120:
            return float(live["price"])
    cache = get_cache()
    entry = await cache.get_entry(f"bn:ticker:spot:{symbol.upper()}USDT")
    if entry and isinstance(entry.value, dict):
        try:
            return float(entry.value.get("lastPrice"))
        except (TypeError, ValueError):
            return None
    return None


async def _deriv_snapshot(symbol: str) -> dict[str, Any]:
    entry = await get_cache().get_entry(f"deriv:{symbol.upper()}")
    return entry.value if entry and isinstance(entry.value, dict) else {}


async def _spread_bps(symbol: str) -> Optional[float]:
    state = get_live_state()
    a = state.get_price("binance", symbol)
    b = state.get_price("bybit", symbol)
    if not a or not b:
        return None
    pa, pb = float(a["price"]), float(b["price"])
    mid = (pa + pb) / 2
    if mid <= 0:
        return None
    return abs(pa - pb) / mid * 10_000


async def _book_imbalance(symbol: str) -> Optional[float]:
    from app.engines.liquidity import depth_imbalance

    state = get_live_state()
    for exch in ("binance", "bybit"):
        snap = state.latest_depth(exch, symbol)
        if snap:
            _, bids, asks = snap
            return depth_imbalance(bids, asks)
    return None


async def evaluate_rule(rule: dict[str, Any], runtime: dict[str, Any]) -> Optional[str]:
    """Return an event message when the rule fires, else None.

    Evaluates against cached/live metrics only — never fabricates.
    """
    rtype = rule["type"]
    params = rule.get("params") or {}
    symbol = rule.get("symbol")

    if rtype == "price_cross":
        if not symbol:
            return None
        price = await _current_price(symbol)
        target = params.get("price")
        direction = params.get("direction", "above")
        if price is None or target is None:
            return None
        prev = runtime["prev"].get("price")
        runtime["prev"]["price"] = price
        if prev is None:
            return None  # need a previous reading to detect a cross
        target = float(target)
        if direction == "above" and prev <= target < price:
            return f"{symbol} crossed above {target:g} (now {price:g})"
        if direction == "below" and prev >= target > price:
            return f"{symbol} crossed below {target:g} (now {price:g})"
        return None

    if rtype in ("liquidity_zone", "liquidity_sweep"):
        if not symbol:
            return None
        price = await _current_price(symbol)
        lo, hi = params.get("price_low"), params.get("price_high")
        if price is None or lo is None or hi is None:
            return None
        lo, hi = float(lo), float(hi)
        in_zone = lo <= price <= hi
        was_in_zone = runtime["prev"].get("in_zone", False)
        runtime["prev"]["in_zone"] = in_zone
        if rtype == "liquidity_zone" and in_zone and not was_in_zone:
            return f"{symbol} entered liquidity zone {lo:g}–{hi:g} (approximation from cached/live prices)"
        if rtype == "liquidity_sweep" and was_in_zone and not in_zone:
            return f"{symbol} left liquidity zone {lo:g}–{hi:g} (sweep approximation from cached/live prices)"
        return None

    if rtype == "oi_spike":
        if not symbol:
            return None
        snap = await _deriv_snapshot(symbol)
        oi = snap.get("binance_oi") or snap.get("bybit_oi")
        if oi is None:
            return None
        prev = runtime["prev"].get("oi")
        runtime["prev"]["oi"] = oi
        if prev in (None, 0):
            return None
        change_pct = (oi - prev) / prev * 100
        threshold = float(params.get("change_pct", 5))
        if abs(change_pct) >= threshold:
            return f"{symbol} open interest moved {change_pct:+.1f}% between polls (>= {threshold:g}%)"
        return None

    if rtype == "funding_extreme":
        if not symbol:
            return None
        snap = await _deriv_snapshot(symbol)
        funding = snap.get("binance_funding")
        if funding is None:
            funding = snap.get("bybit_funding")
        if funding is None:
            return None
        threshold = float(params.get("threshold", 0.0005))
        if abs(funding) >= threshold:
            return f"{symbol} funding {funding:+.5f} exceeds ±{threshold:g}"
        return None

    if rtype == "volume_spike":
        if not symbol:
            return None
        cache = get_cache()
        entry = await cache.get_entry(f"bn:ticker:spot:{symbol.upper()}USDT")
        if not entry or not isinstance(entry.value, dict):
            return None
        try:
            vol = float(entry.value.get("quoteVolume"))
        except (TypeError, ValueError):
            return None
        prev = runtime["prev"].get("volume")
        runtime["prev"]["volume"] = vol
        if prev in (None, 0):
            return None
        multiple = float(params.get("multiple", 2))
        if vol >= prev * multiple:
            return f"{symbol} 24h quote volume spiked {vol / prev:.1f}x between polls (approximation)"
        return None

    if rtype == "book_imbalance":
        if not symbol:
            return None
        imb = await _book_imbalance(symbol)
        if imb is None:
            return None
        threshold = float(params.get("threshold", 0.5))
        if abs(imb) >= threshold:
            side = "bid" if imb > 0 else "ask"
            return f"{symbol} top-of-book imbalance {imb:+.2f} ({side}-heavy, >= {threshold:g})"
        return None

    if rtype == "cross_exchange_divergence":
        if not symbol:
            return None
        spread = await _spread_bps(symbol)
        if spread is None:
            return None
        threshold = float(params.get("threshold_bps", 15))
        if spread >= threshold:
            return f"{symbol} binance/bybit spread {spread:.1f} bps >= {threshold:g} bps"
        return None

    if rtype == "breaking_news":
        from app.services.news import get_aggregator

        min_importance = int(params.get("min_importance", 5))
        seen = set(runtime.get("seen_news") or [])
        agg = get_aggregator()
        items = agg._items if not symbol else [i for i in agg._items if symbol.upper() in i["assets"]]
        new_seen = list(seen)
        messages = []
        for item in items:
            iid = agg._item_id(item)
            if iid in seen:
                continue
            new_seen.append(iid)
            if item["importance"] >= min_importance:
                messages.append(f"Breaking: {item['headline'][:140]}")
        runtime["seen_news"] = new_seen[-200:]
        return messages[0] if messages else None

    if rtype == "trend_change":
        if not symbol:
            return None
        cache = get_cache()
        change = None
        # approximate trend via cached 24h change sign from markets cache
        for key in (f"bn:ticker:spot:{symbol.upper()}USDT",):
            e = await cache.get_entry(key)
            if e and isinstance(e.value, dict):
                try:
                    change = float(e.value.get("priceChangePercent"))
                except (TypeError, ValueError):
                    change = None
        if change is None:
            return None
        sign = 1 if change > 0 else (-1 if change < 0 else 0)
        prev_sign = runtime["prev"].get("trend_sign")
        runtime["prev"]["trend_sign"] = sign
        if prev_sign is None or sign == 0 or prev_sign == 0:
            return None
        if sign != prev_sign:
            return f"{symbol} 24h trend flipped {'up' if sign > 0 else 'down'} ({change:+.2f}%)"
        return None

    if rtype == "liquidation_burst":
        state = get_live_state()
        if not symbol:
            return None
        since = time.time() - 300
        liqs = state.recent_trades("binance_perp_liq", symbol, since) + state.recent_trades(
            "bybit_perp_liq", symbol, since
        )
        total = sum(float(t.get("size_usd") or 0) for t in liqs)
        threshold = float(params.get("min_usd", 1_000_000))
        if total >= threshold:
            return f"{symbol} liquidations ~${total:,.0f} in last 5m (observed via exchange streams)"
        return None

    return None


async def evaluate_once() -> int:
    """One evaluation pass over all active rules. Returns events emitted."""
    store = get_alert_store()
    rules = await store.list_rules()
    fired = 0
    now = time.time()
    for rule in rules:
        if not rule.get("active"):
            continue
        runtime = store._runtime.setdefault(
            rule["id"], {"last_fired": 0.0, "prev": {}, "seen_news": []}
        )
        if now - runtime["last_fired"] < rule.get("cooldown_sec", 300):
            continue  # cooldown + dedupe
        try:
            message = await evaluate_rule(rule, runtime)
        except Exception as exc:
            log.info("alert rule %s evaluation failed: %s", rule["id"], exc)
            continue
        if message:
            runtime["last_fired"] = now
            await store.add_event(
                rule_id=rule["id"],
                type=rule["type"],
                symbol=rule.get("symbol"),
                severity=rule.get("severity", "info"),
                message=message,
            )
            fired += 1
    return fired


async def evaluator_loop() -> None:
    await get_alert_store().load_from_db()
    while True:
        try:
            await evaluate_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.info("alert evaluator pass failed: %s", exc)
        await asyncio.sleep(EVAL_INTERVAL_SEC)
