"""NewsAggregator: fetch from all providers, merge, dedupe by normalized
headline similarity (>=0.85 -> keep earliest, merge asset lists),
categorize, score importance, estimate sentiment."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.core import db as core_db
from app.engines import categorizer
from app.services import get_source_status, iso
from app.services.news import gnews, newsdata, rss

log = logging.getLogger(__name__)

DEDUPE_THRESHOLD = 0.85
SIMILARITY = DEDUPE_THRESHOLD


class NewsAggregator:
    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self.last_fetch: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self._ever_fetched = False

    # -- ingestion ---------------------------------------------------------
    async def refresh(self) -> int:
        """Fetch from all providers and rebuild the merged feed."""
        raw: list[dict[str, Any]] = []
        results = await asyncio.gather(
            newsdata.safe_fetch(), gnews.safe_fetch(), rss.safe_fetch_all()
        )
        for batch in results:
            raw.extend(batch)
        items = self._process(raw)
        async with self._lock:
            self._items = items
            self.last_fetch = datetime.now(timezone.utc)
            self._ever_fetched = True
        await self._persist(items)
        return len(items)

    def _process(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        processed: list[dict[str, Any]] = []
        for r in raw:
            headline = (r.get("headline") or "").strip()
            if not headline:
                continue
            published = r.get("published_at") or now
            if published > now:
                published = now  # never trust future timestamps
            text = f"{headline} {r.get('summary') or ''}"
            assets = categorizer.extract_assets(text)
            category = categorizer.classify_category(headline, r.get("summary"))
            processed.append(
                {
                    "headline": headline,
                    "source": r.get("source") or "unknown",
                    "source_url": r.get("url"),
                    "published_at": published,
                    "assets": assets,
                    "category": category,
                    "sentiment": categorizer.sentiment_score(text),
                    "importance": categorizer.importance_score(headline, category, assets),
                    "kind": categorizer.classify_kind(headline, r.get("source")),
                    "summary": r.get("summary"),
                    "provider": r.get("provider", ""),
                }
            )
        return self._dedupe(processed)

    def _dedupe(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Similarity >= 0.85 on normalized headlines -> keep the earliest,
        merge asset lists."""
        items.sort(key=lambda i: i["published_at"])
        kept: list[dict[str, Any]] = []
        for item in items:
            dup = None
            for existing in kept:
                if (
                    categorizer.headline_similarity(existing["headline"], item["headline"])
                    >= DEDUPE_THRESHOLD
                ):
                    dup = existing
                    break
            if dup is None:
                kept.append(item)
            else:
                merged = list(dict.fromkeys(dup["assets"] + item["assets"]))
                dup["assets"] = merged
                dup["importance"] = max(dup["importance"], item["importance"])
        kept.sort(key=lambda i: i["published_at"], reverse=True)
        return kept

    @staticmethod
    def _item_id(item: dict[str, Any]) -> str:
        key = item.get("source_url") or item["headline"]
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    def _to_contract(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": self._item_id(item),
            "headline": item["headline"],
            "source": item["source"],
            "source_url": item.get("source_url"),
            "published_at": iso(item["published_at"]),
            "assets": item["assets"],
            "category": item["category"],
            "sentiment": item["sentiment"],
            "importance": item["importance"],
            "kind": item["kind"],
            "summary": item.get("summary"),
        }

    # -- reads ---------------------------------------------------------------
    async def get_items(
        self,
        *,
        category: str | None = None,
        asset: str | None = None,
        kind: str | None = None,
        limit: int = 30,
        offset: int = 0,
        auto_refresh: bool = True,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Returns (contract items, meta). Fetches once on first use."""
        if auto_refresh and not self._ever_fetched:
            try:
                await self.refresh()
            except Exception as exc:
                self.last_error = str(exc)
        async with self._lock:
            items = list(self._items)
            fetched = self.last_fetch
        if category:
            items = [i for i in items if i["category"] == category]
        if asset:
            sym = asset.upper()
            items = [i for i in items if sym in i["assets"]]
        if kind:
            items = [i for i in items if i["kind"] == kind]
        page = items[offset : offset + limit]
        meta = {
            "source": self.active_sources(),
            "updated_at": iso(fetched) if fetched else None,
            "stale": False,
            "available": fetched is not None,
        }
        return [self._to_contract(i) for i in page], meta

    def count_for_asset(self, symbol: str, since: datetime) -> int:
        sym = symbol.upper()
        return sum(1 for i in self._items if sym in i["assets"] and i["published_at"] >= since)

    def latest_for_asset(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        sym = symbol.upper()
        matched = [i for i in self._items if sym in i["assets"]]
        return [self._to_contract(i) for i in matched[:limit]]

    def active_sources(self) -> list[str]:
        sources = []
        if newsdata.configured():
            sources.append("newsdata")
        if gnews.configured():
            sources.append("gnews")
        for name in rss.RSS_FEEDS:
            if rss.feed_enabled(name):
                sources.append(f"rss:{name}")
        return sources

    def sources_status(self) -> list[dict[str, Any]]:
        out = []
        for name, configured in (("newsdata", newsdata.configured()), ("gnews", gnews.configured())):
            st = get_source_status(name)
            st.configured = configured
            out.append(
                {
                    "name": name,
                    "configured": configured,
                    "last_fetch": st.last_success or st.last_fetch,
                    "error": st.error,
                }
            )
        for name in rss.RSS_FEEDS:
            st = get_source_status(f"rss:{name}")
            out.append(
                {
                    "name": f"rss:{name}",
                    "configured": rss.feed_enabled(name),
                    "last_fetch": st.last_success or st.last_fetch,
                    "error": st.error,
                }
            )
        return out

    # -- persistence (optional) ---------------------------------------------
    async def _persist(self, items: list[dict[str, Any]]) -> None:
        if not core_db.db_available():
            return
        try:
            from sqlalchemy import select
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            from app.models import NewsArticle

            async with core_db.session() as session:
                if session is None:
                    return
                for item in items[:100]:
                    url = item.get("source_url")
                    if not url:
                        continue
                    stmt = (
                        pg_insert(NewsArticle)
                        .values(
                            url=url,
                            headline=item["headline"],
                            source=item["source"],
                            published_at=item["published_at"],
                            category=item["category"],
                            sentiment=item["sentiment"],
                            importance=item["importance"],
                            kind=item["kind"],
                            summary=item.get("summary"),
                        )
                        .on_conflict_do_nothing(index_elements=["url"])
                    )
                    await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            log.info("news persistence skipped: %s", exc)


_aggregator = NewsAggregator()


def get_aggregator() -> NewsAggregator:
    return _aggregator
