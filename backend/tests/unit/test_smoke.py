"""Backend harness smoke test (task 1.6)."""

from __future__ import annotations

from app.config import Settings
from app.main import create_app


def test_app_wires_the_platform_routes(settings: Settings) -> None:
    application = create_app(settings)

    paths = set(application.openapi()["paths"])

    assert {"/health", "/ready"} <= paths
