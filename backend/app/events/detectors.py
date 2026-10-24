"""Detection layer: derives contract AgentEvents from OBSERVED data only.

Inputs: LiveState (live prices/trades/depth/ws-health), poller derivatives
cache (`deriv:{SYM}` snapshots with funding / OI / long-short), the news
aggregator, and the scenario engine. Detectors never fabricate: with no fresh
observed input a detector simply does not fire. DATA_STALE / DATA_RECOVERED
are the exception — they report feed health itself.

Every detector dedupes via an idempotency key plus a per-key cooldown.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.state import LiveState, get_live_state
from app.engines import liquidity as liq_engine
from app.engines import pressure as pressure_engine
from app.engines import scenarios_v2
from app.events.bus import EventBus, get_event_bus
from app.events.model import make_event

log = logging.getLogger(__name__)

SOURCE_PREFIX = "skybus://detectors"

# --- thresholds (module-level so tests/tuning can override) -------------------
FUNDING_EXTREME = 0.0005  # |funding| >= 0.05% per 8h
FUNDING_CRITICAL = 0.001  # |funding| >= 0.10% per 8h
OI_SPIKE_PCT = 3.0  # 1h OI change % threshold
OI_SPIKE_CRITICAL_PCT = 10.0
OI_WINDOW_SEC = 3600
OI_MIN_HISTORY_SEC = 1800  # need at least this much history to compare
CVD_LOOKBACK_TRADES = 400
CVD_MIN_PRICE_MOVE_PCT = 0.3
CROSS_SPREAD_BPS = 10.0
CROSS_SPREAD_CRITICAL_BPS = 50.0
CROSS_SUSTAIN_SEC = 30.0
ZONE_APPROACH_BPS = 25.0
SWEEP_TOLERANCE_BPS = 15.0
LIQ_BURST_USD = 250_000.0
LIQ_BURST_WINDOW_SEC = 60
NEWS_MIN_IMPORTANCE = 4
NEWS_MAX_AGE_SEC = 900
PRICE_FRESH_SEC = 120

DEDUPE_TTL_SEC = 24 * 3600
DEFAULT_COOLDOWN_SEC = 300
ZONE_COOLDOWN_SEC = 900

FUNDING_BUCKET_SEC = 3600  # funding rate bucket for idempotency keys


def _bucket(now: float, span: int) -> int:
    return int(now // span)


def _trade_ts_sec(t: dict[str, Any]) -> float:
    ts = float(t.get("time", 0) or 0)
    return ts / 1000.0 if ts > 1e12 else ts


class DetectorEngine:
    """Runs all detectors against injected inputs. Tests instantiate their own
    engine with a fresh LiveState / bus / aggregator; production uses the
    module singleton wired to the shared globals."""

    def __init__(
        self,
        *,
        bus: Optional[EventBus] = None,
        state: Optional[LiveState] = None,
        aggregator: Any = None,
    ) -> None:
        self._bus = bus
        self._state = state
        self._aggregator = aggregator
        self._dedupe: dict[str, float] = {}  # idempotency key -> expiry ts
        self._cooldowns: dict[str, float] = {}  # cooldown key -> last fire ts
        self._prev_prices: dict[str, float] = {}
        self._oi_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self._cross_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self._last_scenarios: dict[str, dict[str, str]] = {}  # sym -> {type: scenario_id}
        self._last_regime: dict[str, str] = {}
        self._ws_health_prev: Optional[dict[str, bool]] = None

    # -- injected defaults ------------------------------------------------------
    @property
    def bus(self) -> EventBus:
        if self._bus is None:
            self._bus = get_event_bus()
        return self._bus

    @property
    def state(self) -> LiveState:
        if self._state is None:
            self._state = get_live_state()
        return self._state

    @property
    def aggregator(self) -> Any:
        if self._aggregator is None:
            from app.services.news import get_aggregator

            self._aggregator = get_aggregator()
        return self._aggregator

    # -- dedupe / cooldown -------------------------------------------------------
    def _seen(self, key: str, now: float, ttl: float = DEDUPE_TTL_SEC) -> bool:
        self._dedupe = {k: v for k, v in self._dedupe.items() if v > now}
        if key in self._dedupe:
            return True
        self._dedupe[key] = now + ttl
        return False

    def _cooling(self, key: str, now: float, cooldown: float = DEFAULT_COOLDOWN_SEC) -> bool:
        last = self._cooldowns.get(key)
        if last is not None and now - last < cooldown:
            return True
        self._cooldowns[key] = now
        return False

    # -- main entry ---------------------------------------------------------------
    async def run_once(
        self, symbols: list[str], now: Optional[float] = None
    ) -> list[dict[str, Any]]:
        """Run every detector once over `symbols`; returns published events."""
        now = now if now is not None else time.time()
        pending: list[dict[str, Any]] = []
        pending.extend(self._detect_ws_health(now))
        for sym in symbols:
            deriv = await self._deriv_snapshot(sym)
            pending.extend(self._detect_funding(sym, deriv, now))
            pending.extend(self._detect_oi_spike(sym, deriv, now))
            pending.extend(self._detect_cvd_divergence(sym, now))
            pending.extend(self._detect_cross_exchange(sym, now))
            pending.extend(self._detect_zones(sym, now))
            pending.extend(self._detect_liquidation_bursts(sym, now))
            pending.extend(self._detect_news(sym, now))
            market_state = self._market_state(sym, deriv, now)
            pending.extend(self._detect_scenario_diff(sym, market_state, now))
            pending.extend(self._detect_regime_change(sym, market_state, now))
        published: list[dict[str, Any]] = []
        for event in pending:
            try:
                await self.bus.publish(event)
                published.append(event)
            except Exception as exc:  # bus must never take detectors down
                log.warning("event publish failed: %s", exc)
        return published

    async def _deriv_snapshot(self, sym: str) -> Optional[dict[str, Any]]:
        try:
            entry = await get_cache().get_entry(f"deriv:{sym.upper()}")
            if entry is not None and isinstance(entry.value, dict):
                return entry.value
        except Exception as exc:
            log.info("deriv cache read failed for %s: %s", sym, exc)
        return None

    # -- funding -------------------------------------------------------------------
    def _detect_funding(self, sym: str, deriv: Optional[dict], now: float) -> list[dict]:
        if not deriv:
            return []
        out = []
        for venue, key in (("binance", "binance_funding"), ("bybit", "bybit_funding")):
            funding = deriv.get(key)
            if funding is None or abs(funding) < FUNDING_EXTREME:
                continue
            idem = f"funding:{venue}:{sym}:{_bucket(now, FUNDING_BUCKET_SEC)}"
            if self._seen(idem, now):
                continue
            side = "longs paying shorts" if funding > 0 else "shorts paying longs"
            severity = "critical" if abs(funding) >= FUNDING_CRITICAL else "warning"
            out.append(
                make_event(
                    type="FUNDING_EXTREME",
                    source=f"{SOURCE_PREFIX}/funding",
                    asset=sym,
                    venue=venue,
                    instrument="usdt_perp",
                    severity=severity,
                    summary=(
                        f"{sym} {venue} funding {funding * 100:.4f}%/8h — extreme, {side}"
                    ),
                    evidence=[
                        {
                            "indicator": "funding_rate",
                            "value": f"{funding:.6f}",
                            "supports": True,
                        }
                    ],
                    observed={"funding_rate": funding, "fetched_at": deriv.get("fetched_at")},
                    idempotency_key=idem,
                )
            )
        return out

    # -- open interest ---------------------------------------------------------------
    def _detect_oi_spike(self, sym: str, deriv: Optional[dict], now: float) -> list[dict]:
        if not deriv:
            return []
        oi = deriv.get("binance_oi") or deriv.get("bybit_oi")
        if oi is None:
            return []
        hist = self._oi_history[sym]
        hist.append((now, float(oi)))
        old = [(ts, v) for ts, v in hist if ts <= now - OI_MIN_HISTORY_SEC]
        if not old:
            return []
        ref_ts, ref_oi = old[-1]
        if ref_oi <= 0:
            return []
        change_pct = (float(oi) - ref_oi) / ref_oi * 100.0
        if abs(change_pct) < OI_SPIKE_PCT:
            return []
        idem = f"oi:{sym}:{_bucket(now, OI_WINDOW_SEC)}"
        if self._seen(idem, now):
            return []
        direction = "up" if change_pct > 0 else "down"
        severity = "critical" if abs(change_pct) >= OI_SPIKE_CRITICAL_PCT else "warning"
        return [
            make_event(
                type="OPEN_INTEREST_SPIKE",
                source=f"{SOURCE_PREFIX}/open_interest",
                asset=sym,
                instrument="usdt_perp",
                severity=severity,
                summary=f"{sym} open interest {direction} {abs(change_pct):.1f}% over ~1h",
                evidence=[
                    {
                        "indicator": "oi_change_pct_1h",
                        "value": f"{change_pct:.2f}%",
                        "supports": True,
                    }
                ],
                observed={
                    "open_interest": float(oi),
                    "reference_open_interest": ref_oi,
                    "reference_age_sec": round(now - ref_ts, 1),
                },
                idempotency_key=idem,
            )
        ]

    # -- CVD divergence ---------------------------------------------------------------
    def _detect_cvd_divergence(self, sym: str, now: float) -> list[dict]:
        trades = self.state.recent_trades("binance", sym)[-CVD_LOOKBACK_TRADES:]
        if len(trades) < 50:
            return []
        cvd = pressure_engine.compute_cvd(trades, bucket_sec=60)
        if len(cvd) < 4:
            return []
        first_price = float(trades[0].get("price", 0) or 0)
        last_price = float(trades[-1].get("price", 0) or 0)
        if first_price <= 0 or last_price <= 0:
            return []
        price_move_pct = (last_price - first_price) / first_price * 100.0
        cvd_delta = cvd[-1]["value"] - cvd[-4]["value"]
        direction = None
        if price_move_pct >= CVD_MIN_PRICE_MOVE_PCT and cvd_delta < 0:
            direction = "bearish"  # price up, CVD down
        elif price_move_pct <= -CVD_MIN_PRICE_MOVE_PCT and cvd_delta > 0:
            direction = "bullish"  # price down, CVD up
        if direction is None:
            return []
        idem = f"cvd:{sym}:{direction}:{_bucket(now, 900)}"
        if self._seen(idem, now):
            return []
        return [
            make_event(
                type="CVD_DIVERGENCE",
                source=f"{SOURCE_PREFIX}/cvd",
                asset=sym,
                venue="binance",
                instrument="spot",
                severity="warning",
                summary=(
                    f"{sym} {direction} CVD divergence: price {price_move_pct:+.2f}% "
                    f"while CVD moved {cvd_delta:+.0f} quote"
                ),
                evidence=[
                    {
                        "indicator": "price_move_pct",
                        "value": f"{price_move_pct:.3f}%",
                        "supports": True,
                    },
                    {"indicator": "cvd_delta", "value": f"{cvd_delta:.2f}", "supports": True},
                ],
                observed={
                    "price_first": first_price,
                    "price_last": last_price,
                    "cvd_delta": cvd_delta,
                    "n_trades": len(trades),
                },
                idempotency_key=idem,
            )
        ]

    # -- cross-exchange divergence ------------------------------------------------------
    def _detect_cross_exchange(self, sym: str, now: float) -> list[dict]:
        pa = self.state.get_price("binance", sym)
        pb = self.state.get_price("bybit", sym)
        if not pa or not pb:
            return []
        if now - pa["ts"] > PRICE_FRESH_SEC or now - pb["ts"] > PRICE_FRESH_SEC:
            return []
        a, b = float(pa["price"]), float(pb["price"])
        if a <= 0 or b <= 0:
            return []
        mid = (a + b) / 2.0
        spread_bps = (a - b) / mid * 1e4
        hist = self._cross_history[sym]
        if abs(spread_bps) >= CROSS_SPREAD_BPS:
            hist.append((now, spread_bps))
        else:
            hist.clear()
            return []
        first_ts = hist[0][0]
        sustained = now - first_ts >= CROSS_SUSTAIN_SEC and all(
            abs(s) >= CROSS_SPREAD_BPS for _, s in hist
        )
        if not sustained:
            return []
        direction = "binance_premium" if spread_bps > 0 else "bybit_premium"
        idem = f"xspread:{sym}:{direction}:{_bucket(now, 1800)}"
        if self._seen(idem, now):
            return []
        severity = "critical" if abs(spread_bps) >= CROSS_SPREAD_CRITICAL_BPS else "warning"
        return [
            make_event(
                type="CROSS_EXCHANGE_DIVERGENCE",
                source=f"{SOURCE_PREFIX}/cross_exchange",
                asset=sym,
                severity=severity,
                summary=(
                    f"{sym} binance/bybit spread {spread_bps:+.1f} bps sustained "
                    f"{now - first_ts:.0f}s ({direction})"
                ),
                evidence=[
                    {"indicator": "spread_bps", "value": f"{spread_bps:.2f}", "supports": True}
                ],
                observed={
                    "binance_price": a,
                    "bybit_price": b,
                    "spread_bps": round(spread_bps, 3),
                    "sustained_sec": round(now - first_ts, 1),
                },
                idempotency_key=idem,
            )
        ]

    # -- liquidity zones / price levels -------------------------------------------------
    def _zones_for(self, venue: str, sym: str, mid: float) -> list[dict[str, Any]]:
        snap = self.state.latest_depth(venue, sym)
        if not snap or mid <= 0:
            return []
        _, bids, asks = snap
        walls = liq_engine.detect_walls(bids, asks, venue)
        zones = liq_engine.wall_zones(walls, mid)
        zones.extend(liq_engine.support_resistance_estimates(bids, asks, mid, walls))
        return zones

    def _detect_zones(self, sym: str, now: float) -> list[dict]:
        out: list[dict[str, Any]] = []
        for venue in ("binance", "bybit"):
            p = self.state.get_price(venue, sym)
            if not p or now - p["ts"] > PRICE_FRESH_SEC:
                continue
            price = float(p["price"])
            zones = self._zones_for(venue, sym, price)
            if not zones:
                continue
            key = f"{venue}:{sym}"
            prev = self._prev_prices.get(key)
            self._prev_prices[key] = price
            for zone in zones:
                lo, hi = float(zone["price_low"]), float(zone["price_high"])
                label = zone.get("label", zone.get("type", "zone"))
                if prev is not None and prev != price:
                    crossed_both = (prev < lo and price > hi) or (prev > hi and price < lo)
                    crossed_edge = (prev - lo) * (price - lo) < 0 or (prev - hi) * (
                        price - hi
                    ) < 0
                    if crossed_both:
                        direction = "up" if price > prev else "down"
                        idem = f"zonebreach:{venue}:{sym}:{label}:{direction}:{_bucket(now, 3600)}"
                        if not self._seen(idem, now):
                            out.append(
                                make_event(
                                    type="LIQUIDITY_ZONE_BREACHED",
                                    source=f"{SOURCE_PREFIX}/liquidity",
                                    asset=sym,
                                    venue=venue,
                                    severity="warning",
                                    summary=f"{sym} {venue} price swept through {label} [{lo}, {hi}]",
                                    evidence=[
                                        {
                                            "indicator": "zone",
                                            "value": f"{label} [{lo}, {hi}]",
                                            "supports": True,
                                        }
                                    ],
                                    observed={
                                        "prev_price": prev,
                                        "price": price,
                                        "zone_low": lo,
                                        "zone_high": hi,
                                    },
                                    idempotency_key=idem,
                                )
                            )
                    elif crossed_edge:
                        edge = lo if (prev - lo) * (price - lo) < 0 else hi
                        direction = "up" if price > prev else "down"
                        idem = f"levelcross:{venue}:{sym}:{edge}:{direction}:{_bucket(now, 3600)}"
                        if not self._seen(idem, now):
                            out.append(
                                make_event(
                                    type="PRICE_LEVEL_CROSSED",
                                    source=f"{SOURCE_PREFIX}/price_levels",
                                    asset=sym,
                                    venue=venue,
                                    severity="info",
                                    summary=f"{sym} {venue} crossed {edge} ({label}) {direction}",
                                    evidence=[
                                        {
                                            "indicator": "level",
                                            "value": f"{edge} ({label})",
                                            "supports": True,
                                        }
                                    ],
                                    observed={"prev_price": prev, "price": price, "level": edge},
                                    idempotency_key=idem,
                                )
                            )
                # approach: outside the zone but within tolerance
                if price < lo:
                    dist_bps = (lo - price) / price * 1e4
                elif price > hi:
                    dist_bps = (price - hi) / price * 1e4
                else:
                    dist_bps = 0.0
                if price < lo or price > hi:
                    if dist_bps <= ZONE_APPROACH_BPS:
                        idem = f"zoneapproach:{venue}:{sym}:{label}:{_bucket(now, ZONE_COOLDOWN_SEC)}"
                        if not self._seen(idem, now) and not self._cooling(
                            f"zoneapproach:{venue}:{sym}", now, ZONE_COOLDOWN_SEC
                        ):
                            out.append(
                                make_event(
                                    type="LIQUIDITY_ZONE_APPROACH",
                                    source=f"{SOURCE_PREFIX}/liquidity",
                                    asset=sym,
                                    venue=venue,
                                    severity="info",
                                    summary=f"{sym} {venue} price within {dist_bps:.0f} bps of {label}",
                                    evidence=[
                                        {
                                            "indicator": "distance_bps",
                                            "value": f"{dist_bps:.1f}",
                                            "supports": True,
                                        }
                                    ],
                                    observed={"price": price, "zone_low": lo, "zone_high": hi},
                                    idempotency_key=idem,
                                )
                            )
            # sweep detection from recent trade price path
            trades = self.state.recent_trades(venue, sym)[-300:]
            series = [(_trade_ts_sec(t), float(t.get("price", 0) or 0)) for t in trades]
            series = [(ts, px) for ts, px in series if px > 0]
            if len(series) >= 5:
                for sweep in liq_engine.detect_sweep(series, zones, SWEEP_TOLERANCE_BPS):
                    idem = f"sweep:{venue}:{sym}:{sweep['direction']}:{_bucket(int(sweep['time']), 3600)}"
                    if self._seen(idem, now):
                        continue
                    out.append(
                        make_event(
                            type="LIQUIDITY_SWEEP_DETECTED",
                            source=f"{SOURCE_PREFIX}/liquidity",
                            asset=sym,
                            venue=venue,
                            severity="warning",
                            summary=(
                                f"{sym} {venue} liquidity sweep {sweep['direction']} through "
                                f"{sweep['zone'].get('label', 'zone')} — price reclaimed"
                            ),
                            evidence=[
                                {
                                    "indicator": "sweep",
                                    "value": f"{sweep['direction']} @ {sweep['price']}",
                                    "supports": True,
                                }
                            ],
                            observed={"sweep_price": sweep["price"], "direction": sweep["direction"]},
                            estimated={"zone": sweep["zone"].get("label")},
                            idempotency_key=idem,
                            event_time=sweep["time"],
                        )
                    )
        return out

    # -- liquidation bursts ---------------------------------------------------------------
    def _detect_liquidation_bursts(self, sym: str, now: float) -> list[dict]:
        out: list[dict[str, Any]] = []
        since_ms = (now - LIQ_BURST_WINDOW_SEC) * 1000
        longs = shorts = 0.0
        found = False
        for feed in ("binance_perp_liq", "bybit_perp_liq"):
            venue = feed.split("_")[0]
            for t in self.state.recent_trades(feed, sym, since=since_ms):
                found = True
                size = float(t.get("size_usd", 0) or 0)
                if t.get("side") == "long_liquidated":
                    longs += size
                elif t.get("side") == "short_liquidated":
                    shorts += size
        if not found:
            return []  # no liquidation feed for this symbol — never simulate
        for side, total, etype in (
            ("long", longs, "LONG_LIQUIDATION_BURST"),
            ("short", shorts, "SHORT_LIQUIDATION_BURST"),
        ):
            if total < LIQ_BURST_USD:
                continue
            idem = f"liqburst:{sym}:{side}:{_bucket(now, 300)}"
            if self._seen(idem, now):
                continue
            severity = "critical" if total >= LIQ_BURST_USD * 4 else "warning"
            out.append(
                make_event(
                    type=etype,
                    source=f"{SOURCE_PREFIX}/liquidations",
                    asset=sym,
                    instrument="usdt_perp",
                    severity=severity,
                    summary=f"{sym} {side} liquidation burst: ${total:,.0f} in {LIQ_BURST_WINDOW_SEC}s",
                    evidence=[
                        {
                            "indicator": f"{side}_liquidated_usd",
                            "value": f"{total:.0f}",
                            "supports": True,
                        }
                    ],
                    observed={f"{side}_liquidated_usd": round(total, 2)},
                    idempotency_key=idem,
                )
            )
        return out

    # -- news ------------------------------------------------------------------------------
    def _detect_news(self, sym: str, now: float) -> list[dict]:
        try:
            items = self.aggregator.latest_for_asset(sym, limit=10)
        except Exception as exc:
            log.info("news detector read failed: %s", exc)
            return []
        out = []
        for item in items:
            importance = item.get("importance") or 0
            if importance < NEWS_MIN_IMPORTANCE:
                continue
            published = item.get("published_at")
            try:
                pub_ts = datetime.fromisoformat(str(published).replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                continue
            if now - pub_ts > NEWS_MAX_AGE_SEC:
                continue
            idem = f"news:{item['id']}"
            if self._seen(idem, now):
                continue
            out.append(
                make_event(
                    type="NEWS_BREAKING",
                    source=f"{SOURCE_PREFIX}/news",
                    asset=sym,
                    severity="warning" if importance >= 5 else "info",
                    summary=f"{sym} news: {item['headline']}",
                    evidence=[
                        {
                            "indicator": "importance",
                            "value": str(importance),
                            "supports": True,
                        }
                    ],
                    observed={
                        "headline": item["headline"],
                        "source": item.get("source"),
                        "importance": importance,
                        "published_at": published,
                    },
                    idempotency_key=idem,
                    event_time=pub_ts,
                )
            )
        return out

    # -- market state / scenarios / regime -------------------------------------------------
    def _market_state(self, sym: str, deriv: Optional[dict], now: float) -> dict[str, Any]:
        state = self.state
        price = venue = None
        for exch in ("binance", "bybit"):
            p = state.get_price(exch, sym)
            if p and now - p["ts"] <= PRICE_FRESH_SEC:
                price, venue = float(p["price"]), exch
                break
        trades = state.recent_trades("binance", sym, since=(now - 900) * 1000)
        taker_ratio = cvd_slope = None
        if len(trades) >= 20:
            buy, sell = pressure_engine.split_taker_flow(trades)
            taker_ratio = pressure_engine.taker_ratio(buy, sell)
            cvd = pressure_engine.compute_cvd(trades, bucket_sec=60)
            if len(cvd) >= 2 and (buy + sell) > 0:
                delta = cvd[-1]["value"] - cvd[0]["value"]
                cvd_slope = max(-1.0, min(1.0, delta / (buy + sell)))
        book_imbalance = support = resistance = None
        snap = state.latest_depth(venue or "binance", sym)
        if snap and price:
            _, bids, asks = snap
            book_imbalance = pressure_engine.book_imbalance(bids, asks)
            walls = liq_engine.detect_walls(bids, asks, venue or "binance")
            bids_below = [w["price"] for w in walls["bids"] if w["price"] < price]
            asks_above = [w["price"] for w in walls["asks"] if w["price"] > price]
            support = max(bids_below) if bids_below else None
            resistance = min(asks_above) if asks_above else None
        spread_bps = None
        pa, pb = state.get_price("binance", sym), state.get_price("bybit", sym)
        if pa and pb and now - pa["ts"] <= PRICE_FRESH_SEC and now - pb["ts"] <= PRICE_FRESH_SEC:
            mid = (pa["price"] + pb["price"]) / 2.0
            if mid > 0:
                spread_bps = round((pa["price"] - pb["price"]) / mid * 1e4, 3)
        oi_change_pct = None
        hist = self._oi_history.get(sym)
        if hist:
            old = [(ts, v) for ts, v in hist if ts <= now - OI_MIN_HISTORY_SEC]
            if old and old[-1][1] > 0:
                oi_change_pct = round((hist[-1][1] - old[-1][1]) / old[-1][1] * 100.0, 3)
        return {
            "price": price,
            "funding": (deriv or {}).get("binance_funding"),
            "oi_change_pct": oi_change_pct,
            "taker_ratio": taker_ratio,
            "cvd_slope": cvd_slope,
            "book_imbalance": book_imbalance,
            "spread_bps": spread_bps,
            "support": support,
            "resistance": resistance,
            "price_change_24h": None,
        }

    def _detect_scenario_diff(
        self, sym: str, market_state: dict[str, Any], now: float
    ) -> list[dict]:
        try:
            scenarios = scenarios_v2.generate_scenarios_v2(sym, market_state)
        except Exception as exc:
            log.info("scenario diff failed for %s: %s", sym, exc)
            return []
        current = {s["type"]: s["id"] for s in scenarios if s["type"] != "no_trade"}
        previous = self._last_scenarios.get(sym)
        self._last_scenarios[sym] = current
        if previous is None:
            return []  # baseline — no flood on first observation
        out: list[dict[str, Any]] = []
        for stype, sid in current.items():
            if stype not in previous:
                idem = f"scenario:created:{sym}:{sid}"
                if self._seen(idem, now):
                    continue
                out.append(
                    make_event(
                        type="SCENARIO_CREATED",
                        source=f"{SOURCE_PREFIX}/scenarios",
                        asset=sym,
                        severity="info",
                        summary=f"{sym} scenario activated: {stype}",
                        evidence=[{"indicator": "scenario_type", "value": stype, "supports": True}],
                        observed={"scenario_type": stype},
                        scenario_id=sid,
                        idempotency_key=idem,
                    )
                )
        for stype, sid in previous.items():
            if stype not in current:
                idem = f"scenario:invalidated:{sym}:{sid}"
                if self._seen(idem, now):
                    continue
                out.append(
                    make_event(
                        type="SCENARIO_INVALIDATED",
                        source=f"{SOURCE_PREFIX}/scenarios",
                        asset=sym,
                        severity="warning",
                        summary=f"{sym} scenario invalidated: {stype}",
                        evidence=[
                            {"indicator": "scenario_type", "value": stype, "supports": True}
                        ],
                        observed={"scenario_type": stype},
                        scenario_id=sid,
                        idempotency_key=idem,
                    )
                )
        return out

    def _detect_regime_change(
        self, sym: str, market_state: dict[str, Any], now: float
    ) -> list[dict]:
        regime = scenarios_v2.classify_regime(market_state)
        if regime == "unknown":
            return []
        prev = self._last_regime.get(sym)
        self._last_regime[sym] = regime
        if prev is None or prev == regime:
            return []
        idem = f"regime:{sym}:{prev}->{regime}:{_bucket(now, 3600)}"
        if self._seen(idem, now):
            return []
        return [
            make_event(
                type="MARKET_REGIME_CHANGED",
                source=f"{SOURCE_PREFIX}/regime",
                asset=sym,
                severity="info",
                summary=f"{sym} market regime changed: {prev} -> {regime}",
                evidence=[
                    {"indicator": "regime", "value": f"{prev} -> {regime}", "supports": True}
                ],
                observed={"previous_regime": prev, "regime": regime},
                idempotency_key=idem,
            )
        ]

    # -- ws health --------------------------------------------------------------------------
    def _detect_ws_health(self, now: float) -> list[dict]:
        health = dict(self.state.ws_health)
        prev = self._ws_health_prev
        self._ws_health_prev = health
        if prev is None:
            return []  # baseline
        out: list[dict[str, Any]] = []
        for venue, healthy in health.items():
            was = prev.get(venue)
            if was == healthy:
                continue
            if healthy:
                etype, sev, word = "DATA_RECOVERED", "info", "recovered"
            else:
                etype, sev, word = "DATA_STALE", "warning", "went stale"
            last_msg = self.state.ws_last_msg.get(venue, 0.0)
            idem = f"wshealth:{venue}:{etype}:{_bucket(now, 300)}"
            if self._seen(idem, now):
                continue
            out.append(
                make_event(
                    type=etype,
                    source=f"{SOURCE_PREFIX}/feed_health",
                    venue=venue,
                    severity=sev,
                    summary=f"{venue} websocket feed {word}",
                    evidence=[
                        {
                            "indicator": "ws_health",
                            "value": f"{was} -> {healthy}",
                            "supports": True,
                        }
                    ],
                    observed={
                        "ws_health": healthy,
                        "last_message_age_sec": round(now - last_msg, 1) if last_msg else None,
                    },
                    idempotency_key=idem,
                )
            )
        return out


_engine: Optional[DetectorEngine] = None


def get_detector_engine() -> DetectorEngine:
    global _engine
    if _engine is None:
        _engine = DetectorEngine()
    return _engine


async def detector_loop() -> None:
    """While-True loop: run all detectors every settings.detector_interval
    seconds for the tracked symbols, publishing to the event bus."""
    settings = get_settings()
    engine = get_detector_engine()
    while True:
        try:
            await engine.run_once(settings.tracked_symbol_list)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("detector pass failed: %s", exc)
        try:
            await asyncio.sleep(settings.detector_interval)
        except asyncio.CancelledError:
            raise
