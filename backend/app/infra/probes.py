"""Readiness probes for external dependencies (Postgres, Redis).

Probes are plain data so they can be injected/overridden in tests (the readiness
endpoint resolves them through a FastAPI dependency).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from redis import asyncio as aioredis
from sqlalchemy import text

from app.config import Settings
from app.db import create_engine


@dataclass(frozen=True)
class Probe:
    """A named async dependency check that raises on failure."""

    name: str
    check: Callable[[], Awaitable[None]]


async def check_postgres(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def check_redis(settings: Settings) -> None:
    client = aioredis.from_url(settings.redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()


def build_default_probes(settings: Settings) -> list[Probe]:
    """The dependency set the runtime requires before accepting traffic."""
    return [
        Probe(name="postgres", check=lambda: check_postgres(settings)),
        Probe(name="redis", check=lambda: check_redis(settings)),
    ]
