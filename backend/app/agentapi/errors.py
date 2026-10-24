"""Consistent agent-API error envelopes."""

from __future__ import annotations

from fastapi.responses import JSONResponse


def error_response(status: int, code: str, message: str, request_id: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )
