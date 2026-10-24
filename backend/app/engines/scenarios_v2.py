"""ScenarioV2 engine per AGENT_CONTRACT.md.

Superset of the legacy rule-based engine: all legacy keys keep their exact
names, plus instrument / market_regime / status / contradicting_evidence /
confidence_note / methodology_version. The eight core types
(bullish_continuation, bearish_continuation, bullish_reversal,
bearish_reversal, short_squeeze, long_squeeze, range_continuation, no_trade)
are joined by the legacy bullish_breakout / bearish_sweep rule-sets, reused
from app.engines.scenarios.

Target zones are only emitted when derived from OBSERVED support/resistance
levels — never invented from price multiples; the field is [] otherwise.
Rule-based and explainable; not financial advice.
"""

from __future__ import annotations

from typing import Any, Optional

from app.engines import scenarios as legacy

METHODOLOGY_VERSION = "scenarios.v2"
CONFIDENCE_NOTE = "rule-vote fraction, NOT a calibrated probability"

TRENDING_PCT = 2.0  # |24h change| >= this => trending
REVERSAL_PROXIMITY_PCT = 1.5  # price within this % of the level
RANGE_TAKER_LO = 0.9
RANGE_TAKER_HI = 1.1


def classify_regime(state: dict[str, Any]) -> str:
    """trending_up | trending_down | ranging | unknown, from observed inputs.

    Primary signal: 24h price change. Fallback: price position vs observed
    support/resistance. "unknown" when nothing observed can decide it.
    """
    chg = state.get("price_change_24h")
    if chg is not None:
        if chg >= TRENDING_PCT:
            return "trending_up"
        if chg <= -TRENDING_PCT:
            return "trending_down"
        return "ranging"
    price = state.get("price")
    support = state.get("support")
    resistance = state.get("resistance")
    if price is None or price <= 0:
        return "unknown"
    if resistance is not None and price > resistance:
        return "trending_up"
    if support is not None and price < support:
        return "trending_down"
    if support is not None and resistance is not None and support < price < resistance:
        return "ranging"
    return "unknown"


