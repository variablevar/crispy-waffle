"""Scenario engine: each scenario type reachable, no_trade fallbacks, contract keys."""

from __future__ import annotations

from app.engines import scenarios

REQUIRED_KEYS = {
    "id", "type", "asset", "title", "bias", "trigger_conditions",
    "confirmation_signals", "invalidation_conditions", "target_zones",
    "risks", "evidence", "confidence", "methodology", "generated_at", "stale",
}


def _assert_contract(sc: dict):
    assert REQUIRED_KEYS <= set(sc.keys()), f"missing keys: {REQUIRED_KEYS - set(sc.keys())}"
    assert 0.0 <= sc["confidence"] <= 1.0
    assert sc["bias"] in ("long", "short", "none")
    assert sc["methodology"]


def test_missing_price_yields_no_trade():
    out = scenarios.generate_scenarios("BTC", {"price": None})
    assert len(out) == 1
    assert out[0]["type"] == "no_trade"
    assert out[0]["bias"] == "none"
    _assert_contract(out[0])


def test_conflicting_signals_yield_no_trade():
    out = scenarios.generate_scenarios(
        "ETH",
        {"price": 2300.0, "taker_ratio": 1.3, "cvd_slope": 0.5, "book_imbalance": -0.4},
    )
    assert out[0]["type"] == "no_trade"
    _assert_contract(out[0])


def test_bullish_breakout_reachable():
    out = scenarios.generate_scenarios(
        "ETH",
        {"price": 2350.0, "taker_ratio": 1.4, "cvd_slope": 0.6, "book_imbalance": 0.3,
         "resistance": 2340.0, "funding": 0.0001},
    )
    types = {s["type"] for s in out}
    assert "bullish_breakout" in types
    for sc in out:
        _assert_contract(sc)
    bull = next(s for s in out if s["type"] == "bullish_breakout")
    assert bull["bias"] == "long"
    assert bull["evidence"]


def test_bearish_sweep_reachable():
    out = scenarios.generate_scenarios(
        "ETH",
        {"price": 2290.0, "taker_ratio": 0.7, "cvd_slope": -0.5, "book_imbalance": -0.3,
         "support": 2300.0},
    )
    types = {s["type"] for s in out}
    assert "bearish_sweep" in types


def test_short_squeeze_reachable():
    out = scenarios.generate_scenarios(
        "BTC", {"price": 67000.0, "funding": -0.001, "taker_ratio": 1.3, "oi_change_pct": 5.0},
    )
    assert any(s["type"] == "short_squeeze" for s in out)


def test_long_squeeze_reachable():
    out = scenarios.generate_scenarios(
        "BTC", {"price": 67000.0, "funding": 0.001, "taker_ratio": 0.8, "oi_change_pct": 4.0},
    )
    assert any(s["type"] == "long_squeeze" for s in out)


def test_neutral_state_no_trade():
    out = scenarios.generate_scenarios("SOL", {"price": 150.0, "taker_ratio": 1.0})
    assert out[0]["type"] == "no_trade"
    assert "No rule set" in out[0]["title"] or out[0]["risks"]
