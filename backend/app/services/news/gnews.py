"""GNews client. Disabled without GNEWS_API_KEY."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.services import get_source_status, mark_failure, mark_success
from app.services.http import get_json

log = logging.getLogger(__name__)

SOURCE = "gnews"
URL = "https://gnews.io/api/v4/search"


def configured() -> bool:
    cfg = bool(get_settings().gnews_api_key)
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
    if not configured():
        raise RuntimeError("GNEWS_API_KEY not configured")
    data = await get_json(
        URL,
        params={
            "q": "crypto OR bitcoin OR ethereum",
            "token": get_settings().gnews_api_key,
            "lang": "en",
            "max": 25,
        },
        rate_per_min=10.0,
    )
    articles = data.get("articles")
    if articles is None:
        raise RuntimeError(f"gnews error: {str(data)[:200]}")
    items = []
    for a in articles:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        items.append(
            {
                "headline": title,
                "source": (a.get("source") or {}).get("name") or "GNews",
                "url": a.get("url"),
                "published_at": _parse_dt(a.get("publishedAt")),
                "summary": a.get("description"),
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
        log.info("gnews fetch skipped/failed: %s", exc)
        return []
