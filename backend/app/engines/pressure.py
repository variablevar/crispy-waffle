"""Buy/sell pressure engine.

Uses ONLY aggressive taker flow (Binance aggTrades `m` flag / taker volume
endpoints) and observed order-book depth. It never infers "more buyers than
sellers" — every filled trade has both; what is measured is which side was
the aggressor.
"""

from __future__ import annotations

import time as time_mod
from typing import Any, Optional

METHODOLOGY = (
    "Pressure is measured from aggressive taker flow only: Binance aggTrades "
    "classify each trade by whether the buyer was the maker (m=true => the "
    "aggressor was a SELLER). taker_buy_volume / taker_sell_volume sum quote "
    "USDT on each aggressor side within each window. CVD is the running "
    "difference (buy - sell). book_imbalance is depth-weighted top-of-book "
    "imbalance in -1..1 from observed resting orders. This says nothing about "
    "the total number of buyers vs sellers — every trade has both."
)

CONFIDENCE_HIGH_TRADES = 500
CONFIDENCE_MEDIUM_TRADES = 100


def split_taker_flow(trades: list[dict[str, Any]]) -> tuple[float, float]:
    """Split aggTrades into (taker_buy_quote, taker_sell_quote).

    Binance aggTrade: m=True means the buyer is the maker, i.e. the aggressor
    sold. Accepts dicts with keys p/q/m/T (raw binance) or normalized
    price/qty/is_buyer_maker/time.
    """
    buy = 0.0
    sell = 0.0
    for t in trades:
        price = float(t.get("p", t.get("price", 0)) or 0)
        qty = float(t.get("q", t.get("qty", 0)) or 0)
        is_buyer_maker = t.get("m", t.get("is_buyer_maker"))
        quote = price * qty
        if is_buyer_maker:
            sell += quote
        else:
            buy += quote
    return buy, sell


def taker_ratio(buy: float, sell: float) -> Optional[float]:
    if sell <= 0:
        return None
    return round(buy / sell, 4)


def compute_cvd(trades: list[dict[str, Any]], bucket_sec: int = 60) -> list[dict[str, Any]]:
    """Cumulative volume delta series, bucketed. Trades may be in any order."""
    buckets: dict[int, float] = {}
    for t in trades:
        ts_ms = t.get("T", t.get("time", 0))
        ts = int(ts_ms / 1000) if ts_ms > 1e12 else int(ts_ms)
        bucket = ts - (ts % bucket_sec)
        price = float(t.get("p", t.get("price", 0)) or 0)
        qty = float(t.get("q", t.get("qty", 0)) or 0)
        is_buyer_maker = t.get("m", t.get("is_buyer_maker"))
        delta = -price * qty if is_buyer_maker else price * qty
        buckets[bucket] = buckets.get(bucket, 0.0) + delta
    series = []
    cumulative = 0.0
    for ts in sorted(buckets):
        cumulative += buckets[ts]
        series.append({"time": ts, "value": round(cumulative, 2)})
    return series


def book_imbalance(bids: list[list], asks: list[list], depth: int = 10) -> Optional[float]:
    """Depth-weighted top-of-book imbalance in -1..1.

    +1 = all resting size on bids, -1 = all on asks. None when the book side
    is empty.
    """
    bid_usd = sum(float(p) * float(q) for p, q, *_ in bids[:depth]) if bids else 0.0
    ask_usd = sum(float(p) * float(q) for p, q, *_ in asks[:depth]) if asks else 0.0
    total = bid_usd + ask_usd
    if total <= 0:
        return None
    return round(max(-1.0, min(1.0, (bid_usd - ask_usd) / total)), 4)


