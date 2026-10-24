"""Liquidity engine: wall detection, labelled estimates, heatmap shape."""

from __future__ import annotations

from app.engines import liquidity


def test_detect_walls_threshold(sample_depth):
    bids, asks = sample_depth
    walls = liquidity.detect_walls(bids, asks, exchange="binance")
    wall_prices = {w["price"] for w in walls["bids"]} | {w["price"] for w in walls["asks"]}
    # 99.0 x 10 = 990 USD and 102.5 x 12 = 1230 USD dominate the median (~100 USD)
    assert 99.0 in wall_prices
    assert 102.5 in wall_prices
    assert all(w["exchange"] == "binance" for w in walls["bids"] + walls["asks"])


def test_estimated_clusters_are_labelled_estimates():
    zones = liquidity.estimated_liquidation_clusters(mid_price=67000.0, open_interest_usd=5e9)
    assert zones, "expected estimated clusters for valid inputs"
    for z in zones:
        assert z["type"] == "estimated_liquidation"
        assert z["source"] == "estimation_model"
        assert z["label"].startswith("ESTIMATED")
        assert z["price_low"] < z["price_high"]
    # leverage buckets x 2 directions
    assert len(zones) == 2 * len(liquidity.LEVERAGE_BUCKETS)


def test_estimated_clusters_empty_on_bad_input():
    assert liquidity.estimated_liquidation_clusters(0, 5e9) == []
    assert liquidity.estimated_liquidation_clusters(100, 0) == []


def test_support_resistance_estimates_labelled(sample_depth):
    bids, asks = sample_depth
    walls = liquidity.detect_walls(bids, asks, exchange="binance")
    zones = liquidity.support_resistance_estimates(bids, asks, mid_price=100.0, walls=walls)
    for z in zones:
        assert z["type"] in ("estimated_support", "estimated_resistance")
        assert z["source"] == "estimation_model"
        assert "ESTIMATED" in z["label"]


def test_heatmap_shape_and_normalization(sample_depth):
    bids, asks = sample_depth
    snapshots = [(1000.0, bids, asks), (1060.0, bids, asks)]
    hm = liquidity.build_heatmap(snapshots, n_price_buckets=10)
    assert hm is not None
    assert len(hm["price_points"]) == 10
    assert len(hm["time_points"]) == 2
    assert len(hm["intensity"]) == 10
    assert all(len(row) == 2 for row in hm["intensity"])
    flat = [v for row in hm["intensity"] for v in row]
    assert max(flat) == 1.0  # normalized
    # insufficient history -> None, not a fabricated grid
    assert liquidity.build_heatmap([], n_price_buckets=10) is None
