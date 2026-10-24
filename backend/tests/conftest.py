"""Offline test fixtures. Env is set BEFORE any app import so the settings
singleton boots with workers/DB/Redis disabled."""

from __future__ import annotations

import os
import time

os.environ.setdefault("WORKERS_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("NEWSDATA_API_KEY", "")
os.environ.setdefault("GNEWS_API_KEY", "")

import pytest


@pytest.fixture()
def sample_trades() -> list[dict]:
    """Raw-Binance-shaped aggTrades: m=True => buyer is maker => taker SELL."""
    now_ms = int(time.time() * 1000)
    return [
        {"p": "100.0", "q": "1.0", "m": False, "T": now_ms - 500},   # taker buy 100
        {"p": "100.0", "q": "2.0", "m": True, "T": now_ms - 400},    # taker sell 200
        {"p": "101.0", "q": "1.0", "m": False, "T": now_ms - 300},   # taker buy 101
        {"p": "99.0", "q": "0.5", "m": True, "T": now_ms - 200},     # taker sell 49.5
    ]


@pytest.fixture()
def sample_depth() -> tuple[list[list], list[list]]:
    bids = [["99.0", "10.0"], ["98.5", "1.0"], ["98.0", "1.0"], ["97.5", "1.0"]]
    asks = [["101.0", "1.0"], ["101.5", "1.0"], ["102.0", "1.0"], ["102.5", "12.0"]]
    return bids, asks


@pytest.fixture()
def coingecko_market_row() -> dict:
    return {
        "id": "bitcoin",
        "symbol": "btc",
        "name": "Bitcoin",
        "image": "https://example.com/btc.png",
        "current_price": 67000.0,
        "market_cap": 1_320_000_000_000,
        "total_volume": 25_000_000_000,
        "circulating_supply": 19_700_000,
        "price_change_percentage_1h_in_currency": 0.4,
        "price_change_percentage_24h_in_currency": 2.1,
        "price_change_percentage_7d_in_currency": -1.3,
        "sparkline_in_7d": {"price": [66000.0, 66500.0, 67000.0]},
    }


@pytest.fixture()
def coingecko_global() -> dict:
    return {
        "data": {
            "total_market_cap": {"usd": 2_400_000_000_000},
            "total_volume": {"usd": 90_000_000_000},
            "market_cap_percentage": {"btc": 55.0, "eth": 17.0},
            "market_cap_change_percentage_24h_usd": 1.2,
            "active_cryptocurrencies": 15000,
        }
    }
