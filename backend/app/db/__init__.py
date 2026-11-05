"""Database engine helpers (SQLAlchemy 2.0).

C-01 ships no business models — only the engine factory used by readiness probes
and (later) by C-02 migrations/models.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def to_async_url(url: str) -> str:
    """Normalize a libpq URL to its asyncpg dialect."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(to_async_url(database_url), pool_pre_ping=True)
