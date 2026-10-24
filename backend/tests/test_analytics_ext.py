"""Engine extension tests: volume_acceleration, detect_sweep,
detect_withdrawals, contract normalization (linear vs inverse), premium."""

from __future__ import annotations

import pytest

from app.engines import contract_norm
from app.engines.liquidity import detect_sweep, detect_withdrawals
from app.engines.pressure import volume_acceleration

NOW = 1_700_000_000.0


def _trade(ts_sec: float, price: float, qty: float) -> dict:
    return {"time": ts_sec * 1000, "price": price, "qty": qty}


# -- volume_acceleration --------------------------------------------------------

def test_volume_acceleration_math():
    trades = [
        _trade(NOW - 60, 100.0, 2.0),    # recent window: 200 quote
        _trade(NOW - 120, 100.0, 1.0),   # recent window: 100 quote
        _trade(NOW - 400, 100.0, 1.5),   # prior window: 150 quote
    ]
    assert volume_acceleration(trades, window_sec=300, now=NOW) == pytest.approx(2.0)


def test_volume_acceleration_none_without_prior_window():
    trades = [_trade(NOW - 60, 100.0, 2.0)]
    assert volume_acceleration(trades, window_sec=300, now=NOW) is None
    assert volume_acceleration([], window_sec=300, now=NOW) is None


def test_volume_acceleration_handles_second_timestamps():
    trades = [
        {"time": NOW - 60, "price": 100.0, "qty": 1.0},
        {"time": NOW - 400, "price": 100.0, "qty": 1.0},
    ]
    assert volume_acceleration(trades, window_sec=300, now=NOW) == pytest.approx(1.0)


# -- detect_sweep -----------------------------------------------------------------

ZONE = {"price_low": 100.0, "price_high": 101.0, "label": "observed bid wall"}


def test_detect_sweep_down_and_reclaim():
    series = [(1, 100.5), (2, 99.8), (3, 99.7), (4, 100.6)]
    sweeps = detect_sweep(series, [ZONE])
    assert len(sweeps) == 1
    assert sweeps[0]["direction"] == "down"
    assert sweeps[0]["price"] == pytest.approx(99.7)  # excursion extreme
    assert sweeps[0]["time"] == 4


def test_detect_sweep_up_and_reject():
    series = [(1, 100.5), (2, 101.3), (3, 100.4)]
    sweeps = detect_sweep(series, [ZONE])
    assert len(sweeps) == 1
    assert sweeps[0]["direction"] == "up"
    assert sweeps[0]["price"] == pytest.approx(101.3)


def test_detect_sweep_negative_cases():
    assert detect_sweep([(1, 100.5), (2, 100.6), (3, 100.4)], [ZONE]) == []
    # break below with no reclaim within lookahead => not a sweep
    assert detect_sweep([(1, 100.5), (2, 99.5), (3, 99.4)], [ZONE]) == []
    assert detect_sweep([], [ZONE]) == []


# -- detect_withdrawals -------------------------------------------------------------

def test_detect_withdrawals():
    prev = [[100.0, 10.0], [99.0, 5.0], [98.0, 4.0]]
    cur = [[100.0, 3.0], [99.0, 5.0]]  # 100 dropped 70%, 98 pulled entirely
    out = detect_withdrawals(prev, cur, threshold_pct=50)
    by_price = {w["price"]: w for w in out}
    assert set(by_price) == {100.0, 98.0}
    assert by_price[100.0]["drop_pct"] == pytest.approx(70.0)
    assert by_price[98.0]["drop_pct"] == pytest.approx(100.0)
    assert by_price[98.0]["cur_size"] == 0.0


def test_detect_withdrawals_no_change():
    book = [[100.0, 10.0]]
    assert detect_withdrawals(book, book) == []


# -- contract_norm -------------------------------------------------------------------

def test_normalize_volume_linear():
    out = contract_norm.normalize_volume(2.0, 100.0, "linear")
    assert out["base_volume"] == pytest.approx(2.0)
    assert out["quote_volume"] == pytest.approx(200.0)


def test_normalize_volume_inverse():
    # 1000 contracts x $100/contract at price 50k => $100k quote => 2 BTC base
    out = contract_norm.normalize_volume(1000.0, 50_000.0, "inverse", contract_size=100.0)
    assert out["quote_volume"] == pytest.approx(100_000.0)
    assert out["base_volume"] == pytest.approx(2.0)


def test_normalize_volume_inverse_requires_contract_size():
    with pytest.raises(ValueError):
        contract_norm.normalize_volume(1000.0, 50_000.0, "inverse")


def test_normalize_volume_rejects_bad_inputs():
    with pytest.raises(ValueError):
        contract_norm.normalize_volume(1.0, 0.0, "linear")
    with pytest.raises(ValueError):
        contract_norm.normalize_volume(1.0, 100.0, "quadratic")


def test_perp_premium_pct():
    assert contract_norm.perp_premium_pct(51_000.0, 50_000.0) == pytest.approx(2.0)
    assert contract_norm.perp_premium_pct(49_500.0, 50_000.0) == pytest.approx(-1.0)
    assert contract_norm.perp_premium_pct(0.0, 50_000.0) is None


def test_basis():
    out = contract_norm.basis(51_000.0, 50_000.0)
    assert out["absolute"] == pytest.approx(1000.0)
    assert out["pct"] == pytest.approx(2.0)
    assert contract_norm.basis(0.0, 50_000.0) == {"absolute": None, "pct": None}
