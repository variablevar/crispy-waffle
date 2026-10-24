"""Async SkyBus agent API client (REST + WebSocket stream).

Built against docs/AGENT_CONTRACT.md (agent.v1). Auth is the ``X-API-Key``
header on every request, REST and WS alike.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator, Dict, Optional, Sequence, Type, TypeVar

import httpx
import websockets
from websockets.exceptions import WebSocketException

from ._streaming import (
    Backoff,
    DedupeSet,
    build_stream_url,
    build_subscribe_message,
    parse_stream_message,
)
from .exceptions import (
    SkybusAuthError,
    SkybusError,
    SkybusNotFoundError,
    SkybusRateLimitError,
    SkybusStaleDataError,
    SkybusUnavailableError,
)
from .models import (
    AgentEvent,
    AssetSnapshot,
    CrossExchangeReport,
    DerivativesReport,
    Envelope,
    EventsPage,
    LiquidityReport,
    MarketOverview,
    NewsItem,
    NewsPage,
    PressureReport,
    ScenarioSet,
    SentimentReport,
    SystemHealth,
)

__all__ = ["SkybusClient"]

M = TypeVar("M")

# Module-level indirection so tests can patch sleep / the WS connector.
_sleep = asyncio.sleep
_ws_connect = websockets.connect

_AGENT_BASE = "/api/v1/agent"


def _parse_error(response: httpx.Response) -> Dict[str, Optional[str]]:
    code: Optional[str] = None
    message: Optional[str] = None
    request_id: Optional[str] = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        code = err.get("code")
        message = err.get("message")
        request_id = err.get("request_id")
    if not message:
        message = response.text[:500] or f"HTTP {response.status_code}"
    if not request_id:
        request_id = response.headers.get("x-request-id")
    return {"code": code, "message": message, "request_id": request_id}


def _parse_retry_after(response: httpx.Response) -> Optional[float]:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


class SkybusClient:
    """Async client for the SkyBus agent API.

    Usage::

        async with SkybusClient("http://localhost:8123", api_key="...") as c:
            overview = await c.get_market_overview()

    The client also works without the context manager (the underlying HTTP
    client is created lazily); call :meth:`aclose` when done in that case.

    :param max_acceptable_staleness_sec: opt-in staleness guard. When set,
        any envelope that is not fresh within this many seconds (see
        :meth:`Envelope.is_fresh`) raises :class:`SkybusStaleDataError`
        instead of being returned.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        *,
        max_acceptable_staleness_sec: Optional[float] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_acceptable_staleness_sec = max_acceptable_staleness_sec
        self._http: Optional[httpx.AsyncClient] = None

    # -- lifecycle ---------------------------------------------------------

    async def __aenter__(self) -> "SkybusClient":
        self._ensure_http()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"X-API-Key": self.api_key},
            )
        return self._http

    # -- core request pipeline ---------------------------------------------

    def _rest_backoff(self, attempt: int) -> float:
        return min(5.0, 0.5 * (2**attempt))

    def _check_staleness(self, envelope: Envelope[Any]) -> None:
        limit = self.max_acceptable_staleness_sec
        if limit is not None and not envelope.is_fresh(limit):
            raise SkybusStaleDataError(
                f"response data is stale (limit {limit}s, request {envelope.request_id})",
                request_id=envelope.request_id,
                code="stale_data",
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        model: Type[M],
    ) -> Envelope[M]:
        http = self._ensure_http()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        last_exc: Optional[BaseException] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await http.request(method, path, params=clean_params)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await _sleep(self._rest_backoff(attempt))
                    continue
                raise SkybusUnavailableError(
                    f"network error contacting SkyBus after {attempt + 1} attempt(s): {exc}",
                    code="network_error",
                ) from exc

            status = response.status_code

            if status in (401, 403):
                info = _parse_error(response)
                raise SkybusAuthError(
                    info["message"] or "unauthorized",
                    status=status,
                    request_id=info["request_id"],
                    code=info["code"],
                )
            if status == 404:
                info = _parse_error(response)
                raise SkybusNotFoundError(
                    info["message"] or "not found",
                    status=status,
                    request_id=info["request_id"],
                    code=info["code"],
                )
            if status == 429:
                info = _parse_error(response)
                retry_after = _parse_retry_after(response)
                if attempt < self.max_retries:
                    await _sleep(
                        retry_after
                        if retry_after is not None
                        else self._rest_backoff(attempt)
                    )
                    continue
                raise SkybusRateLimitError(
                    info["message"] or "rate limited",
                    status=status,
                    request_id=info["request_id"],
                    code=info["code"],
                    retry_after=retry_after,
                )
            if status >= 500:
                if attempt < self.max_retries:
                    await _sleep(self._rest_backoff(attempt))
                    continue
                info = _parse_error(response)
                raise SkybusUnavailableError(
                    info["message"] or f"SkyBus unavailable (HTTP {status})",
                    status=status,
                    request_id=info["request_id"],
                    code=info["code"],
                )
            if status >= 400:
                info = _parse_error(response)
                raise SkybusError(
                    info["message"] or f"HTTP {status}",
                    status=status,
                    request_id=info["request_id"],
                    code=info["code"],
                )

            envelope: Envelope[M] = Envelope[model].model_validate(response.json())
            self._check_staleness(envelope)
            return envelope

        # Unreachable, but keeps type checkers happy.
        raise SkybusUnavailableError(
            f"request failed: {last_exc}", code="network_error"
        ) from last_exc

    # -- REST endpoints ------------------------------------------------------

    async def get_market_overview(self) -> Envelope[MarketOverview]:
        return await self._request("GET", f"{_AGENT_BASE}/market/overview", model=MarketOverview)

    async def get_snapshot(
        self,
        asset: str,
        venue: Optional[str] = None,
        instrument: Optional[str] = None,
    ) -> Envelope[AssetSnapshot]:
        return await self._request(
            "GET",
            f"{_AGENT_BASE}/assets/{asset}/snapshot",
            params={"venue": venue, "instrument": instrument},
            model=AssetSnapshot,
        )

    async def get_news(
        self,
        asset: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Envelope[NewsPage]:
        path = (
            f"{_AGENT_BASE}/assets/{asset}/news" if asset is not None else f"{_AGENT_BASE}/news"
        )
        return await self._request(
            "GET", path, params={"limit": limit, "cursor": cursor}, model=NewsPage
        )

    async def iter_news(
        self, asset: Optional[str] = None, limit: int = 50
    ) -> AsyncIterator[NewsItem]:
        """Async-paginate through all news items for an asset."""
        cursor: Optional[str] = None
        while True:
            page = await self.get_news(asset=asset, limit=limit, cursor=cursor)
            if page.data is None:
                return
            for item in page.data.items:
                yield item
            cursor = page.data.next_cursor
            if not cursor:
                return

    async def get_pressure(
        self, asset: str, timeframe: Optional[str] = None
    ) -> Envelope[PressureReport]:
        return await self._request(
            "GET",
            f"{_AGENT_BASE}/assets/{asset}/pressure",
            params={"timeframe": timeframe},
            model=PressureReport,
        )

    async def get_derivatives(self, asset: str) -> Envelope[DerivativesReport]:
        return await self._request(
            "GET", f"{_AGENT_BASE}/assets/{asset}/derivatives", model=DerivativesReport
        )

    async def get_liquidity(self, asset: str) -> Envelope[LiquidityReport]:
        return await self._request(
            "GET", f"{_AGENT_BASE}/assets/{asset}/liquidity", model=LiquidityReport
        )

    async def get_sentiment(self, asset: str) -> Envelope[SentimentReport]:
        return await self._request(
            "GET", f"{_AGENT_BASE}/assets/{asset}/sentiment", model=SentimentReport
        )

    async def get_scenarios(self, asset: str) -> Envelope[ScenarioSet]:
        return await self._request(
            "GET", f"{_AGENT_BASE}/assets/{asset}/scenarios", model=ScenarioSet
        )

    async def get_cross_exchange(self, asset: str) -> Envelope[CrossExchangeReport]:
        return await self._request(
            "GET", f"{_AGENT_BASE}/assets/{asset}/cross-exchange", model=CrossExchangeReport
        )

    async def get_events(
        self,
        limit: int = 50,
        cursor: Optional[str] = None,
        type: Optional[str] = None,
        asset: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[Any] = None,
    ) -> Envelope[EventsPage]:
        if isinstance(since, datetime):
            since = since.isoformat()
        return await self._request(
            "GET",
            f"{_AGENT_BASE}/events",
            params={
                "limit": limit,
                "cursor": cursor,
                "type": type,
                "asset": asset,
                "severity": severity,
                "since": since,
            },
            model=EventsPage,
        )

    async def iter_events(
        self,
        limit: int = 50,
        type: Optional[str] = None,
        asset: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[Any] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Async-paginate through durable event history (newest first)."""
        cursor: Optional[str] = None
        while True:
            page = await self.get_events(
                limit=limit, cursor=cursor, type=type, asset=asset, severity=severity, since=since
            )
            if page.data is None:
                return
            for event in page.data.items:
                yield event
            cursor = page.data.next_cursor
            if not cursor:
                return

    async def get_health(self) -> Envelope[SystemHealth]:
        return await self._request("GET", f"{_AGENT_BASE}/system/health", model=SystemHealth)

    # -- streaming -----------------------------------------------------------

    def _connect_ws(self, url: str) -> Any:
        """Open the WS connection (factored out so tests can substitute a fake)."""
        return _ws_connect(url, additional_headers={"X-API-Key": self.api_key})

    async def stream(
        self,
        assets: Optional[Sequence[str]] = None,
        venues: Optional[Sequence[str]] = None,
        event_types: Optional[Sequence[str]] = None,
        severities: Optional[Sequence[str]] = None,
        last_event_id: Optional[str] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Async generator over :class:`AgentEvent`.

        Sends the contract subscribe frame first, yields replayed events
        (when ``last_event_id`` is given) followed by live events. On
        disconnect it reconnects with exponential backoff (0.5s -> 30s cap,
        jittered) and resumes from the last received event's ``stream_id``
        for gap recovery. Events are deduped in memory by ``id`` and
        ``idempotency_key``. Heartbeats and ``subscribed`` frames are handled
        internally. Cancelling the consumer closes the generator cleanly.
        """
        url = build_stream_url(self.base_url)
        dedupe = DedupeSet()
        backoff = Backoff(base=0.5, cap=30.0)
        resume_id = last_event_id

        while True:
            try:
                async with self._connect_ws(url) as ws:
                    await ws.send(
                        build_subscribe_message(
                            assets=assets,
                            venues=venues,
                            event_types=event_types,
                            severities=severities,
                            last_event_id=resume_id,
                        )
                    )
                    backoff.reset()
                    async for raw in ws:
                        event = parse_stream_message(raw)
                        if event is None:
                            continue  # subscribed / heartbeat / unknown kinds
                        if dedupe.seen(event):
                            continue
                        if event.stream_id:
                            resume_id = event.stream_id
                        yield event
            except asyncio.CancelledError:
                raise
            except (WebSocketException, OSError):
                await _sleep(backoff.next_delay())
