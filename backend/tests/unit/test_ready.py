"""Readiness contract: GET /ready with injectable probes (task 4.5)."""

from __future__ import annotations

from app.infra.probes import Probe
from app.infra.routers.ready import get_readiness_probes
from fastapi import FastAPI
from fastapi.testclient import TestClient


async def _ok() -> None:
    return None


async def _fail() -> None:
    raise ConnectionError("unreachable")


def _override(app: FastAPI, probes: list[Probe]) -> None:
    app.dependency_overrides[get_readiness_probes] = lambda: probes


def test_ready_returns_200_when_all_dependencies_up(app: FastAPI) -> None:
    _override(app, [Probe(name="postgres", check=_ok), Probe(name="redis", check=_ok)])

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ready_returns_503_and_names_the_down_dependency(app: FastAPI) -> None:
    _override(app, [Probe(name="postgres", check=_ok), Probe(name="redis", check=_fail)])

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["unavailable"] == ["redis"]


def test_ready_returns_503_and_names_every_down_dependency(app: FastAPI) -> None:
    _override(app, [Probe(name="postgres", check=_fail), Probe(name="redis", check=_fail)])

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert set(response.json()["unavailable"]) == {"postgres", "redis"}
