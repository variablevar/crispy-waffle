"""ScenarioV2 tests: all 8 core types reachable from crafted states, contract
keys present (superset of legacy), no invented target zones."""

from __future__ import annotations

from app.engines import scenarios_v2
from tests.test_scenarios import REQUIRED_KEYS as LEGACY_KEYS

V2_KEYS = LEGACY_KEYS | {
    "instrument", "market_regime", "status", "contradicting_evidence",
    "confidence_note", "methodology_version",
}


def _assert_v2_contract(sc: dict):
    assert V2_KEYS <= set(sc.keys()), f"missing keys: {V2_KEYS - set(sc.keys())}"
    assert 0.0 <= sc["confidence"] <= 1.0
    assert sc["bias"] in ("long", "short", "none")
    assert sc["status"] in ("active", "invalidated", "expired")
    assert sc["market_regime"] in ("trending_up", "trending_down", "ranging", "unknown")
    assert sc["confidence_note"] == "rule-vote fraction, NOT a calibrated probability"
    assert sc["methodology_version"] == "scenarios.v2"
    assert isinstance(sc["contradicting_evidence"], list)
    for ce in sc["contradicting_evidence"]:
        assert set(ce) == {"indicator", "value"}


def _types(out):
    return {s["type"] for s in out}


def test_bullish_continuation_reachable():
    out = scenarios_v2.generate_scenarios_v2(
        "BTC", {"price": 100.0, "price_change_24h": 3.0, "taker_ratio": 1.2, "cvd_slope": 0.3}
    )
    assert "bullish_continuation" in _types(out)
    sc = next(s for s in out if s["type"] == "bullish_continuation")
    assert sc["bias"] == "long"
    assert sc["market_regime"] == "trending_up"
    _assert_v2_contract(sc)


def test_bearish_continuation_reachable():
    out = scenarios_v2.generate_scenarios_v2(
        "BTC", {"price": 100.0, "price_change_24h": -3.0, "taker_ratio": 0.85, "cvd_slope": -0.3}
    )
    assert "bearish_continuation" in _types(out)
    sc = next(s for s in out if s["type"] == "bearish_continuation")
    assert sc["bias"] == "short"
    _assert_v2_contract(sc)


def test_bullish_reversal_reachable():
    out = scenarios_v2.generate_scenarios_v2(
        "ETH",
        {"price": 100.0, "support": 99.5, "price_change_24h": 0.5, "taker_ratio": 1.3},
    )
    assert "bullish_reversal" in _types(out)
    _assert_v2_contract(next(s for s in out if s["type"] == "bullish_reversal"))


def test_bearish_reversal_reachable():
    out = scenarios_v2.generate_scenarios_v2(
        "ETH",
        {"price": 100.0, "resistance": 100.5, "price_change_24h": -0.5, "taker_ratio": 0.75},
    )
    assert "bearish_reversal" in _types(out)
    _assert_v2_contract(next(s for s in out if s["type"] == "bearish_reversal"))


def test_short_squeeze_reachable():
    out = scenarios_v2.generate_scenarios_v2(
        "SOL", {"price": 100.0, "funding": -0.001, "taker_ratio": 1.2}
    )
    assert "short_squeeze" in _types(out)
    _assert_v2_contract(next(s for s in out if s["type"] == "short_squeeze"))


def test_long_squeeze_reachable():
    out = scenarios_v2.generate_scenarios_v2(
        "SOL", {"price": 100.0, "funding": 0.001, "taker_ratio": 0.9}
    )
    assert "long_squeeze" in _types(out)
    _assert_v2_contract(next(s for s in out if s["type"] == "long_squeeze"))


def test_range_continuation_reachable():
    out = scenarios_v2.generate_scenarios_v2(
        "BTC",
        {"price": 100.0, "support": 98.0, "resistance": 102.0,
         "price_change_24h": 0.3, "taker_ratio": 1.0, "funding": 0.0001},
    )
    assert "range_continuation" in _types(out)
    sc = next(s for s in out if s["type"] == "range_continuation")
    assert sc["bias"] == "none"
    assert sc["market_regime"] == "ranging"
    _assert_v2_contract(sc)


def test_no_trade_on_missing_data():
    out = scenarios_v2.generate_scenarios_v2("BTC", {"price": None})
    assert len(out) == 1
    assert out[0]["type"] == "no_trade"
    _assert_v2_contract(out[0])


def test_legacy_rule_sets_still_emit():
    bull = scenarios_v2.generate_scenarios_v2(
        "ETH", {"price": 2350.0, "taker_ratio": 1.4, "cvd_slope": 0.6,
                "book_imbalance": 0.3, "resistance": 2340.0, "funding": 0.0001}
    )
    assert "bullish_breakout" in _types(bull)
    bear = scenarios_v2.generate_scenarios_v2(
        "ETH", {"price": 2290.0, "taker_ratio": 0.7, "cvd_slope": -0.5,
                "book_imbalance": -0.3, "support": 2300.0}
    )
    assert "bearish_sweep" in _types(bear)


def test_no_target_zones_without_observed_levels():
    out = scenarios_v2.generate_scenarios_v2(
        "BTC", {"price": 100.0, "price_change_24h": 3.0, "taker_ratio": 1.2, "cvd_slope": 0.3}
    )
    assert out
    for sc in out:
        assert sc["target_zones"] == []


def test_target_zones_from_observed_levels():
    out = scenarios_v2.generate_scenarios_v2(
        "SOL", {"price": 100.0, "funding": -0.001, "taker_ratio": 1.2, "resistance": 103.0}
    )
    sc = next(s for s in out if s["type"] == "short_squeeze")
    assert sc["target_zones"]
    zone = sc["target_zones"][0]
    assert zone["price_low"] == 103.0  # anchored to the observed resistance


def test_contradicting_evidence_populated():
    out = scenarios_v2.generate_scenarios_v2(
        "BTC", {"price": 100.0, "price_change_24h": 3.0, "taker_ratio": 1.2, "cvd_slope": -0.1}
    )
    sc = next(s for s in out if s["type"] == "bullish_continuation")
    assert any(ce["indicator"] == "cvd_slope" for ce in sc["contradicting_evidence"])


def test_classify_regime():
    assert scenarios_v2.classify_regime({"price_change_24h": 3.0}) == "trending_up"
    assert scenarios_v2.classify_regime({"price_change_24h": -3.0}) == "trending_down"
    assert scenarios_v2.classify_regime({"price_change_24h": 0.5}) == "ranging"
    assert scenarios_v2.classify_regime({"price": 100.0, "support": 98.0, "resistance": 102.0}) == "ranging"
    assert scenarios_v2.classify_regime({"price": 103.0, "resistance": 102.0}) == "trending_up"
    assert scenarios_v2.classify_regime({"price": 97.0, "support": 98.0}) == "trending_down"
    assert scenarios_v2.classify_regime({}) == "unknown"
