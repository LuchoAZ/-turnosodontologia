"""Liveness contract: GET /health (task 4.3)."""

from __future__ import annotations

from app.infra.probes import Probe
from app.infra.routers.ready import get_readiness_probes
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_has_no_business_data(client: TestClient) -> None:
    payload = client.get("/health").json()

    assert set(payload) == {"status"}


def test_health_stays_up_when_a_dependency_is_down(app: FastAPI) -> None:
    async def failing() -> None:
        raise RuntimeError("postgres is down")

    app.dependency_overrides[get_readiness_probes] = lambda: [Probe(name="postgres", check=failing)]

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
