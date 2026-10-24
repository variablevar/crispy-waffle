"""Liquidity intelligence engine.

Observed facts (order-book walls, concentration, imbalance) are kept strictly
separate from ESTIMATED liquidation clusters derived from leverage proxies
(open interest x typical leverage buckets mapped to price offsets). Every
estimated zone is labelled as an estimate — never presented as observed.
"""

from __future__ import annotations

import statistics
from typing import Any, Optional

WALL_MULTIPLE = 3.0  # size_usd > N x median level size => wall
DISCLAIMER = (
    "Walls and imbalances are OBSERVED from live order-book snapshots. "
    "Liquidation clusters are ESTIMATES from a model that maps open interest "
    "x typical leverage buckets (5x/10x/25x/50x) to price offsets; they are "
    "not observed liquidation levels and must not be treated as fact."
)

LEVERAGE_BUCKETS = (5.0, 10.0, 25.0, 50.0)
# fraction of OI assumed concentrated in each leverage bucket
BUCKET_WEIGHTS = (0.15, 0.30, 0.35, 0.20)


def _level_usd(level: list) -> float:
    return float(level[0]) * float(level[1])


def detect_walls(
    bids: list[list], asks: list[list], exchange: str, multiple: float = WALL_MULTIPLE
) -> dict[str, list[dict[str, Any]]]:
    """Levels whose size_usd exceeds `multiple` x the median level size."""
    out = {"bids": [], "asks": []}
    for side, levels in (("bids", bids), ("asks", asks)):
        if not levels:
            continue
        sizes = [_level_usd(l) for l in levels]
        median = statistics.median(sizes) if sizes else 0.0
        if median <= 0:
            continue
        threshold = multiple * median
        for level, size in zip(levels, sizes):
            if size > threshold:
                out[side].append(
                    {"price": float(level[0]), "size_usd": round(size, 2), "exchange": exchange}
                )
    return out


def depth_imbalance(bids: list[list], asks: list[list], depth: int = 20) -> Optional[float]:
    bid_usd = sum(_level_usd(l) for l in bids[:depth]) if bids else 0.0
    ask_usd = sum(_level_usd(l) for l in asks[:depth]) if asks else 0.0
    total = bid_usd + ask_usd
    if total <= 0:
        return None
    return round(max(-1.0, min(1.0, (bid_usd - ask_usd) / total)), 4)


def concentration(
    bids: list[list], asks: list[list], mid_price: float, pct: float = 0.02
) -> dict[str, float]:
    """Share of book depth within +/-pct of mid price (0..1 per side)."""
    out = {"bids": 0.0, "asks": 0.0}
    if mid_price <= 0:
        return out
    for side, levels in (("bids", bids), ("asks", asks)):
        total = sum(_level_usd(l) for l in levels) or 0.0
        if total <= 0:
            continue
        near = sum(
            _level_usd(l) for l in levels if abs(float(l[0]) - mid_price) / mid_price <= pct
        )
        out[side] = round(near / total, 4)
    return out


def estimated_liquidation_clusters(
    mid_price: float, open_interest_usd: float, source: str = "estimation_model"
) -> list[dict[str, Any]]:
    """ESTIMATED liquidation clusters from OI x leverage buckets.

    Longs opened near the current price get liquidated at roughly
    price * (1 - 1/leverage); shorts at price * (1 + 1/leverage).
    """
    if mid_price <= 0 or open_interest_usd <= 0:
        return []
    zones: list[dict[str, Any]] = []
    for lev, weight in zip(LEVERAGE_BUCKETS, BUCKET_WEIGHTS):
        size = open_interest_usd * weight
        offset = 1.0 / lev
        for direction in ("long", "short"):
            centre = mid_price * (1 - offset) if direction == "long" else mid_price * (1 + offset)
            width = mid_price * offset * 0.15  # narrow band around the estimate
            zones.append(
                {
                    "price_low": round(centre - width, 8),
                    "price_high": round(centre + width, 8),
                    "type": "estimated_liquidation",
                    "strength": round(min(1.0, weight * 3), 3),
                    "size_usd": round(size, 2),
                    "exchange": None,
                    "label": f"ESTIMATED — {direction} liquidation cluster (~{int(lev)}x leverage bucket)",
                    "source": source,
                }
            )
    return zones


def support_resistance_estimates(
    bids: list[list], asks: list[list], mid_price: float, walls: dict[str, list]
) -> list[dict[str, Any]]:
    """Derive estimated support/resistance zones from observed walls."""
    zones: list[dict[str, Any]] = []
    for wall in walls.get("bids", []):
        price = wall["price"]
        if price < mid_price:
            zones.append(
                {
                    "price_low": round(price * 0.998, 8),
                    "price_high": round(price * 1.002, 8),
                    "type": "estimated_support",
                    "strength": 0.6,
                    "size_usd": wall["size_usd"],
                    "exchange": wall["exchange"],
                    "label": "ESTIMATED support — derived from observed bid wall",
                    "source": "estimation_model",
                }
            )
    for wall in walls.get("asks", []):
        price = wall["price"]
        if price > mid_price:
            zones.append(
                {
                    "price_low": round(price * 0.998, 8),
                    "price_high": round(price * 1.002, 8),
                    "type": "estimated_resistance",
                    "strength": 0.6,
                    "size_usd": wall["size_usd"],
                    "exchange": wall["exchange"],
                    "label": "ESTIMATED resistance — derived from observed ask wall",
                    "source": "estimation_model",
                }
            )
    return zones


