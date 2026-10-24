"""RSS news feeds. Reachability is verified at runtime; a feed is disabled
after repeated failures instead of breaking the pipeline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from app.services import get_source_status, mark_failure, mark_success
from app.services.http import get_text

log = logging.getLogger(__name__)

RSS_FEEDS: dict[str, str] = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "binance_announcements": "https://www.binance.com/en/support/announcement/rss",
    "decrypt": "https://decrypt.co/feed",
}

MAX_CONSECUTIVE_FAILURES = 3


def _parse_dt(entry: Any) -> datetime | None:
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            return None
    return None


async def fetch_feed(name: str, url: str) -> list[dict[str, Any]]:
    """Fetch + parse one RSS feed. Raises on failure."""
    import feedparser

    text = await get_text(url, rate_per_min=10.0)
    parsed = await _parse(text)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"rss parse failed: {getattr(parsed, 'bozo_exception', 'unknown')}")
    items = []
    for entry in parsed.entries[:40]:
        title = (getattr(entry, "title", "") or "").strip()
        link = getattr(entry, "link", None)
        if not title:
            continue
        summary = getattr(entry, "summary", None)
        if summary and len(summary) > 500:
            summary = summary[:500]
        items.append(
            {
                "headline": title,
                "source": name,
                "url": link,
                "published_at": _parse_dt(entry),
                "summary": summary,
                "provider": f"rss:{name}",
            }
        )
    mark_success(f"rss:{name}")
    return items


async def _parse(text: str):
    import asyncio

    import feedparser

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, feedparser.parse, text)


def feed_enabled(name: str) -> bool:
    st = get_source_status(f"rss:{name}")
    return st.consecutive_failures < MAX_CONSECUTIVE_FAILURES


async def safe_fetch_all() -> list[dict[str, Any]]:
    """Fetch all enabled feeds; failed feeds are skipped and their status
    recorded. Never raises."""
    import asyncio

    async def one(name: str, url: str) -> list[dict[str, Any]]:
        if not feed_enabled(name):
            return []
        try:
            return await fetch_feed(name, url)
        except Exception as exc:
            mark_failure(f"rss:{name}", str(exc))
            log.info("rss feed %s failed: %s", name, exc)
            return []

    results = await asyncio.gather(*(one(n, u) for n, u in RSS_FEEDS.items()))
    return [item for batch in results for item in batch]
