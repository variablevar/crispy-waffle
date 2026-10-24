"""Pressure engine: taker flow math, CVD, imbalance, confidence, no fabrication."""

from __future__ import annotations

from app.engines import pressure


def test_split_taker_flow(sample_trades):
    buy, sell = pressure.split_taker_flow(sample_trades)
    assert buy == 201.0       # 100*1 + 101*1
    assert sell == 249.5      # 100*2 + 99*0.5


def test_taker_ratio():
    assert pressure.taker_ratio(200.0, 100.0) == 2.0
    assert pressure.taker_ratio(0.0, 0.0) is None


def test_cvd_accumulates(sample_trades):
    cvd = pressure.compute_cvd(sample_trades)
    assert cvd, "expected a non-empty CVD series"
    assert cvd[-1]["value"] == round(201.0 - 249.5, 2)
    assert all("time" in p and "value" in p for p in cvd)


def test_book_imbalance_bounds(sample_depth):
    bids, asks = sample_depth
    imb = pressure.book_imbalance(bids, asks)
    assert imb is not None and -1.0 <= imb <= 1.0
    # bids total 1300 USD vs asks ~1477 USD -> slightly negative
    assert imb < 0
    assert pressure.book_imbalance([], []) is None


def test_confidence_labels():
    assert pressure.confidence_label(0, False) == "low"
    assert pressure.confidence_label(10_000, True) == "high"


def test_build_report_empty_is_unavailable_not_fabricated():
    report = pressure.build_report(
        "BTC", spot_trades=None, perp_trades=None, bids=None, asks=None,
        updated_at=None, stale=False,
    )
    assert report["available"] is False
    assert report["taker_buy_volume"] is None
    assert report["taker_ratio"] is None
    assert report["cvd"] == []
    assert report["confidence"] == "low"
    assert report["methodology"]


def test_build_report_with_data(sample_trades, sample_depth):
    bids, asks = sample_depth
    report = pressure.build_report(
        "BTC", spot_trades=sample_trades, perp_trades=None, bids=bids, asks=asks,
        updated_at="2026-10-22T00:00:00Z", stale=False,
    )
    assert report["available"] is True
    assert report["taker_buy_volume"] == 201.0
    assert report["spot_vs_futures"]["spot_ratio"] is not None
    assert report["spot_vs_futures"]["futures_ratio"] is None
    assert set(report["timeframes"].keys()) == {"15m", "1h", "4h"}