def wall_zones(walls: dict[str, list], mid_price: float) -> list[dict[str, Any]]:
    """Observed walls as zones (observed_bid_wall / observed_ask_wall)."""
    zones = []
    max_size = max(
        (w["size_usd"] for side in ("bids", "asks") for w in walls.get(side, [])), default=0.0
    )
    for side, ztype in (("bids", "observed_bid_wall"), ("asks", "observed_ask_wall")):
        for wall in walls.get(side, []):
            zones.append(
                {
                    "price_low": round(wall["price"] * 0.999, 8),
                    "price_high": round(wall["price"] * 1.001, 8),
                    "type": ztype,
                    "strength": round(wall["size_usd"] / max_size, 3) if max_size else 0.5,
                    "size_usd": wall["size_usd"],
                    "exchange": wall["exchange"],
                    "label": f"Observed {'bid' if side == 'bids' else 'ask'} wall on {wall['exchange']}",
                    "source": f"{wall['exchange']}_orderbook",
                }
            )
    return zones


def detect_sweep(
    price_series: list,
    zones: list[dict[str, Any]],
    tolerance_bps: float = 15,
    lookahead: int = 10,
) -> list[dict[str, Any]]:
    """Detect liquidity sweeps: price crosses a zone edge then closes back
    inside within `lookahead` bars.

    price_series: ordered [(ts, price), ...] or [{time, price}, ...].
    zones: dicts with price_low / price_high (from wall_zones etc.).
    Returns [{time, direction, price, zone}] where direction is "down" (swept
    below price_low and reclaimed) or "up" (swept above price_high and
    rejected back), and price is the excursion extreme.
    """
    points: list[tuple[float, float]] = []
    for p in price_series:
        if isinstance(p, dict):
            ts, px = float(p.get("time", 0) or 0), float(p.get("price", 0) or 0)
        else:
            ts, px = float(p[0]), float(p[1])
        if px > 0:
            points.append((ts, px))
    sweeps: list[dict[str, Any]] = []
    for zone in zones:
        try:
            lo, hi = float(zone["price_low"]), float(zone["price_high"])
        except (KeyError, TypeError, ValueError):
            continue
        if lo <= 0 or hi <= 0 or hi < lo:
            continue
        i = 0
        while i < len(points):
            ts, px = points[i]
            tol_dn = lo * tolerance_bps / 1e4
            tol_up = hi * tolerance_bps / 1e4
            if px < lo - tol_dn:
                # wick below the zone — look for a reclaim of price_low
                extreme = px
                j = i
                while j < min(len(points), i + lookahead + 1):
                    extreme = min(extreme, points[j][1])
                    if points[j][1] >= lo:
                        sweeps.append(
                            {"time": points[j][0], "direction": "down", "price": extreme, "zone": zone}
                        )
                        i = j
                        break
                    j += 1
            elif px > hi + tol_up:
                extreme = px
                j = i
                while j < min(len(points), i + lookahead + 1):
                    extreme = max(extreme, points[j][1])
                    if points[j][1] <= hi:
                        sweeps.append(
                            {"time": points[j][0], "direction": "up", "price": extreme, "zone": zone}
                        )
                        i = j
                        break
                    j += 1
            i += 1
    return sweeps


def detect_withdrawals(
    prev_book: list[list], cur_book: list[list], threshold_pct: float = 50
) -> list[dict[str, Any]]:
    """Order-book levels whose resting size dropped sharply between snapshots.

    prev_book / cur_book: one side of a book as [[price, qty], ...]. A level
    counts as withdrawn when its size fell by >= threshold_pct (a level absent
    from cur_book counts as a 100% drop). Returns
    [{price, prev_size, cur_size, drop_pct}] sorted by drop_pct desc.
    """
    cur_sizes: dict[float, float] = {}
    for level in cur_book or []:
        try:
            cur_sizes[float(level[0])] = float(level[1])
        except (TypeError, ValueError, IndexError):
            continue
    out: list[dict[str, Any]] = []
    for level in prev_book or []:
        try:
            price, prev_size = float(level[0]), float(level[1])
        except (TypeError, ValueError, IndexError):
            continue
        if prev_size <= 0:
            continue
        cur_size = cur_sizes.get(price, 0.0)
        drop_pct = (prev_size - cur_size) / prev_size * 100.0
        if drop_pct >= threshold_pct:
            out.append(
                {
                    "price": price,
                    "prev_size": prev_size,
                    "cur_size": cur_size,
                    "drop_pct": round(drop_pct, 2),
                }
            )
    out.sort(key=lambda w: -w["drop_pct"])
    return out


def build_heatmap(
    snapshots: list[tuple[float, list[list], list[list]]], n_price_buckets: int = 20
) -> Optional[dict[str, Any]]:
    """Heatmap grid from recent depth snapshots.

    snapshots: list of (ts, bids, asks). Returns price_points, time_points,
    intensity (rows=price buckets, cols=time points) — or None when there is
    not enough history.
    """
    if len(snapshots) < 2:
        return None
    prices = [float(l[0]) for _, bids, asks in snapshots for l in (bids + asks)]
    if not prices:
        return None
    lo, hi = min(prices), max(prices)
    if hi <= lo:
        return None
    step = (hi - lo) / n_price_buckets
    price_points = [round(lo + (i + 0.5) * step, 8) for i in range(n_price_buckets)]
    time_points = [int(ts) for ts, _, _ in snapshots]
    intensity = [[0.0 for _ in snapshots] for _ in range(n_price_buckets)]
    for col, (_, bids, asks) in enumerate(snapshots):
        for level in bids + asks:
            price, qty = float(level[0]), float(level[1])
            row = min(n_price_buckets - 1, max(0, int((price - lo) / step)))
            intensity[row][col] += price * qty
    # normalize to 0..1
    max_v = max((v for row in intensity for v in row), default=0.0)
    if max_v > 0:
        intensity = [[round(v / max_v, 4) for v in row] for row in intensity]
    return {"price_points": price_points, "time_points": time_points, "intensity": intensity}
