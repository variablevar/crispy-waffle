"""Async access layer for the SkyBus agent REST API.

Prefers the sibling ``skybus-client`` package when it is importable
(``from skybus_client import SkybusClient``) and falls back to plain httpx
calls against the agent REST endpoints documented in
``docs/AGENT_CONTRACT.md``. Never recalculates anything — pure proxy.
"""
from __future__ import annotations

import os
from typing import Any, Optional

AGENT_PREFIX = "/api/v1/agent"
DEFAULT_BASE_URL = "http://localhost:8123"
HTTP_TIMEOUT_SEC = 20.0


class SkybusApiError(Exception):
    """Structured error from (or about) the SkyBus agent API."""

    def __init__(
        self,
        code: str,
        message: str,
        status: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id

    def to_dict(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.status is not None:
            err["status"] = self.status
        if self.request_id is not None:
            err["request_id"] = self.request_id
        return {"error": err}


class MissingApiKeyError(SkybusApiError):
    def __init__(self) -> None:
        super().__init__(
            "missing_api_key",
            "SKYBUS_API_KEY is not set in the MCP server's environment. "
            "Set it in the server configuration (env block) and retry.",
        )


class _ClientUnavailable(Exception):
    """Internal: the sibling skybus-client package is not importable."""


def get_base_url() -> str:
    return os.environ.get("SKYBUS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def get_api_key() -> Optional[str]:
    key = os.environ.get("SKYBUS_API_KEY")
    return key if key else None


def _unwrap_envelope(payload: Any) -> dict[str, Any]:
    """Pass through the agent.v1 envelope metadata alongside ``data``."""
    if isinstance(payload, dict) and "data" in payload:
        return {
            "schema_version": payload.get("schema_version"),
            "request_id": payload.get("request_id"),
            "observed_at": payload.get("observed_at"),
            "processed_at": payload.get("processed_at"),
            "freshness_sec": payload.get("freshness_sec"),
            "stale": payload.get("stale"),
            "available": payload.get("available"),
            "provenance": payload.get("provenance"),
            "methodology_version": payload.get("methodology_version"),
            "data": payload.get("data"),
        }
    # Defensive: unexpected shape — return as-is under data.
    return {
        "schema_version": None,
        "request_id": None,
        "observed_at": None,
        "processed_at": None,
        "freshness_sec": None,
        "stale": None,
        "available": None,
        "provenance": None,
        "methodology_version": None,
        "data": payload,
    }


# ---------------------------------------------------------------------------
# skybus-client backend (preferred)
# ---------------------------------------------------------------------------


def _skybus_client_cls() -> Optional[type]:
    try:
        from skybus_client import SkybusClient  # type: ignore

        return SkybusClient
    except Exception:
        return None


_CLIENT_ERROR_CODES = {
    "SkybusAuthError": "unauthorized",
    "SkybusRateLimitError": "rate_limited",
    "SkybusUnavailableError": "upstream_unavailable",
    "SkybusError": "client_error",
}


async def _via_client(cls: type, method: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    api_key = get_api_key()
    if not api_key:
        raise MissingApiKeyError()
    try:
        async with cls(base_url=get_base_url(), api_key=api_key) as c:
            result = await getattr(c, method)(*args, **kwargs)
    except Exception as exc:
        code = _CLIENT_ERROR_CODES.get(type(exc).__name__, "client_error")
        raise SkybusApiError(code, str(exc) or type(exc).__name__) from exc
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    return _unwrap_envelope(result)


# ---------------------------------------------------------------------------
# httpx fallback backend
# ---------------------------------------------------------------------------


async def _httpx_get(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    import httpx

    api_key = get_api_key()
    if not api_key:
        raise MissingApiKeyError()
    url = get_base_url() + AGENT_PREFIX + path
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT_SEC, headers={"X-API-Key": api_key}
        ) as client:
            resp = await client.get(url, params=clean_params)
    except httpx.HTTPError as exc:
        raise SkybusApiError(
            "unreachable", f"SkyBus API unreachable at {get_base_url()}: {exc}"
        ) from exc

    if resp.status_code >= 400:
        code: str = f"http_{resp.status_code}"
        message = resp.text[:500]
        request_id = resp.headers.get("X-Request-ID")
        try:
            body = resp.json()
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict):
                code = err.get("code") or code
                message = err.get("message") or message
                request_id = err.get("request_id") or request_id
        except ValueError:
            pass
        raise SkybusApiError(code, message, resp.status_code, request_id)

    try:
        payload = resp.json()
    except ValueError as exc:
        raise SkybusApiError(
            "bad_response", "SkyBus API returned a non-JSON response"
        ) from exc
    return _unwrap_envelope(payload)


async def _request(
    client_method: str,
    path: str,
    params: Optional[dict[str, Any]] = None,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Dispatch via skybus-client when importable, else httpx."""
    cls = _skybus_client_cls()
    if cls is not None:
        try:
            return await _via_client(cls, client_method, *args, **kwargs)
        except _ClientUnavailable:
            pass
    return await _httpx_get(path, params)


# ---------------------------------------------------------------------------
# Public API — one coroutine per agent endpoint
# ---------------------------------------------------------------------------


async def fetch_market_overview() -> dict[str, Any]:
    return await _request("get_market_overview", "/market/overview")


async def fetch_snapshot(asset: str) -> dict[str, Any]:
    return await _request("get_snapshot", f"/assets/{asset}/snapshot", None, asset)


async def fetch_news(asset: Optional[str], limit: int) -> dict[str, Any]:
    if asset:
        return await _request(
            "get_news", f"/assets/{asset}/news", {"limit": limit}, asset, limit=limit
        )
    # Global news feed (not in contract v1 per-asset list; the sibling client
    # supports asset=None). If the server lacks it, a structured error
    # propagates to the caller.
    return await _request("get_news", "/news", {"limit": limit}, None, limit=limit)


async def fetch_liquidity(asset: str) -> dict[str, Any]:
    return await _request("get_liquidity", f"/assets/{asset}/liquidity", None, asset)


async def fetch_derivatives(asset: str) -> dict[str, Any]:
    return await _request("get_derivatives", f"/assets/{asset}/derivatives", None, asset)


async def fetch_scenarios(asset: str) -> dict[str, Any]:
    return await _request("get_scenarios", f"/assets/{asset}/scenarios", None, asset)


async def fetch_cross_exchange(asset: str) -> dict[str, Any]:
    return await _request(
        "get_cross_exchange", f"/assets/{asset}/cross-exchange", None, asset
    )


async def fetch_health() -> dict[str, Any]:
    return await _request("get_health", "/system/health")
