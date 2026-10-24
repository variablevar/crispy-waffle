"""Cross-product analytics: venue comparison, BTC/ETH divergence,
spot-vs-perp pressure. Pure functions over observed inputs — None-safe,
never fabricate.
"""

from __future__ import annotations

from typing import Any, Optional

FUNDING_EPS = 1e-6  # funding rates within +/-eps count as neutral
DIVERGENCE_THRESHOLD_PCT = 3.0


def compare_venues(tickers: list[dict[str, Any]]) -> dict[str, Any]:
    """Pairwise venue comparison per instrument.

    tickers: [{venue, instrument, symbol, price, funding_rate, open_interest}]
    (missing fields allowed). Returns {"pairs": [{venues, instrument,
    price_a, price_b, spread_bps, funding_gap, oi_gap_pct, agreeing}]}.

    `agreeing`: True/False when both venues report funding and the signs
    agree/disagree (both near-zero counts as agreeing); None when there is
    not enough data to judge.
    """
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for t in tickers or []:
        venue, instrument = t.get("venue"), t.get("instrument")
        if not venue or not instrument:
            continue
        by_key.setdefault((str(t.get("symbol", "")).upper(), instrument), []).append(t)

    pairs: list[dict[str, Any]] = []
    for (symbol, instrument), rows in sorted(by_key.items()):
        rows = sorted(rows, key=lambda r: r.get("venue", ""))
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                price_a, price_b = a.get("price"), b.get("price")
                spread_bps = None
                if price_a and price_b and price_a > 0 and price_b > 0:
                    mid = (float(price_a) + float(price_b)) / 2.0
                    spread_bps = round((float(price_a) - float(price_b)) / mid * 1e4, 3)
                fa, fb = a.get("funding_rate"), b.get("funding_rate")
                funding_gap = None
                agreeing: Optional[bool] = None
                if fa is not None and fb is not None:
                    funding_gap = round(float(fa) - float(fb), 8)
                    a_dir = 0 if abs(fa) < FUNDING_EPS else (1 if fa > 0 else -1)
                    b_dir = 0 if abs(fb) < FUNDING_EPS else (1 if fb > 0 else -1)
                    agreeing = a_dir == b_dir or 0 in (a_dir, b_dir)
                oia, oib = a.get("open_interest"), b.get("open_interest")
                oi_gap_pct = None
                if oia and oib and (float(oia) + float(oib)) > 0:
                    avg = (float(oia) + float(oib)) / 2.0
                    oi_gap_pct = round((float(oia) - float(oib)) / avg * 100.0, 3)
                pairs.append(
                    {
                        "venues": [a.get("venue"), b.get("venue")],
                        "symbol": symbol,
                        "instrument": instrument,
                        "price_a": price_a,
                        "price_b": price_b,
                        "spread_bps": spread_bps,
                        "funding_gap": funding_gap,
                        "oi_gap_pct": oi_gap_pct,
                        "agreeing": agreeing,
                    }
                )
    return {"pairs": pairs}


def btc_eth_divergence(
    btc_change_24h: Optional[float],
    eth_change_24h: Optional[float],
    threshold_pct: float = DIVERGENCE_THRESHOLD_PCT,
) -> Optional[dict[str, Any]]:
    """BTC vs ETH 24h-change divergence. None when either input is missing."""
    if btc_change_24h is None or eth_change_24h is None:
        return None
    gap = float(btc_change_24h) - float(eth_change_24h)
    diverging = abs(gap) >= threshold_pct
    if diverging:
        leader = "BTC" if gap > 0 else "ETH"
        note = f"BTC and ETH diverging ({gap:+.1f}pp over 24h); {leader} leading"
    else:
        note = "BTC and ETH moving together (normal high correlation)"
    return {
        "correlation_note": note,
        "btc_change_24h": btc_change_24h,
        "eth_change_24h": eth_change_24h,
        "diverging": diverging,
    }


def spot_vs_perp_pressure(
    spot_report: Optional[dict[str, Any]], perp_ratio: Optional[float]
) -> Optional[dict[str, Any]]:
    """Compare spot taker ratio (from a PressureReport) with the perp taker
    ratio. Divergence = aggressor sides disagree (one above 1, the other
    below). None when neither side is observed."""
    spot_ratio = None
    if spot_report:
        spot_ratio = spot_report.get("taker_ratio")
    if spot_ratio is None and perp_ratio is None:
        return None
    divergence: Optional[bool] = None
    note = "insufficient data to compare spot and perp pressure"
    if spot_ratio is not None and perp_ratio is not None:
        divergence = (spot_ratio - 1.0) * (perp_ratio - 1.0) < 0
        if divergence:
            heavier = "spot" if spot_ratio > perp_ratio else "perp"
            note = f"Spot and perp aggressor flow disagree; {heavier} side buying harder"
        else:
            note = "Spot and perp aggressor flow aligned"
    return {
        "spot_ratio": spot_ratio,
        "perp_ratio": perp_ratio,
        "divergence": divergence,
        "note": note,
    }
