"""Background pollers: CoinGecko markets/global, Fear & Greed, news,
derivatives snapshots (funding / OI / long-short). Persist to DB when a
database is available; never crash the app on failure."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core import db as core_db
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.symbols import update_from_markets
from app.services import binance_rest, bybit_rest, coingecko, feargreed
from app.services.news import get_aggregator

log = logging.getLogger(__name__)


async def _loop(name: str, interval: int, fn, run_immediately: bool = True) -> None:
    while True:
        if run_immediately:
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.info("%s poll failed: %s", name, exc)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        run_immediately = True


async def poll_markets() -> None:
    res = await coingecko.top_markets(limit=250)
    if res.available and isinstance(res.value, list):
        update_from_markets(res.value)
        await _persist_assets(res.value)
    await coingecko.global_overview()


async def _persist_assets(markets: list[dict]) -> None:
    if not core_db.db_available():
        return
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.models import Asset

        async with core_db.session() as session:
            if session is None:
                return
            for coin in markets[:250]:
                sym = (coin.get("symbol") or "").upper()
                if not sym:
                    continue
                stmt = (
                    pg_insert(Asset)
                    .values(
                        symbol=sym,
                        name=coin.get("name") or sym,
                        coingecko_id=coin.get("id"),
                        image=coin.get("image"),
                    )
                    .on_conflict_do_nothing(index_elements=["symbol"])
                )
                await session.execute(stmt)
            await session.commit()
    except Exception as exc:
        log.info("asset persistence skipped: %s", exc)


async def poll_fear_greed() -> None:
    await feargreed.fear_greed(limit=30)


async def poll_news() -> None:
    await get_aggregator().refresh()


async def poll_derivatives() -> None:
    """Funding / OI / long-short snapshots for tracked symbols -> cache keys
    `deriv:{SYM}` consumed by the derivatives endpoint + alert evaluator."""
    symbols = get_settings().tracked_symbol_list
    for sym in symbols:
        pair = f"{sym}USDT"
        try:
            premium, oi, ls, bb_tickers = await asyncio.gather(
                binance_rest.premium_index(pair),
                binance_rest.open_interest(pair),
                binance_rest.global_long_short_ratio(pair),
                bybit_rest.tickers(pair, category="linear"),
            )
            snapshot: dict = {
                "fetched_at": datetime.now(timezone.utc).timestamp(),
                "binance_funding": None,
                "binance_oi": None,
                "binance_ls_ratio": None,
                "bybit_funding": None,
                "bybit_oi": None,
                "bybit_ls_ratio": None,
                "stale_parts": [],
            }
            if premium.available and isinstance(premium.value, dict):
                try:
                    snapshot["binance_funding"] = float(premium.value.get("lastFundingRate"))
                except (TypeError, ValueError):
                    pass
            if oi.available and isinstance(oi.value, dict):
                try:
                    snapshot["binance_oi"] = float(oi.value.get("openInterest"))
                except (TypeError, ValueError):
                    pass
            if ls.available and isinstance(ls.value, list) and ls.value:
                try:
                    snapshot["binance_ls_ratio"] = float(ls.value[0].get("longShortRatio"))
                except (TypeError, ValueError, IndexError):
                    pass
            if bb_tickers.available and isinstance(bb_tickers.value, list) and bb_tickers.value:
                t = bb_tickers.value[0]
                for key, field in (("bybit_funding", "fundingRate"), ("bybit_oi", "openInterest")):
                    try:
                        snapshot[key] = float(t[field]) if t.get(field) not in (None, "") else None
                    except (TypeError, ValueError):
                        pass
            await get_cache().set(f"deriv:{sym}", snapshot, ttl=300)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.info("derivatives poll for %s failed: %s", sym, exc)


async def start_pollers() -> list[asyncio.Task]:
    settings = get_settings()
    tasks = [
        asyncio.create_task(
            _loop("markets", settings.market_poll_interval, poll_markets), name="poll_markets"
        ),
        asyncio.create_task(
            _loop("fear_greed", settings.fear_greed_poll_interval, poll_fear_greed),
            name="poll_fear_greed",
        ),
        asyncio.create_task(
            _loop("news", settings.news_poll_interval, poll_news), name="poll_news"
        ),
        asyncio.create_task(
            _loop("derivatives", settings.derivatives_poll_interval, poll_derivatives),
            name="poll_derivatives",
        ),
    ]
    log.info("pollers started")
    return tasks


async def stop_pollers(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    log.info("pollers stopped")
