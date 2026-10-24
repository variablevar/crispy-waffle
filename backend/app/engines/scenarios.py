"""Rule-based scenario engine.

Emits explainable scenarios (bullish_breakout / bearish_sweep /
short_squeeze / long_squeeze / no_trade) from a market-state snapshot.
When data is missing or signals conflict it emits no_trade with an
explanation. Rule-based and explainable; not financial advice.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.services import iso

METHODOLOGY = (
    "Rule-based engine. Each scenario lists its trigger conditions (what must "
    "be true now), confirmation signals (what would strengthen it), "
    "invalidation conditions (what kills it) and the evidence observed. "
    "Confidence is the fraction of weighted evidence supporting the scenario. "
    "Missing or conflicting inputs produce no_trade with an explanation. "
    "This is not financial advice."
)

# thresholds
TAKER_BULL = 1.15
TAKER_BEAR = 0.87
IMB_BULL = 0.10
IMB_BEAR = -0.10
FUNDING_EXTREME_POS = 0.0005  # 0.05% per 8h
FUNDING_EXTREME_NEG = -0.0005


def _state(**kwargs) -> dict[str, Any]:
    base = {
        "price": None,
        "funding": None,
        "oi_change_pct": None,
        "taker_ratio": None,
        "cvd_slope": None,  # -1..1 normalized
        "book_imbalance": None,  # -1..1
        "spread_bps": None,  # cross-exchange spread, basis points
        "support": None,
        "resistance": None,
        "price_change_24h": None,
    }
    base.update(kwargs)
    return base


def _present(state: dict[str, Any]) -> list[str]:
    return [k for k, v in state.items() if v is not None]


def _missing(state: dict[str, Any]) -> list[str]:
    return [k for k, v in state.items() if v is None]


def _mk(
    stype: str,
    symbol: str,
    *,
    title: str,
    bias: str,
    triggers: list[str],
    confirmations: list[str],
    invalidations: list[str],
    targets: list[dict[str, Any]],
    risks: list[str],
    evidence: list[dict[str, Any]],
    confidence: float,
    stale: bool = False,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12],
        "type": stype,
        "asset": symbol.upper(),
        "title": title,
        "bias": bias,
        "trigger_conditions": triggers,
        "confirmation_signals": confirmations,
        "invalidation_conditions": invalidations,
        "target_zones": targets,
        "risks": risks,
        "evidence": evidence,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "methodology": METHODOLOGY,
        "generated_at": iso(),
        "stale": stale,
    }


def _ev(indicator: str, value: Any, supports: bool) -> dict[str, Any]:
    return {"indicator": indicator, "value": str(value), "supports": supports}


def _no_trade(symbol: str, explanation: str, state: dict[str, Any], stale: bool = False) -> dict[str, Any]:
    return _mk(
        "no_trade",
        symbol,
        title="No trade — edge not established",
        bias="none",
        triggers=[],
        confirmations=[],
        invalidations=[],
        targets=[],
        risks=["Forcing a trade without confluence", "Data gaps may hide real conditions"],
        evidence=[_ev("explanation", explanation, False)],
        confidence=0.0,
        stale=stale,
    )


def _conflicting(state: dict[str, Any]) -> bool:
    """Detect grossly conflicting signals."""
    tr = state.get("taker_ratio")
    imb = state.get("book_imbalance")
    cvd = state.get("cvd_slope")
    if tr is not None and imb is not None:
        if tr > TAKER_BULL and imb < IMB_BEAR:
            return True
        if tr < TAKER_BEAR and imb > IMB_BULL:
            return True
    if tr is not None and cvd is not None:
        if tr > TAKER_BULL and cvd < -0.3:
            return True
        if tr < TAKER_BEAR and cvd > 0.3:
            return True
    return False


def generate_scenarios(symbol: str, state: dict[str, Any], stale: bool = False) -> list[dict[str, Any]]:
    """Evaluate rules against a market-state snapshot.

    state keys: price, funding, oi_change_pct, taker_ratio, cvd_slope (-1..1),
    book_imbalance (-1..1), spread_bps, support, resistance, price_change_24h.
    """
    state = _state(**state)
    price = state["price"]
    if price is None or price <= 0:
        missing = ", ".join(_missing(state)) or "price"
        return [
            _no_trade(symbol, f"Required market data missing ({missing}); cannot evaluate scenarios.", state, stale)
        ]

    if _conflicting(state):
        return [
            _no_trade(
                symbol,
                "Signals conflict (taker flow vs book imbalance / CVD disagree); standing aside.",
                state,
                stale,
            )
        ]

    tr = state["taker_ratio"]
    imb = state["book_imbalance"]
    cvd = state["cvd_slope"]
    funding = state["funding"]
    oi_chg = state["oi_change_pct"]
    resistance = state["resistance"]
    support = state["support"]
    scenarios: list[dict[str, Any]] = []

    # --- short squeeze -----------------------------------------------------
    if funding is not None and funding <= FUNDING_EXTREME_NEG and tr is not None and tr > 1.0:
        ev = [
            _ev("funding", f"{funding:.5f} (deeply negative — shorts paying longs)", True),
            _ev("taker_ratio", tr, tr > 1.0),
            _ev("oi_change_pct", oi_chg if oi_chg is not None else "unavailable", (oi_chg or 0) > 0),
            _ev("cvd_slope", cvd if cvd is not None else "unavailable", (cvd or 0) > 0),
        ]
        conf = sum(1 for e in ev if e["supports"]) / len(ev)
        tgt_lo = price * 1.02
        tgt_hi = price * (1.05 if resistance is None else max(1.02, (resistance / price)))
        scenarios.append(
            _mk(
                "short_squeeze",
                symbol,
                title="Potential short squeeze — crowded shorts under pressure",
                bias="long",
                triggers=["Funding deeply negative while taker buy flow dominates"],
                confirmations=["OI rising into the move", "Price reclaiming nearby ask walls", "CVD slope positive"],
                invalidations=["Funding normalizes >= 0", "Taker ratio falls back below 1.0"],
                targets=[{"price_low": round(tgt_lo, 8), "price_high": round(tgt_hi, 8), "label": "squeeze extension zone"}],
                risks=["Squeeze fails if spot demand fades", "Funding can stay negative longer than expected"],
                evidence=ev,
                confidence=conf,
                stale=stale,
            )
        )

    # --- long squeeze ------------------------------------------------------
    if funding is not None and funding >= FUNDING_EXTREME_POS and tr is not None and tr < 1.0:
        ev = [
            _ev("funding", f"{funding:.5f} (elevated — longs paying shorts)", True),
            _ev("taker_ratio", tr, tr < 1.0),
            _ev("oi_change_pct", oi_chg if oi_chg is not None else "unavailable", (oi_chg or 0) > 0),
            _ev("cvd_slope", cvd if cvd is not None else "unavailable", (cvd or 0) < 0),
        ]
        conf = sum(1 for e in ev if e["supports"]) / len(ev)
        tgt_hi = price * 0.98
        tgt_lo = price * (0.95 if support is None else min(0.98, support / price))
        scenarios.append(
            _mk(
                "long_squeeze",
                symbol,
                title="Potential long squeeze — crowded longs vulnerable",
                bias="short",
                triggers=["Funding elevated while taker sell flow dominates"],
                confirmations=["OI rising while price stalls", "Bid walls pulling", "CVD slope negative"],
                invalidations=["Funding normalizes <= 0", "Taker ratio back above 1.0"],
                targets=[{"price_low": round(tgt_lo, 8), "price_high": round(tgt_hi, 8), "label": "flush zone"}],
                risks=["Squeeze thesis dies on strong spot bid", "Funding can stay high in strong trends"],
                evidence=ev,
                confidence=conf,
                stale=stale,
            )
        )

    # --- bullish breakout --------------------------------------------------
    bull_flow = tr is not None and tr > TAKER_BULL
    bull_book = imb is not None and imb > IMB_BULL
    bull_cvd = cvd is not None and cvd > 0.2
    above_resistance = resistance is not None and price > resistance
    funding_ok = funding is None or funding < FUNDING_EXTREME_POS
    bull_votes = sum([bull_flow, bull_book, bull_cvd, above_resistance])
    if bull_votes >= 2 and funding_ok:
        ev = [
            _ev("taker_ratio", tr if tr is not None else "unavailable", bull_flow),
            _ev("book_imbalance", imb if imb is not None else "unavailable", bull_book),
            _ev("cvd_slope", cvd if cvd is not None else "unavailable", bull_cvd),
            _ev("price_vs_resistance", f"{price} vs {resistance}" if resistance else "unavailable", above_resistance),
            _ev("funding", funding if funding is not None else "unavailable", funding_ok),
        ]
        conf = sum(1 for e in ev if e["supports"]) / len(ev)
        scenarios.append(
            _mk(
                "bullish_breakout",
                symbol,
                title="Bullish breakout forming — aggressive buying with book support",
                bias="long",
                triggers=["Taker buy dominance", "Book skewed to bids"],
                confirmations=["Break and hold above nearest ask wall / estimated resistance", "Funding stays neutral"],
                invalidations=["Taker ratio back below 1.0", "Rejection wick below breakout level", "Funding spikes positive"],
                targets=[{"price_low": round(price * 1.02, 8), "price_high": round(price * 1.06, 8), "label": "measured move zone"}],
                risks=["False breakout / liquidity grab above range highs", "BTC correlation drag"],
                evidence=ev,
                confidence=conf,
                stale=stale,
            )
        )

    # --- bearish sweep -----------------------------------------------------
    bear_flow = tr is not None and tr < TAKER_BEAR
    bear_book = imb is not None and imb < IMB_BEAR
    bear_cvd = cvd is not None and cvd < -0.2
    below_support = support is not None and price < support
    bear_votes = sum([bear_flow, bear_book, bear_cvd, below_support])
    if bear_votes >= 2:
        ev = [
            _ev("taker_ratio", tr if tr is not None else "unavailable", bear_flow),
            _ev("book_imbalance", imb if imb is not None else "unavailable", bear_book),
            _ev("cvd_slope", cvd if cvd is not None else "unavailable", bear_cvd),
            _ev("price_vs_support", f"{price} vs {support}" if support else "unavailable", below_support),
        ]
        conf = sum(1 for e in ev if e["supports"]) / len(ev)
        scenarios.append(
            _mk(
                "bearish_sweep",
                symbol,
                title="Bearish sweep risk — aggressive selling into thinning bids",
                bias="short",
                triggers=["Taker sell dominance", "Book skewed to asks"],
                confirmations=["Loss of nearest bid wall / estimated support", "CVD accelerating down"],
                invalidations=["Taker ratio back above 1.0", "Sweep reclaims broken level quickly"],
                targets=[{"price_low": round(price * 0.94, 8), "price_high": round(price * 0.98, 8), "label": "downside liquidity zone"}],
                risks=["Sweep reverses violently (stop hunt)", "Shorts overcrowd and squeeze"],
                evidence=ev,
                confidence=conf,
                stale=stale,
            )
        )

    if not scenarios:
        present = ", ".join(_present(state)) or "none"
        missing = ", ".join(_missing(state)) or "none"
        scenarios.append(
            _no_trade(
                symbol,
                f"No rule set reached its trigger threshold. Data present: {present}. Missing: {missing}.",
                state,
                stale,
            )
        )
    return scenarios
