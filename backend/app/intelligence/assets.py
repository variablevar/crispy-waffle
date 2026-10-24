"""Asset-level intelligence: the shared computation behind both the public
dashboard coin routes and the agent API. Every function returns the exact
dict shape the public API has always returned."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal, Optional

from app.api import deps
from app.core.cache import get_cache
from app.core.state import get_live_state
from app.engines import liquidity as liq_engine
from app.engines import pressure as pressure_engine
from app.engines import scenarios as scenario_engine
from app.engines import scenarios_v2 as scenario_engine_v2
from app.engines import sentiment as sentiment_engine
from app.services import binance_rest, bybit_rest, coingecko, coinglass, defillama, dexscreener, feargreed, iso
from app.services.news import get_aggregator

_TF_TO_BINANCE = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"}
_TF_TO_CG_DAYS = {"15m": 1, "1h": 30, "4h": 90, "1d": 180, "1w": 360}
_TF_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def binance_klines_to_candles(raw: list[list]) -> list[dict[str, Any]]:
    candles = []
    for k in raw:
        candles.append(
            {
                "time": int(k[0]) // 1000,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            }
        )
    return candles


def cg_chart_to_candles(data: dict, tf_seconds: int) -> list[dict[str, Any]]:
    prices = data.get("prices") or []
    volumes = {int(v[0]): float(v[1]) for v in (data.get("total_volumes") or [])}
    buckets: dict[int, dict[str, Any]] = {}
    for ms, price in prices:
        ts = int(ms) // 1000
        bucket = ts - (ts % tf_seconds)
        c = buckets.get(bucket)
        if c is None:
            buckets[bucket] = {
                "time": bucket,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0.0,
            }
        else:
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price
    vol_buckets: dict[int, float] = {}
    for ms, vol in volumes.items():
        ts = ms // 1000
        bucket = ts - (ts % tf_seconds)
        vol_buckets[bucket] = vol_buckets.get(bucket, 0.0) + vol
    for ts, candle in buckets.items():
        candle["volume"] = round(vol_buckets.get(ts, 0.0), 2)
    return [buckets[ts] for ts in sorted(buckets)]


async def best_price(symbol: str) -> Optional[float]:
    """Live WS price first, then cached 24h tickers."""
    state = get_live_state()
    for exch in ("binance", "bybit"):
        live = state.get_price(exch, symbol)
        if live and time.time() - live.get("ts", 0) < 120:
            return float(live["price"])
    entry = await get_cache().get_entry(f"bn:ticker:spot:{symbol.upper()}USDT")
    if entry and isinstance(entry.value, dict):
        try:
            return float(entry.value["lastPrice"])
        except (KeyError, TypeError, ValueError):
            pass
    return None


def ticker_out(
    exchange: str,
    instrument: str,
    pair: str,
    *,
    price=None,
    bid=None,
    ask=None,
    volume_24h=None,
    funding_rate=None,
    open_interest=None,
    updated_at=None,
    stale=False,
) -> dict[str, Any]:
    spread_bps = None
    if bid and ask and bid > 0:
        mid = (bid + ask) / 2
        spread_bps = round((ask - bid) / mid * 10_000, 2)
    return {
        "exchange": exchange,
        "instrument": instrument,
        "symbol": pair,
        "price": price,
        "bid": bid,
        "ask": ask,
        "spread_bps": spread_bps,
        "volume_24h": volume_24h,
        "funding_rate": funding_rate,
        "open_interest": open_interest,
        "updated_at": updated_at,
        "stale": stale,
    }


def to_f(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# facade functions (one per intelligence product)
# ---------------------------------------------------------------------------


async def get_coin_detail(symbol: str) -> dict[str, Any]:
    info = deps.symbol_or_404(symbol)
    detail_res, markets_res = await asyncio.gather(
        coingecko.coin_detail(info.coingecko_id), coingecko.top_markets(limit=250)
    )
    market_row = None
    if markets_res.available and isinstance(markets_res.value, list):
        for c in markets_res.value:
            if c.get("id") == info.coingecko_id:
                market_row = c
                break

    if not detail_res.available or not isinstance(detail_res.value, dict):
        if market_row is not None:
            base = deps.coin_summary_from_market(
                market_row, updated_at=markets_res.updated_at, stale=True
            )
            base.update(
                {
                    "description": None,
                    "ath": None,
                    "atl": None,
                    "ath_change_pct": None,
                    "total_volume": market_row.get("total_volume"),
                    "market_cap_rank": market_row.get("market_cap_rank"),
                    "homepage": None,
                    "available": True,
                }
            )
            return base
        return {
            **{k: None for k in ("price", "change_1h", "change_24h", "change_7d", "market_cap",
                                 "volume_24h", "circulating_supply", "dominance", "description",
                                 "ath", "atl", "ath_change_pct", "total_volume", "market_cap_rank",
                                 "homepage", "sentiment", "image")},
            "id": info.coingecko_id,
            "symbol": info.symbol,
            "name": info.name,
            "sparkline": [],
            "trend": "neutral",
            "news_count_24h": 0,
            "available": False,
            "updated_at": None,
            "stale": False,
        }

    d = detail_res.value
    md = d.get("market_data") or {}
    pct = md.get("price_change_percentage_1h_in_currency") or {}
    pct24 = md.get("price_change_percentage_24h_in_currency") or {}
    pct7d = md.get("price_change_percentage_7d_in_currency") or {}
    coin_like = {
        "id": d.get("id"),
        "symbol": (d.get("symbol") or info.symbol).upper(),
        "name": d.get("name"),
        "image": (d.get("image") or {}).get("large") or (d.get("image") or {}).get("small"),
        "current_price": (md.get("current_price") or {}).get("usd"),
        "price_change_percentage_1h_in_currency": pct.get("usd"),
        "price_change_percentage_24h_in_currency": pct24.get("usd"),
        "price_change_percentage_7d_in_currency": pct7d.get("usd"),
        "market_cap": (md.get("market_cap") or {}).get("usd"),
        "total_volume": (md.get("total_volume") or {}).get("usd"),
        "circulating_supply": md.get("circulating_supply"),
        "sparkline_in_7d": md.get("sparkline_7d"),
        "market_cap_rank": d.get("market_cap_rank"),
    }
    base = deps.coin_summary_from_market(
        coin_like, updated_at=detail_res.updated_at, stale=detail_res.stale
    )
    homepage = None
    links = d.get("links") or {}
    if links.get("homepage"):
        homepage = next((h for h in links["homepage"] if h), None)
    base.update(
        {
            "description": ((d.get("description") or {}).get("en") or None),
            "ath": (md.get("ath") or {}).get("usd"),
            "atl": (md.get("atl") or {}).get("usd"),
            "ath_change_pct": (md.get("ath_change_percentage") or {}).get("usd"),
            "total_volume": (md.get("total_volume") or {}).get("usd"),
            "market_cap_rank": d.get("market_cap_rank"),
            "homepage": homepage,
            "available": True,
        }
    )
    return base


async def get_chart(
    symbol: str,
    timeframe: Literal["15m", "1h", "4h", "1d", "1w"] = "1h",
    source: Literal["auto", "binance", "coingecko"] = "auto",
) -> dict[str, Any]:
    info = deps.symbol_or_404(symbol)
    pair = info.binance_spot_pair

    if source in ("auto", "binance"):
        res = await binance_rest.klines(pair, _TF_TO_BINANCE[timeframe], limit=200)
        if res.available and isinstance(res.value, list):
            return {
                "candles": binance_klines_to_candles(res.value),
                "source": "binance_spot",
                "available": True,
                "updated_at": res.updated_at,
                "stale": res.stale,
            }
        if source == "binance":
            return {"candles": [], "source": "binance_spot", "available": False, "updated_at": None, "stale": False}

    res = await coingecko.market_chart(info.coingecko_id, _TF_TO_CG_DAYS[timeframe])
    if res.available and isinstance(res.value, dict):
        return {
            "candles": cg_chart_to_candles(res.value, _TF_SECONDS[timeframe]),
            "source": "coingecko",
            "available": True,
            "updated_at": res.updated_at,
            "stale": res.stale,
        }
    return {"candles": [], "source": "none", "available": False, "updated_at": None, "stale": False}


async def get_tickers(symbol: str) -> dict[str, Any]:
    info = deps.symbol_or_404(symbol)
    pair = info.binance_spot_pair
    (
        bn_spot_t,
        bn_spot_book,
        bn_perp_t,
        bn_perp_book,
        bn_premium,
        bn_oi,
        bb_spot,
        bb_linear,
    ) = await asyncio.gather(
        binance_rest.ticker_24h(pair, "spot"),
        binance_rest.book_ticker(pair, "spot"),
        binance_rest.ticker_24h(pair, "perp"),
        binance_rest.book_ticker(pair, "perp"),
        binance_rest.premium_index(pair),
        binance_rest.open_interest(pair),
        bybit_rest.tickers(pair, "spot"),
        bybit_rest.tickers(pair, "linear"),
    )

    items: list[dict[str, Any]] = []

    if bn_spot_t.available and isinstance(bn_spot_t.value, dict):
        t = bn_spot_t.value
        book = bn_spot_book.value if bn_spot_book.available and isinstance(bn_spot_book.value, dict) else {}
        items.append(
            ticker_out(
                "binance", "spot", pair,
                price=to_f(t.get("lastPrice")),
                bid=to_f(book.get("bidPrice")),
                ask=to_f(book.get("askPrice")),
                volume_24h=to_f(t.get("quoteVolume")),
                updated_at=bn_spot_t.updated_at,
                stale=bn_spot_t.stale or bn_spot_book.stale,
            )
        )
    if bn_perp_t.available and isinstance(bn_perp_t.value, dict):
        t = bn_perp_t.value
        book = bn_perp_book.value if bn_perp_book.available and isinstance(bn_perp_book.value, dict) else {}
        premium = bn_premium.value if bn_premium.available and isinstance(bn_premium.value, dict) else {}
        oi = bn_oi.value if bn_oi.available and isinstance(bn_oi.value, dict) else {}
        items.append(
            ticker_out(
                "binance", "usdt_perp", pair,
                price=to_f(t.get("lastPrice")),
                bid=to_f(book.get("bidPrice")),
                ask=to_f(book.get("askPrice")),
                volume_24h=to_f(t.get("quoteVolume")),
                funding_rate=to_f(premium.get("lastFundingRate")),
                open_interest=to_f(oi.get("openInterest")),
                updated_at=bn_perp_t.updated_at,
                stale=any(r.stale for r in (bn_perp_t, bn_perp_book, bn_premium, bn_oi)),
            )
        )
    for res, category, instrument in ((bb_spot, "spot", "spot"), (bb_linear, "linear", "usdt_perp")):
        if res.available and isinstance(res.value, list) and res.value:
            t = res.value[0]
            items.append(
                ticker_out(
                    "bybit", instrument, pair,
                    price=to_f(t.get("lastPrice")),
                    bid=to_f(t.get("bid1Price")),
                    ask=to_f(t.get("ask1Price")),
                    volume_24h=to_f(t.get("turnover24h")),
                    funding_rate=to_f(t.get("fundingRate")) if instrument == "usdt_perp" else None,
                    open_interest=to_f(t.get("openInterest")) if instrument == "usdt_perp" else None,
                    updated_at=res.updated_at,
                    stale=res.stale,
                )
            )

    updated = max((i["updated_at"] for i in items if i["updated_at"]), default=None)
    return deps.list_wrapper(
        items, ["binance", "bybit"], updated, any(i["stale"] for i in items), available=bool(items)
    )


async def get_pressure(symbol: str) -> dict[str, Any]:
    info = deps.symbol_or_404(symbol)
    pair = info.binance_spot_pair
    spot_trades, perp_trades, depth = await asyncio.gather(
        binance_rest.agg_trades(pair, limit=1000, market="spot"),
        binance_rest.agg_trades(pair, limit=500, market="perp"),
        binance_rest.depth(pair, limit=20, market="spot"),
    )

    bids = asks = None
    if depth.available and isinstance(depth.value, dict):
        bids = depth.value.get("bids")
        asks = depth.value.get("asks")

    results = [r for r in (spot_trades, perp_trades, depth) if r.available]
    updated = max((r.updated_at for r in results if r.updated_at), default=None)
    stale = any(r.stale for r in results) if results else False

    report = pressure_engine.build_report(
        info.symbol,
        spot_trades=spot_trades.value if spot_trades.available else None,
        perp_trades=perp_trades.value if perp_trades.available else None,
        bids=bids,
        asks=asks,
        updated_at=updated,
        stale=stale,
    )
    if spot_trades.available and isinstance(spot_trades.value, list) and spot_trades.value:
        report["volume_acceleration"] = pressure_engine.volume_acceleration(spot_trades.value)
    else:
        report["volume_acceleration"] = None
    return report


async def _liquidations_block(symbol: str) -> dict[str, Any]:
    state = get_live_state()
    recent = []
    for exch_key, exch_name in (("binance_perp_liq", "binance"), ("bybit_perp_liq", "bybit")):
        for t in state.recent_trades(exch_key, symbol):
            ts = t.get("time") or 0
            recent.append(
                {
                    "time": int(ts // 1000) if ts > 1e12 else int(ts),
                    "side": t.get("side", "unknown"),
                    "size_usd": round(float(t.get("size_usd") or 0), 2),
                    "exchange": exch_name,
                }
            )
    if coinglass.available():
        res = await coinglass.liquidation_history(symbol)
        if res.available:
            return {
                "available": True,
                "source": "coinglass",
                "note": "Observed liquidation data from CoinGlass.",
                "recent": recent[-50:],
            }
    if recent:
        return {
            "available": True,
            "source": "exchange_ws_streams",
            "note": "Observed liquidation orders from exchange public streams (partial coverage — streams may restart).",
            "recent": sorted(recent, key=lambda r: r["time"])[-50:],
        }
    return {
        "available": False,
        "source": "none",
        "note": "No liquidation feed available (Binance force-orders REST requires auth; CoinGlass key not configured). See /liquidity for the labelled estimation model.",
        "recent": [],
    }


async def get_derivatives(symbol: str) -> dict[str, Any]:
    info = deps.symbol_or_404(symbol)
    pair = info.binance_spot_pair
    (
        premium,
        oi_bn,
        ls_bn,
        funding_hist_bn,
        bb_linear,
        bb_funding,
        bb_oi,
        bb_ls,
        spot_t,
        perp_t,
    ) = await asyncio.gather(
        binance_rest.premium_index(pair),
        binance_rest.open_interest(pair),
        binance_rest.global_long_short_ratio(pair),
        binance_rest.funding_history(pair),
        bybit_rest.tickers(pair, "linear"),
        bybit_rest.funding_history(pair),
        bybit_rest.open_interest(pair),
        bybit_rest.long_short_ratio(pair),
        binance_rest.ticker_24h(pair, "spot"),
        binance_rest.ticker_24h(pair, "perp"),
    )

    funding_binance = to_f((premium.value or {}).get("lastFundingRate")) if premium.available else None
    bb_t = bb_linear.value[0] if bb_linear.available and isinstance(bb_linear.value, list) and bb_linear.value else {}
    funding_bybit = to_f(bb_t.get("fundingRate"))
    oi_binance = to_f((oi_bn.value or {}).get("openInterest")) if oi_bn.available else None
    oi_bybit = to_f(bb_t.get("openInterest"))

    funding_history = []
    if funding_hist_bn.available and isinstance(funding_hist_bn.value, list):
        for f in funding_hist_bn.value:
            funding_history.append(
                {"time": int(f["fundingTime"]) // 1000, "exchange": "binance", "value": float(f["fundingRate"])}
            )
    if bb_funding.available and isinstance(bb_funding.value, list):
        for f in bb_funding.value:
            funding_history.append(
                {"time": int(f["fundingRateTimestamp"]) // 1000, "exchange": "bybit", "value": float(f["fundingRate"])}
            )
    funding_history.sort(key=lambda x: x["time"])

    oi_history = []
    if bb_oi.available and isinstance(bb_oi.value, list):
        for entry in reversed(bb_oi.value):
            oi_history.append({"time": int(entry["timestamp"]) // 1000, "value": float(entry["openInterest"])})
    if oi_binance is not None:
        oi_history.append({"time": int(time.time()), "value": oi_binance})

    ls_binance = None
    if ls_bn.available and isinstance(ls_bn.value, list) and ls_bn.value:
        ls_binance = to_f(ls_bn.value[0].get("longShortRatio"))
    ls_bybit = None
    if bb_ls.available and isinstance(bb_ls.value, list) and bb_ls.value:
        entry = bb_ls.value[0]
        buy, sell = to_f(entry.get("buyRatio")), to_f(entry.get("sellRatio"))
        if buy is not None and sell:
            ls_bybit = round(buy / sell, 4)

    basis = None
    spot_price = to_f((spot_t.value or {}).get("lastPrice")) if spot_t.available else None
    perp_price = to_f((perp_t.value or {}).get("lastPrice")) if perp_t.available else None
    if spot_price and perp_price:
        basis = round(perp_price - spot_price, 8)

    liquidations = await _liquidations_block(info.symbol)

    # --- agent-grade derivatives deltas (additive fields) -------------------
    oi_change_pct_1h = None
    if bb_oi.available and isinstance(bb_oi.value, list) and len(bb_oi.value) >= 2:
        try:
            newest = float(bb_oi.value[0]["openInterest"])
            oldest = float(bb_oi.value[-1]["openInterest"])
            if oldest > 0:
                oi_change_pct_1h = round((newest - oldest) / oldest * 100, 3)
        except (KeyError, TypeError, ValueError):
            pass

    funding_change_1h = None
    if len(funding_history) >= 2:
        funding_change_1h = round(funding_history[-1]["value"] - funding_history[-2]["value"], 8)

    perp_premium_pct = None
    if spot_price and perp_price and spot_price > 0:
        perp_premium_pct = round((perp_price - spot_price) / spot_price * 100, 4)

    results = [premium, oi_bn, bb_linear]
    available_any = any(r.available for r in results)
    updated = max((r.updated_at for r in results if r.updated_at), default=None)
    stale = any(r.stale for r in results if r.available)

    return {
        "symbol": info.symbol,
        "funding": {"binance": funding_binance, "bybit": funding_bybit, "history": funding_history},
        "open_interest": {"binance": oi_binance, "bybit": oi_bybit, "history": oi_history},
        "long_short_ratio": (
            {"binance": ls_binance, "bybit": ls_bybit}
            if (ls_binance is not None or ls_bybit is not None)
            else None
        ),
        "basis": basis,
        "oi_change_pct_1h": oi_change_pct_1h,
        "funding_change_1h": funding_change_1h,
        "perp_premium_pct": perp_premium_pct,
        "liquidations": liquidations,
        "available": available_any,
        "updated_at": updated,
        "stale": stale,
    }


async def get_liquidity(symbol: str) -> dict[str, Any]:
    info = deps.symbol_or_404(symbol)
    pair = info.binance_spot_pair
    bn_depth, bb_book, deriv_entry, price = await asyncio.gather(
        binance_rest.depth(pair, limit=100, market="spot"),
        bybit_rest.orderbook(pair, limit=50, category="spot"),
        get_cache().get_entry(f"deriv:{info.symbol}"),
        best_price(info.symbol),
    )

    books: list[tuple[str, list, list]] = []
    if bn_depth.available and isinstance(bn_depth.value, dict):
        books.append(("binance", bn_depth.value.get("bids") or [], bn_depth.value.get("asks") or []))
    if bb_book.available and isinstance(bb_book.value, dict):
        books.append(("bybit", bb_book.value.get("b") or [], bb_book.value.get("a") or []))

    mid_price = price
    if mid_price is None and books:
        exch, bids, asks = books[0]
        if bids and asks:
            mid_price = (float(bids[0][0]) + float(asks[0][0])) / 2

    walls = {"bids": [], "asks": []}
    for exch, bids, asks in books:
        w = liq_engine.detect_walls(bids, asks, exch)
        walls["bids"].extend(w["bids"])
        walls["asks"].extend(w["asks"])
    walls["bids"].sort(key=lambda w: -w["size_usd"])
    walls["asks"].sort(key=lambda w: -w["size_usd"])
    walls["bids"] = walls["bids"][:20]
    walls["asks"] = walls["asks"][:20]

    imbalance = None
    for exch, bids, asks in books:
        imbalance = liq_engine.depth_imbalance(bids, asks)
        if imbalance is not None:
            break

    zones: list[dict[str, Any]] = []
    if mid_price:
        zones.extend(liq_engine.wall_zones(walls, mid_price))
        for exch, bids, asks in books:
            w = {"bids": [x for x in walls["bids"] if x["exchange"] == exch],
                 "asks": [x for x in walls["asks"] if x["exchange"] == exch]}
            zones.extend(liq_engine.support_resistance_estimates(bids, asks, mid_price, w))
        deriv = deriv_entry.value if deriv_entry and isinstance(deriv_entry.value, dict) else {}
        oi_base = deriv.get("binance_oi") or deriv.get("bybit_oi")
        if oi_base:
            zones.extend(liq_engine.estimated_liquidation_clusters(mid_price, float(oi_base) * mid_price))

    state = get_live_state()
    snapshots = list(state.depth_history.get(f"binance:{info.symbol}", [])) or list(
        state.depth_history.get(f"bybit:{info.symbol}", [])
    )
    heatmap = liq_engine.build_heatmap([(ts, b, a) for ts, b, a in snapshots]) if snapshots else None

    # Detected sweeps from the recent trade path through known zones (additive).
    sweeps: list[dict[str, Any]] = []
    trades = state.recent_trades("binance", info.symbol)
    if trades and zones:
        price_series = [
            {"time": t.get("time", 0), "price": float(t.get("price", t.get("p", 0)) or 0)}
            for t in trades
            if t.get("price") or t.get("p")
        ]
        if len(price_series) >= 5:
            sweeps = liq_engine.detect_sweep(price_series, zones)

    available = bool(books)
    updated = None
    stale = False
    results = [r for r in (bn_depth, bb_book) if r.available]
    if results:
        updated = max((r.updated_at for r in results if r.updated_at), default=None)
        stale = any(r.stale for r in results)

    return {
        "symbol": info.symbol,
        "mid_price": mid_price,
        "walls": walls,
        "zones": zones,
        "heatmap": heatmap,
        "imbalance": imbalance,
        "sweeps": sweeps,
        "disclaimer": liq_engine.DISCLAIMER,
        "available": available,
        "updated_at": updated,
        "stale": stale,
    }


async def build_market_state(symbol: str) -> dict[str, Any]:
    """Assemble the scenario-engine market state from cached/live data."""
    info = deps.symbol_or_404(symbol)
    pair = info.binance_spot_pair
    spot_t, perp_t, premium, depth, trades, deriv_entry, bb_oi, bb_linear = await asyncio.gather(
        binance_rest.ticker_24h(pair, "spot"),
        binance_rest.ticker_24h(pair, "perp"),
        binance_rest.premium_index(pair),
        binance_rest.depth(pair, limit=50, market="spot"),
        binance_rest.agg_trades(pair, limit=1000, market="spot"),
        get_cache().get_entry(f"deriv:{info.symbol}"),
        bybit_rest.open_interest(pair),
        bybit_rest.tickers(pair, "linear"),
    )

    price = None
    if spot_t.available and isinstance(spot_t.value, dict):
        price = to_f(spot_t.value.get("lastPrice"))
    if price is None:
        price = await best_price(info.symbol)

    funding = None
    if premium.available and isinstance(premium.value, dict):
        funding = to_f(premium.value.get("lastFundingRate"))
    if funding is None and deriv_entry and isinstance(deriv_entry.value, dict):
        funding = deriv_entry.value.get("binance_funding") or deriv_entry.value.get("bybit_funding")

    oi_change_pct = None
    if bb_oi.available and isinstance(bb_oi.value, list) and len(bb_oi.value) >= 2:
        try:
            newest = float(bb_oi.value[0]["openInterest"])
            oldest = float(bb_oi.value[-1]["openInterest"])
            if oldest > 0:
                oi_change_pct = round((newest - oldest) / oldest * 100, 3)
        except (KeyError, TypeError, ValueError):
            pass

    taker_ratio = cvd_slope = None
    if trades.available and isinstance(trades.value, list) and trades.value:
        buy, sell = pressure_engine.split_taker_flow(trades.value)
        taker_ratio = pressure_engine.taker_ratio(buy, sell)
        cvd = pressure_engine.compute_cvd(trades.value)
        if len(cvd) >= 2:
            deltas = [cvd[i]["value"] - cvd[i - 1]["value"] for i in range(1, len(cvd))]
            total = sum(abs(d) for d in deltas)
            if total > 0:
                cvd_slope = round(sum(deltas) / total, 3)

    book_imbalance = support = resistance = None
    if depth.available and isinstance(depth.value, dict):
        bids = depth.value.get("bids") or []
        asks = depth.value.get("asks") or []
        book_imbalance = liq_engine.depth_imbalance(bids, asks)
        if price:
            walls = liq_engine.detect_walls(bids, asks, "binance")
            bid_walls = sorted((w["price"] for w in walls["bids"] if w["price"] < price), reverse=True)
            ask_walls = sorted(w["price"] for w in walls["asks"] if w["price"] > price)
            support = bid_walls[0] if bid_walls else None
            resistance = ask_walls[0] if ask_walls else None

    spread_bps = None
    if spot_t.available and bb_linear.available and isinstance(bb_linear.value, list) and bb_linear.value:
        bb_price = to_f(bb_linear.value[0].get("lastPrice"))
        if price and bb_price:
            spread_bps = round(abs(price - bb_price) / ((price + bb_price) / 2) * 10_000, 2)

    change_24h = None
    if spot_t.available and isinstance(spot_t.value, dict):
        change_24h = to_f(spot_t.value.get("priceChangePercent"))

    stale = any(r.stale for r in (spot_t, premium, depth, trades) if r.available)
    updated = max(
        (r.updated_at for r in (spot_t, premium, depth, trades) if r.available and r.updated_at),
        default=None,
    )
    state = {
        "price": price,
        "funding": funding,
        "oi_change_pct": oi_change_pct,
        "taker_ratio": taker_ratio,
        "cvd_slope": cvd_slope,
        "book_imbalance": book_imbalance,
        "spread_bps": spread_bps,
        "support": support,
        "resistance": resistance,
        "price_change_24h": change_24h,
    }
    return {"state": state, "stale": stale, "updated_at": updated}


async def get_scenarios(symbol: str) -> dict[str, Any]:
    """Dashboard shape (v1 rules) — unchanged public contract."""
    info = deps.symbol_or_404(symbol)
    built = await build_market_state(info.symbol)
    state = built["state"]
    scenarios = scenario_engine.generate_scenarios(info.symbol, state, stale=built["stale"])
    market_state = {k: (f"{v:.6g}" if isinstance(v, float) else str(v)) for k, v in state.items()}
    return {
        "scenarios": scenarios,
        "market_state": market_state,
        "available": state.get("price") is not None,
        "updated_at": built["updated_at"],
        "stale": built["stale"],
    }


async def get_scenarios_v2(symbol: str) -> dict[str, Any]:
    """Agent shape: same market state, ScenarioV2 superset output."""
    info = deps.symbol_or_404(symbol)
    built = await build_market_state(info.symbol)
    state = built["state"]
    scenarios = scenario_engine_v2.generate_scenarios_v2(info.symbol, state, stale=built["stale"])
    market_state = {k: (f"{v:.6g}" if isinstance(v, float) else str(v)) for k, v in state.items()}
    return {
        "scenarios": scenarios,
        "market_state": market_state,
        "available": state.get("price") is not None,
        "updated_at": built["updated_at"],
        "stale": built["stale"],
    }


async def get_sentiment(symbol: str) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    info = deps.symbol_or_404(symbol)
    agg = get_aggregator()
    if not agg._ever_fetched:
        try:
            await agg.refresh()
        except Exception:
            pass

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    items = [i for i in agg._items if info.symbol in i["assets"] and i["published_at"] >= since]
    news_component = None
    if items:
        vals = [i["sentiment"] for i in items if i.get("sentiment") is not None]
        if vals:
            news_component = round(sum(vals) / len(vals), 3)

    markets_res, fng_res, deriv_entry = await asyncio.gather(
        coingecko.top_markets(limit=250),
        feargreed.fear_greed(limit=5),
        get_cache().get_entry(f"deriv:{info.symbol}"),
    )
    change_1h = change_24h = change_7d = volume = mcap = None
    if markets_res.available and isinstance(markets_res.value, list):
        for c in markets_res.value:
            if c.get("id") == info.coingecko_id:
                change_1h = c.get("price_change_percentage_1h_in_currency")
                change_24h = c.get("price_change_percentage_24h_in_currency")
                change_7d = c.get("price_change_percentage_7d_in_currency")
                volume = c.get("total_volume")
                mcap = c.get("market_cap")
                break

    funding = None
    if deriv_entry and isinstance(deriv_entry.value, dict):
        funding = deriv_entry.value.get("binance_funding") or deriv_entry.value.get("bybit_funding")

    fear_greed_block = None
    if fng_res.available and isinstance(fng_res.value, dict) and fng_res.value.get("data"):
        current = fng_res.value["data"][0]
        fear_greed_block = {
            "value": float(current["value"]),
            "classification": current.get("value_classification", "unknown"),
            "source": "alternative.me",
            "attribution": feargreed.ATTRIBUTION,
            "history": [],
            "updated_at": fng_res.updated_at,
            "stale": fng_res.stale,
        }

    stale = markets_res.stale if markets_res.available else False
    return sentiment_engine.build_sentiment_report(
        news_component=news_component,
        change_1h=change_1h,
        change_24h=change_24h,
        change_7d=change_7d,
        volume_24h=volume,
        market_cap=mcap,
        funding_rate=funding,
        fear_greed=fear_greed_block,
        updated_at=markets_res.updated_at if markets_res.available else None,
        stale=stale,
    )


async def get_defi(symbol: str) -> dict[str, Any]:
    info = deps.symbol_or_404(symbol)
    dex_res, tvl_res = await asyncio.gather(
        dexscreener.search_pairs(info.symbol), defillama.tvl_for_symbol(info.symbol)
    )

    pools: list[dict[str, Any]] = []
    if dex_res.available and isinstance(dex_res.value, dict):
        for p in (dex_res.value.get("pairs") or []):
            base_sym = ((p.get("baseToken") or {}).get("symbol") or "").upper()
            if base_sym != info.symbol:
                continue
            pools.append(
                {
                    "dex": p.get("dexId") or "unknown",
                    "chain": p.get("chainId") or "unknown",
                    "pair": f"{base_sym}/{((p.get('quoteToken') or {}).get('symbol') or '?')}",
                    "liquidity_usd": to_f((p.get("liquidity") or {}).get("usd")),
                    "volume_24h": to_f((p.get("volume") or {}).get("h24")),
                    "price_usd": to_f(p.get("priceUsd")),
                    "price_change_24h": to_f((p.get("priceChange") or {}).get("h24")),
                    "url": p.get("url"),
                }
            )
    pools.sort(key=lambda p: -(p["liquidity_usd"] or 0))
    pools = pools[:20]

    tvl_usd = None
    if tvl_res.available and isinstance(tvl_res.value, dict):
        tvl_usd = tvl_res.value.get("tvl_usd")

    available = dex_res.available or tvl_res.available
    updated = None
    results = [r for r in (dex_res, tvl_res) if r.available]
    if results:
        updated = max((r.updated_at for r in results if r.updated_at), default=None)
    return {
        "pools": pools,
        "tvl_usd": tvl_usd,
        "source": [s for s, r in (("dexscreener", dex_res), ("defillama", tvl_res)) if r.available],
        "available": available,
        "updated_at": updated,
        "stale": any(r.stale for r in results) if results else False,
    }


async def get_news(symbol: str, limit: int = 20) -> dict[str, Any]:
    info = deps.symbol_or_404(symbol)
    agg = get_aggregator()
    items, meta = await agg.get_items(asset=info.symbol, limit=limit)
    return {"items": items, "meta": meta}
