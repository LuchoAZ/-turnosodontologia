from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.config import Settings, load_config
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient

BASE_ENV: dict[str, str] = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/odontologia",
    "REDIS_URL": "redis://localhost:6379/0",
    "SESSION_SECRET": "s" * 64,
    "JWT_REFRESH_SECRET": "j" * 64,
}


@pytest.fixture
def base_env() -> dict[str, str]:
    return dict(BASE_ENV)


@pytest.fixture
def settings(base_env: dict[str, str]) -> Settings:
    return load_config(base_env)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
