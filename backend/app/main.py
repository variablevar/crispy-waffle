"""SkyBus FastAPI application factory.

Lifespan boots the cache (Redis w/ in-memory fallback), the database
(optional), the websocket ingestors, the pollers, the alert evaluator and the
agent event detectors. With workers disabled (tests) the app serves REST
endpoints only.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agentapi.auth import _HTTPErrorResponse
from app.agentapi.errors import error_response
from app.agentapi.middleware import AgentRequestMiddleware
from app.agentapi import routers as agent_routers
from app.agentapi import stream as agent_stream
from app.api.routers import alerts, coins, market, news, system
from app.core import db as core_db
from app.core.cache import init_cache
from app.core.config import get_settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_cache(settings.redis_url)
    await core_db.init_db(settings.database_url)

    poller_tasks: list[asyncio.Task] = []
    evaluator_task: asyncio.Task | None = None
    event_tasks: list[asyncio.Task] = []
    ingestor = None
    if settings.workers_enabled:
        from app.events import start_events, stop_events
        from app.workers import pollers
        from app.workers.alerts import evaluator_loop
        from app.workers.ingestor import get_ingestor

        poller_tasks = await pollers.start_pollers()
        evaluator_task = asyncio.create_task(evaluator_loop(), name="alert_evaluator")
        event_tasks = await start_events()
        ingestor = get_ingestor()
        ingestor.start(settings.tracked_symbol_list)

    yield

    if ingestor is not None:
        await ingestor.stop()
    if evaluator_task is not None:
        evaluator_task.cancel()
        await asyncio.gather(evaluator_task, return_exceptions=True)
    if event_tasks:
        from app.events import stop_events

        await stop_events(event_tasks)
    if poller_tasks:
        from app.workers import pollers

        await pollers.stop_pollers(poller_tasks)
    await core_db.dispose_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SkyBus API",
        version="1.1.0",
        description="Real-time crypto news & trading intelligence. All payloads carry "
        "source, timestamps and staleness; unavailable sources are reported, never fabricated. "
        "Machine consumers use the authenticated /api/v1/agent namespace.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AgentRequestMiddleware)

    app.include_router(market.router, prefix="/api/v1")
    app.include_router(coins.router, prefix="/api/v1")
    app.include_router(news.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(system.router, prefix="/api/v1")
    # Agent namespace (authenticated)
    app.include_router(agent_routers.router, prefix="/api/v1/agent")
    app.include_router(agent_stream.router, prefix="/api/v1/agent")

    @app.exception_handler(_HTTPErrorResponse)
    async def _agent_auth_error(request: Request, exc: _HTTPErrorResponse):
        return exc.response

    @app.exception_handler(HTTPException)
    async def _agent_http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/v1/agent"):
            code = {404: "not_found", 401: "unauthorized", 403: "forbidden", 429: "rate_limited"}.get(
                exc.status_code, "bad_request"
            )
            request_id = getattr(request.state, "request_id", "")
            return error_response(exc.status_code, code, str(exc.detail), request_id)
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


app = create_app()