def timeframe_windows(
    trades: list[dict[str, Any]], windows: dict[str, int] | None = None, now: float | None = None
) -> dict[str, dict[str, Any]]:
    """Per-timeframe taker flow. windows maps label -> window seconds."""
    windows = windows or {"15m": 900, "1h": 3600, "4h": 14400}
    now = now if now is not None else time_mod.time()
    out: dict[str, dict[str, Any]] = {}
    for label, span in windows.items():
        cutoff_ms = (now - span) * 1000
        window_trades = [
            t for t in trades if float(t.get("T", t.get("time", 0)) or 0) >= cutoff_ms
        ]
        if not window_trades:
            out[label] = {"buy": None, "sell": None, "ratio": None}
            continue
        buy, sell = split_taker_flow(window_trades)
        out[label] = {
            "buy": round(buy, 2),
            "sell": round(sell, 2),
            "ratio": taker_ratio(buy, sell),
        }
    return out


def volume_acceleration(
    trades: list[dict[str, Any]], window_sec: int = 300, now: float | None = None
) -> Optional[float]:
    """Ratio of taker quote volume in the most recent `window_sec` vs the
    immediately preceding window of equal length.

    Quote volume sums BOTH aggressor sides (buy + sell) — this measures
    activity acceleration, not direction. Returns None when the preceding
    window has no volume (insufficient data to compare against).
    Trade timestamps may be unix seconds or milliseconds.
    """
    if not trades:
        return None
    now = now if now is not None else time_mod.time()
    recent_cutoff = now - window_sec
    prior_cutoff = now - 2 * window_sec
    recent_vol = 0.0
    prior_vol = 0.0
    for t in trades:
        ts = float(t.get("T", t.get("time", 0)) or 0)
        if ts > 1e12:
            ts /= 1000.0
        if ts < prior_cutoff:
            continue
        price = float(t.get("p", t.get("price", 0)) or 0)
        qty = float(t.get("q", t.get("qty", 0)) or 0)
        if ts >= recent_cutoff:
            recent_vol += price * qty
        else:
            prior_vol += price * qty
    if prior_vol <= 0:
        return None
    return round(recent_vol / prior_vol, 4)


def confidence_label(n_trades: int, has_book: bool) -> str:
    if n_trades >= CONFIDENCE_HIGH_TRADES and has_book:
        return "high"
    if n_trades >= CONFIDENCE_MEDIUM_TRADES:
        return "medium"
    return "low"


def build_report(
    symbol: str,
    *,
    spot_trades: list[dict[str, Any]] | None,
    perp_trades: list[dict[str, Any]] | None,
    bids: list[list] | None,
    asks: list[list] | None,
    updated_at: str | None,
    stale: bool,
    now: float | None = None,
) -> dict[str, Any]:
    """Assemble the contract PressureReport from raw inputs (None = unavailable)."""
    trades = spot_trades or []
    has_data = bool(trades) or bool(perp_trades)

    if trades:
        buy, sell = split_taker_flow(trades)
        ratio = taker_ratio(buy, sell)
        cvd = compute_cvd(trades)
        tfs = timeframe_windows(trades, now=now)
    else:
        buy = sell = ratio = None
        cvd = []
        tfs = {k: {"buy": None, "sell": None, "ratio": None} for k in ("15m", "1h", "4h")}

    imb = book_imbalance(bids or [], asks or []) if (bids and asks) else None

    spot_ratio = None
    futures_ratio = None
    if trades:
        b, s = split_taker_flow(trades)
        spot_ratio = taker_ratio(b, s)
    if perp_trades:
        b, s = split_taker_flow(perp_trades)
        futures_ratio = taker_ratio(b, s)

    return {
        "symbol": symbol.upper(),
        "taker_buy_volume": round(buy, 2) if buy is not None else None,
        "taker_sell_volume": round(sell, 2) if sell is not None else None,
        "taker_ratio": ratio,
        "cvd": cvd,
        "book_imbalance": imb,
        "spot_vs_futures": {"spot_ratio": spot_ratio, "futures_ratio": futures_ratio},
        "timeframes": tfs,
        "methodology": METHODOLOGY,
        "confidence": confidence_label(len(trades), imb is not None) if has_data else "low",
        "available": has_data,
        "updated_at": updated_at,
        "stale": stale,
    }
