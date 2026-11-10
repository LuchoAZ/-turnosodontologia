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
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.v1.auth.router import router as auth_router
from app.config import Settings, format_config_error, load_config
from app.db.engine import create_db_engine, create_session_factory
from app.db.redis import create_redis_client
from app.domain.auth.errors import AuthError
from app.infra.observability import setup_observability
from app.infra.routers.health import router as health_router
from app.infra.routers.ready import router as ready_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved = settings if settings is not None else load_config()
        application.state.settings = resolved
        application.state.observability = setup_observability(resolved)
        engine = create_db_engine(resolved)
        redis_client = create_redis_client(resolved)
        application.state.db_engine = engine
        application.state.session_factory = create_session_factory(engine)
        application.state.redis = redis_client
        try:
            yield
        finally:
            redis_client.close()
            engine.dispose()

    application = FastAPI(
        title="Gestión Odontológica PyME API",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.exception_handler(AuthError)
    async def _auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(),
            headers=exc.headers(),
        )

    application.include_router(health_router)
    application.include_router(ready_router)
    application.include_router(auth_router)
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
