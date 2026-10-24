"""Async SQLAlchemy engine/session. Degrades to None when the DB is absent."""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

_engine: Any = None
_session_factory: Any = None
_available: bool = False


async def init_db(database_url: str | None) -> bool:
    """Create the async engine and probe the connection. Never raises."""
    global _engine, _session_factory, _available
    _engine = None
    _session_factory = None
    _available = False
    if not database_url:
        return False
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy import text

        engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _engine = engine
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
        _available = True
        log.info("database: connected")
    except Exception as exc:
        log.info("database: unavailable (%s); persistence disabled", exc)
    return _available


def db_available() -> bool:
    return _available


def get_engine() -> Optional[Any]:
    return _engine if _available else None


def session():
    """Async context manager yielding a session, or None when DB is down."""
    if not _available or _session_factory is None:
        return _NullSession()
    return _session_factory()


class _NullSession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


async def dispose_db() -> None:
    global _engine, _session_factory, _available
    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception:
            pass
    _engine = None
    _session_factory = None
    _available = False
