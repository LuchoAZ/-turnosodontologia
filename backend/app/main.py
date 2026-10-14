"""FastAPI entrypoint.

``create_app`` builds the application (config is validated at startup through the
lifespan, before any traffic is accepted). ``config_or_exit`` is the fail-fast
boot seam used by the CLI entrypoint: it exits with a non-zero code and a message
that names the offending variable.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from pydantic import ValidationError

from app.config import Settings, format_config_error, load_config
from app.infra.observability import setup_observability
from app.infra.routers.health import router as health_router
from app.infra.routers.ready import router as ready_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved = settings if settings is not None else load_config()
        application.state.settings = resolved
        application.state.observability = setup_observability(resolved)
        yield

    application = FastAPI(
        title="Gestión Odontológica PyME API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(ready_router)
    return application


def config_or_exit(env: Mapping[str, str] | None = None) -> Settings:
    try:
        return load_config(env)
    except ValidationError as exc:
        print(format_config_error(exc), file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> None:
    settings = config_or_exit()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8000)


# Module-level app for `uvicorn app.main:app`. Config is validated on startup.
app = create_app()
