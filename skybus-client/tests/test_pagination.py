"""Cursor pagination: get_news pages + iter_news, get_events + iter_events."""

from __future__ import annotations

import respx
from httpx import Response

from skybus_client import SkybusClient
from skybus_client.models import NewsItem

from conftest import BASE_URL, make_envelope


def news_item(item_id: str) -> dict:
    return {
        "id": item_id,
        "headline": f"headline {item_id}",
        "source": "reuters",
        "source_url": None,
        "published_at": "2026-10-24T12:00:00Z",
        "assets": ["BTC"],
        "category": "macro",
        "sentiment": 0.2,
        "importance": 3,
        "kind": "verified",
        "summary": None,
    }


async def test_iter_news_paginates_until_cursor_exhausted():
    page1 = make_envelope(
        {"items": [news_item("n1"), news_item("n2")], "next_cursor": "cursor-2"}
    )
    page2 = make_envelope({"items": [news_item("n3")], "next_cursor": None})

    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/api/v1/agent/assets/BTC/news")
        route.side_effect = [Response(200, json=page1), Response(200, json=page2)]

        async with SkybusClient(BASE_URL, api_key="k") as client:
            items = [item async for item in client.iter_news("BTC")]

    assert [i.id for i in items] == ["n1", "n2", "n3"]
    assert all(isinstance(i, NewsItem) for i in items)

    # second request must carry the opaque cursor from page 1
    first, second = route.calls
    assert "cursor" not in first.request.url.params
    assert second.request.url.params["cursor"] == "cursor-2"
    assert second.request.url.params["limit"] == "50"


async def test_get_news_single_page():
    page = make_envelope({"items": [news_item("n1")], "next_cursor": None})
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/assets/ETH/news").mock(return_value=Response(200, json=page))
        async with SkybusClient(BASE_URL, api_key="k") as client:
            env = await client.get_news("ETH", limit=10)

    assert env.data.next_cursor is None
    assert env.data.items[0].headline == "headline n1"


def event_item(event_id: str) -> dict:
    from conftest import make_event

    return make_event(event_id, stream_id=f"1698{event_id}-0")


async def test_iter_events_paginates_with_filters():
    page1 = make_envelope({"items": [event_item("0001")], "next_cursor": "c9"})
    page2 = make_envelope({"items": [event_item("0002")], "next_cursor": None})

    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/api/v1/agent/events")
        route.side_effect = [Response(200, json=page1), Response(200, json=page2)]

        async with SkybusClient(BASE_URL, api_key="k") as client:
            events = [
                e
                async for e in client.iter_events(
                    limit=25, type="FUNDING_EXTREME", asset="BTC", severity="warning"
                )
            ]

    assert [e.id for e in events] == ["0001", "0002"]
    params = route.calls[0].request.url.params
    assert params["type"] == "FUNDING_EXTREME"
    assert params["asset"] == "BTC"
    assert params["severity"] == "warning"
    assert params["limit"] == "25"
    assert route.calls[1].request.url.params["cursor"] == "c9"


async def test_iter_news_stops_on_unavailable_page():
    page = make_envelope(None, available=False, observed_at=None, freshness_sec=None)
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/api/v1/agent/assets/BTC/news").mock(return_value=Response(200, json=page))
        async with SkybusClient(BASE_URL, api_key="k") as client:
            items = [item async for item in client.iter_news("BTC")]
    assert items == []
