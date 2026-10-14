from __future__ import annotations

import pytest
from redis import Redis
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration


def test_containers_smoke(pg_engine: Engine, docker_services: dict[str, str]) -> None:
    with pg_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1

    client = Redis.from_url(docker_services["redis_url"])
    try:
        assert client.ping() is True
    finally:
        client.close()