def _target_zones(bias: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Target zones from OBSERVED levels only. [] when none observed."""
    resistance = state.get("resistance")
    support = state.get("support")
    if bias == "long" and resistance is not None and resistance > 0:
        return [
            {
                "price_low": round(resistance, 8),
                "price_high": round(resistance * 1.02, 8),
                "label": "observed resistance zone",
            }
        ]
    if bias == "short" and support is not None and support > 0:
        return [
            {
                "price_low": round(support * 0.98, 8),
                "price_high": round(support, 8),
                "label": "observed support zone",
            }
        ]
    return []


def _upgrade(sc: dict[str, Any], state: dict[str, Any], regime: str) -> dict[str, Any]:
    """Promote a legacy scenario dict to the ScenarioV2 superset."""
    contradicting = [
        {"indicator": e["indicator"], "value": e["value"]}
        for e in sc.get("evidence", [])
        if e.get("supports") is False
    ]
    return {
        **sc,
        "instrument": "usdt_perp",
        "market_regime": regime,
        "status": "active",
        "contradicting_evidence": contradicting,
        "target_zones": _target_zones(sc.get("bias", "none"), state),
        "confidence_note": CONFIDENCE_NOTE,
        "methodology_version": METHODOLOGY_VERSION,
    }


def _near(price: float, level: Optional[float], pct: float = REVERSAL_PROXIMITY_PCT) -> bool:
    return level is not None and level > 0 and abs(price - level) / price * 100.0 <= pct


def _v2_rules(
    symbol: str, state: dict[str, Any], regime: str, stale: bool
) -> list[dict[str, Any]]:
    """Continuation / reversal / range rules. All inputs observed; any None
    simply drops that evidence vote."""
    price = state["price"]
    tr = state.get("taker_ratio")
    cvd = state.get("cvd_slope")
    imb = state.get("book_imbalance")
    funding = state.get("funding")
    support = state.get("support")
    resistance = state.get("resistance")
    out: list[dict[str, Any]] = []

    def mk(stype, title, bias, triggers, confirmations, invalidations, risks, evidence):
        conf = (
            sum(1 for e in evidence if e["supports"]) / len(evidence) if evidence else 0.0
        )
        out.append(
            legacy._mk(
                stype,
                symbol,
                title=title,
                bias=bias,
                triggers=triggers,
                confirmations=confirmations,
                invalidations=invalidations,
                targets=[],  # replaced with observed-level zones in _upgrade
                risks=risks,
                evidence=evidence,
                confidence=conf,
                stale=stale,
            )
        )

    if regime == "trending_up" and tr is not None and tr > 1.0:
        evidence = [
            legacy._ev("market_regime", regime, True),
            legacy._ev("taker_ratio", tr, tr > 1.0),
            legacy._ev("cvd_slope", cvd if cvd is not None else "unavailable", (cvd or 0) >= 0),
            legacy._ev(
                "book_imbalance", imb if imb is not None else "unavailable", (imb or 0) > 0
            ),
        ]
        mk(
            "bullish_continuation",
            "Bullish continuation — uptrend with aggressive buy flow",
            "long",
            ["Trending up with taker buy dominance"],
            ["CVD slope stays positive", "Book skews to bids"],
            ["Taker ratio falls below 1.0", "Regime flips to ranging/down"],
            ["Trend exhaustion after extended move", "Funding overheating"],
            evidence,
        )

    if regime == "trending_down" and tr is not None and tr < 1.0:
        evidence = [
            legacy._ev("market_regime", regime, True),
            legacy._ev("taker_ratio", tr, tr < 1.0),
            legacy._ev("cvd_slope", cvd if cvd is not None else "unavailable", (cvd or 0) <= 0),
            legacy._ev(
                "book_imbalance", imb if imb is not None else "unavailable", (imb or 0) < 0
            ),
        ]
        mk(
            "bearish_continuation",
            "Bearish continuation — downtrend with aggressive sell flow",
            "short",
            ["Trending down with taker sell dominance"],
            ["CVD slope stays negative", "Book skews to asks"],
            ["Taker ratio rises above 1.0", "Regime flips to ranging/up"],
            ["Capitulation bounce", "Shorts overcrowd and squeeze"],
            evidence,
        )

    if regime in ("ranging", "trending_down") and _near(price, support) and tr is not None and tr >= RANGE_TAKER_HI:
        evidence = [
            legacy._ev("support", f"{support} (observed)", True),
            legacy._ev("price_vs_support", f"{price} within {REVERSAL_PROXIMITY_PCT}% of support", True),
            legacy._ev("taker_ratio", tr, tr >= RANGE_TAKER_HI),
            legacy._ev("cvd_slope", cvd if cvd is not None else "unavailable", (cvd or 0) > 0),
        ]
        mk(
            "bullish_reversal",
            "Bullish reversal attempt — buy flow at observed support",
            "long",
            ["Price at observed support with taker buy dominance"],
            ["CVD slope turns positive", "Ask walls above get absorbed"],
            ["Support breaks on volume", "Taker ratio falls back below 1.0"],
            ["Support is an estimate from observed walls, not a guarantee"],
            evidence,
        )

    if regime in ("ranging", "trending_up") and _near(price, resistance) and tr is not None and tr <= RANGE_TAKER_LO:
        evidence = [
            legacy._ev("resistance", f"{resistance} (observed)", True),
            legacy._ev(
                "price_vs_resistance",
                f"{price} within {REVERSAL_PROXIMITY_PCT}% of resistance",
                True,
            ),
            legacy._ev("taker_ratio", tr, tr <= RANGE_TAKER_LO),
            legacy._ev("cvd_slope", cvd if cvd is not None else "unavailable", (cvd or 0) < 0),
        ]
        mk(
            "bearish_reversal",
            "Bearish reversal attempt — sell flow at observed resistance",
            "short",
            ["Price at observed resistance with taker sell dominance"],
            ["CVD slope turns negative", "Bid walls below pull"],
            ["Resistance breaks and holds", "Taker ratio back above 1.0"],
            ["Breakout through resistance can accelerate violently"],
            evidence,
        )

    funding_neutral = funding is None or abs(funding) < legacy.FUNDING_EXTREME_POS
    in_range = (
        support is not None and resistance is not None and support < price < resistance
    )
    if (
        regime == "ranging"
        and in_range
        and funding_neutral
        and (tr is None or RANGE_TAKER_LO <= tr <= RANGE_TAKER_HI)
    ):
        evidence = [
            legacy._ev("market_regime", regime, True),
            legacy._ev("range", f"{support} .. {resistance} (observed)", in_range),
            legacy._ev(
                "taker_ratio",
                tr if tr is not None else "unavailable",
                tr is not None and RANGE_TAKER_LO <= tr <= RANGE_TAKER_HI,
            ),
            legacy._ev(
                "funding", funding if funding is not None else "unavailable", funding_neutral
            ),
        ]
        mk(
            "range_continuation",
            "Range continuation — price balanced between observed support and resistance",
            "none",
            ["Ranging regime, price inside observed support/resistance band"],
            ["Funding stays neutral", "Taker flow stays balanced"],
            ["Range edge breaks with volume", "Funding turns extreme"],
            ["Range edges attract stop hunts", "Low conviction environment"],
            evidence,
        )

    return out


def generate_scenarios_v2(
    symbol: str, state: dict[str, Any], stale: bool = False
) -> list[dict[str, Any]]:
    """ScenarioV2 scenarios for `symbol` from a market-state snapshot.

    state keys (any may be None — missing inputs never fabricate):
    price, funding, oi_change_pct, taker_ratio, cvd_slope, book_imbalance,
    spread_bps, support, resistance, price_change_24h.
    """
    state = legacy._state(**state)
    regime = classify_regime(state)
    legacy_out = legacy.generate_scenarios(symbol, state, stale=stale)
    fired = [sc for sc in legacy_out if sc["type"] != "no_trade"]

    out: list[dict[str, Any]] = [_upgrade(sc, state, regime) for sc in fired]
    price = state["price"]
    if price is not None and price > 0 and not legacy._conflicting(state):
        out.extend(
            _upgrade(sc, state, regime)
            for sc in _v2_rules(symbol, state, regime, stale)
        )
    if not out:
        # legacy returned a no_trade (missing data, conflict, or no rule fired)
        no_trade = next((sc for sc in legacy_out if sc["type"] == "no_trade"), None)
        if no_trade is not None:
            out.append(_upgrade(no_trade, state, regime))
    return out
