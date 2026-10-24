"""NewsData.io crypto news client. Disabled without NEWSDATA_API_KEY."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.services import get_source_status, mark_failure, mark_success
from app.services.http import get_json

log = logging.getLogger(__name__)

SOURCE = "newsdata"
URL = "https://newsdata.io/api/1/crypto"


def configured() -> bool:
    cfg = bool(get_settings().newsdata_api_key)
    get_source_status(SOURCE).configured = cfg
    return cfg


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def fetch_latest() -> list[dict[str, Any]]:
    """Fetch latest crypto news. Raises when unconfigured or upstream fails."""
    if not configured():
        raise RuntimeError("NEWSDATA_API_KEY not configured")
    data = await get_json(
        URL,
        params={"apikey": get_settings().newsdata_api_key, "language": "en", "removeduplicate": "1"},
        rate_per_min=10.0,
    )
    if data.get("status") != "success":
        raise RuntimeError(f"newsdata status={data.get('status')}")
    items = []
    for r in data.get("results") or []:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        items.append(
            {
                "headline": title,
                "source": r.get("source_name") or r.get("source_id") or "NewsData.io",
                "url": r.get("link"),
                "published_at": _parse_dt(r.get("pubDate")),
                "summary": r.get("description"),
                "provider": SOURCE,
            }
        )
    mark_success(SOURCE)
    return items


async def safe_fetch() -> list[dict[str, Any]]:
    try:
        return await fetch_latest()
    except Exception as exc:
        if configured():
            mark_failure(SOURCE, str(exc))
        else:
            get_source_status(SOURCE).configured = False
        log.info("newsdata fetch skipped/failed: %s", exc)
        return []
