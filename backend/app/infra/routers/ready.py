"""Readiness probe: verifies required dependencies behind injectable probes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.infra.probes import Probe, build_default_probes

router = APIRouter(tags=["platform"])


def get_readiness_probes(request: Request) -> list[Probe]:
    settings: Settings = request.app.state.settings
    return build_default_probes(settings)


@router.get("/ready")
async def ready(
    probes: Annotated[list[Probe], Depends(get_readiness_probes)],
) -> JSONResponse:
    unavailable: list[str] = []
    for probe in probes:
        try:
            await probe.check()
        except Exception:
            unavailable.append(probe.name)

    if unavailable:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "unavailable": unavailable},
        )
    return JSONResponse(status_code=200, content={"status": "ready"})
