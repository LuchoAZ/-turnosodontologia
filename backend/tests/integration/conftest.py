from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer


def _docker_available() -> bool:
    """True when a Docker daemon is reachable; nothing else is skipped."""
    try:
        from testcontainers.core.docker_client import DockerClient

        DockerClient().client.ping()
    except Exception:
        return False
    return True


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


@pytest.fixture(scope="session")
def docker_services() -> Iterator[dict[str, str]]:
    """Start real Postgres 16 + Redis 7 containers for the session.

    Skips only when Docker itself is unreachable; any other failure (bad image,
    misconfigured helper) propagates and fails the test instead of hiding.
    """
    if not _docker_available():
        pytest.skip("Docker is not available")
    with (
        PostgresContainer("postgres:16-alpine") as pg,
        RedisContainer("redis:7-alpine") as redis,
    ):
        redis_host = redis.get_container_host_ip()
        redis_port = redis.get_exposed_port(6379)
        yield {
            "postgres_url": _normalize_postgres_url(pg.get_connection_url(driver=None)),
            "redis_url": f"redis://{redis_host}:{redis_port}/0",
        }


@pytest.fixture
def pg_engine(docker_services: dict[str, str]) -> Iterator[Engine]:
    eng = create_engine(docker_services["postgres_url"], future=True)
    try:
        yield eng
    finally:
        eng.dispose()
