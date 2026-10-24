"""Request-ID / correlation-ID middleware for the agent API namespace."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.agentapi.auth import audit


class AgentRequestMiddleware(BaseHTTPMiddleware):
    """Assigns a ULID request id to /api/v1/agent/* calls, echoes correlation
    ids, and audits the request after the response is produced."""

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v1/agent"):
            return await call_next(request)

        import ulid

        request_id = str(ulid.new())
        request.state.request_id = request_id
        correlation_id = request.headers.get("x-correlation-id")
        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        if correlation_id:
            response.headers["X-Correlation-ID"] = correlation_id

        await audit(
            {
                "consumer": getattr(request.state, "consumer", None) or "anonymous",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "request_id": request_id,
                "latency_ms": round(latency_ms, 2),
            }
        )
        return response
