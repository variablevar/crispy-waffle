"""Typed exceptions for skybus-client.

Every error raised by :class:`skybus_client.SkybusClient` subclasses
:class:`SkybusError` and carries the HTTP ``status`` (``None`` for pure
network failures), the server ``request_id`` (ULID, when known) and the
machine-readable error ``code`` from the contract error body.
"""

from __future__ import annotations

from typing import Optional


class SkybusError(Exception):
    """Base class for all skybus-client errors."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        request_id: Optional[str] = None,
        code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.request_id = request_id
        self.code = code

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"{type(self).__name__}(message={self.message!r}, status={self.status!r}, "
            f"request_id={self.request_id!r}, code={self.code!r})"
        )


class SkybusAuthError(SkybusError):
    """401 (missing/invalid key) or 403 (insufficient scope)."""


class SkybusRateLimitError(SkybusError):
    """429 rate-limited. ``retry_after`` mirrors the Retry-After header (seconds)."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class SkybusNotFoundError(SkybusError):
    """404 — unknown asset/endpoint (contract ``not_found`` code)."""


class SkybusUnavailableError(SkybusError):
    """5xx or network failure after all retries were exhausted."""


class SkybusStaleDataError(SkybusError):
    """Response data was older than the client's ``max_acceptable_staleness_sec``.

    Only raised when that opt-in client option is set; by default stale
    responses are returned with ``envelope.stale``/``is_fresh()`` for the
    caller to inspect.
    """
