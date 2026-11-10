"""Servidor real de backend para el e2e de Playwright (task 8.7).

Levanta Postgres 16 + Redis 7 con Testcontainers (o reutiliza
``E2E_DATABASE_URL``/``E2E_REDIS_URL`` si están definidas), corre la cadena real
de Alembic, siembra ``clinica-demo`` y arranca uvicorn en ``127.0.0.1:8000``.

Playwright lo declara como uno de los ``webServer``: espera ``GET /health`` y lo
baja al terminar la corrida. No usa datos reales ni secretos del repo.
"""

from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = int(os.environ.get("E2E_BACKEND_PORT", "8000"))
PASSWORD = os.environ.get("E2E_USER_PASSWORD", "demo-password-123")


def _normalize_postgres_url(url: str) -> str:
    """Testcontainers devuelve ``postgresql://``; el engine usa ``psycopg`` v3."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def _resolve_services(stack: ExitStack) -> tuple[str, str]:
    """URLs de Postgres y Redis: contenedores nuevos o los del entorno."""
    database_url = os.environ.get("E2E_DATABASE_URL")
    redis_url = os.environ.get("E2E_REDIS_URL")
    if database_url and redis_url:
        return _normalize_postgres_url(database_url), redis_url

    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

    postgres = stack.enter_context(PostgresContainer("postgres:16-alpine"))
    redis = stack.enter_context(RedisContainer("redis:7-alpine"))
    host = redis.get_container_host_ip()
    port = redis.get_exposed_port(6379)
    return (
        _normalize_postgres_url(postgres.get_connection_url(driver=None)),
        f"redis://{host}:{port}/0",
    )


def _migrate(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def _seed(database_url: str) -> None:
    from sqlalchemy import create_engine

    sys.path.insert(0, str(BACKEND_ROOT / "tests"))
    from fixtures.seed_auth_e2e import USER_EMAIL, seed

    engine = create_engine(database_url, future=True)
    try:
        account = seed(engine, password=PASSWORD)
    finally:
        engine.dispose()
    print(
        f"[e2e] cuenta lista: {account.tenant_slug} / {USER_EMAIL}",
        flush=True,
    )


def _export_settings(database_url: str, redis_url: str) -> None:
    """Variables que ``load_config`` exige; valores ficticios para el e2e."""
    os.environ.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_URL": database_url,
            "REDIS_URL": redis_url,
            "SESSION_SECRET": "s" * 64,
            "JWT_REFRESH_SECRET": "j" * 64,
            "MFA_ENCRYPTION_KEY": "m" * 32,
            "COOKIE_SECURE": "false",
        }
    )


def main() -> None:
    import uvicorn

    # uvicorn importa ``app.main`` por nombre: la raíz del backend tiene que estar
    # en ``sys.path`` (el script vive en ``backend/scripts``).
    sys.path.insert(0, str(BACKEND_ROOT))

    with ExitStack() as stack:
        database_url, redis_url = _resolve_services(stack)
        _migrate(database_url)
        _seed(database_url)
        _export_settings(database_url, redis_url)
        print(f"[e2e] uvicorn en http://{HOST}:{PORT}", flush=True)
        uvicorn.run(
            "app.main:create_app",
            factory=True,
            host=HOST,
            port=PORT,
            log_level="warning",
        )


if __name__ == "__main__":
    main()
