"""Reversibilidad de la migración 002_core_tenancy.

Usa un contenedor **propio** (no el compartido de la suite) porque ``downgrade
base`` hace ``DROP ROLE odontologia_app`` y el rol es un objeto de clúster: si
otra base del mismo contenedor tuviera grants a ese rol, el ``DROP`` fallaría.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from testcontainers.community.postgres import PostgresContainer

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def _count(engine_url: str, sql: str) -> int:
    engine = create_engine(engine_url, future=True)
    try:
        with engine.connect() as connection:
            return int(connection.exec_driver_sql(sql).scalar_one())
    finally:
        engine.dispose()


def test_ciclo_downgrade_upgrade_es_reversible(docker_services: dict[str, str]) -> None:
    with PostgresContainer("postgres:16-alpine") as pg:
        url = _normalize_postgres_url(pg.get_connection_url(driver=None))

        config = Config()
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", url)

        tables = (
            "SELECT count(*) FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename IN ('tenant', 'membership')"
        )
        globals_sql = "SELECT count(*) FROM price_concept WHERE tenant_id IS NULL"

        command.upgrade(config, "head")
        assert _count(url, tables) == 2
        assert _count(url, globals_sql) == 80

        command.downgrade(config, "base")
        assert _count(url, tables) == 0

        command.upgrade(config, "head")
        assert _count(url, tables) == 2
        assert _count(url, globals_sql) == 80


def test_la_migracion_003_auth_es_reversible(docker_services: dict[str, str]) -> None:
    """``downgrade 002_core_tenancy`` borra el DDL y el rol; ``upgrade head`` los repone."""
    with PostgresContainer("postgres:16-alpine") as pg:
        url = _normalize_postgres_url(pg.get_connection_url(driver=None))

        config = Config()
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", url)

        auth_tables = (
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename IN "
            "('session', 'refresh_token', 'auth_event', 'password_reset_token')"
        )
        policies = (
            "SELECT count(*) FROM pg_policies WHERE policyname IN "
            "('session_tenant_isolation', 'refresh_token_tenant_isolation')"
        )
        trigger = (
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'auth_event_append_only' "
            "AND NOT tgisinternal"
        )
        functions = (
            "SELECT count(*) FROM pg_proc WHERE proname IN "
            "('auth_resolve_session_by_sid', 'auth_resolve_session_by_refresh', "
            "'auth_event_forbid_mutation')"
        )
        resolver_role = "SELECT count(*) FROM pg_roles WHERE rolname = 'auth_resolver'"
        user_columns = (
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'user' AND column_name IN "
            "('failed_login_count', 'lockout_strikes', 'locked_until', 'last_lockout_at', "
            "'mfa_enrolled_at', 'mfa_secret_key_version', 'credentials_version', "
            "'last_totp_step')"
        )

        command.upgrade(config, "head")
        assert _count(url, auth_tables) == 4
        assert _count(url, policies) == 2
        assert _count(url, trigger) == 1
        assert _count(url, functions) == 3
        assert _count(url, resolver_role) == 1
        assert _count(url, user_columns) == 8

        command.downgrade(config, "002_core_tenancy")
        assert _count(url, auth_tables) == 0
        assert _count(url, policies) == 0
        assert _count(url, trigger) == 0
        assert _count(url, functions) == 0
        assert _count(url, resolver_role) == 0
        assert _count(url, user_columns) == 0

        command.upgrade(config, "head")
        assert _count(url, auth_tables) == 4
        assert _count(url, resolver_role) == 1
        assert _count(url, user_columns) == 8
