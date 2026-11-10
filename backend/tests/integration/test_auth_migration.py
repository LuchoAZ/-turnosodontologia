"""Integración de la migración 003_auth: DDL, rol y resolver (tasks 2.3/2.9)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

APP_ROLE = "odontologia_app"
RESOLVER_ROLE = "auth_resolver"

SESSION_COLUMNS = {
    "id",
    "user_id",
    "tenant_id",
    "credentials_version",
    "mfa_satisfied",
    "last_used_step",
    "expires_at",
    "revoked_at",
    "created_at",
}
REFRESH_COLUMNS = {
    "id",
    "session_id",
    "tenant_id",
    "family_id",
    "token_hash",
    "estado",
    "expires_at",
    "used_at",
    "replaced_by",
    "created_at",
}
AUTH_EVENT_COLUMNS = {"id", "tipo", "user_id", "tenant_id", "detail", "created_at"}
RESET_COLUMNS = {"id", "user_id", "token_hash", "expires_at", "used_at", "created_at"}
NEW_USER_COLUMNS = {
    "failed_login_count",
    "lockout_strikes",
    "locked_until",
    "last_lockout_at",
    "mfa_enrolled_at",
    "mfa_secret_key_version",
    "credentials_version",
    "last_totp_step",
}


def _columns(connection: Connection, table: str) -> set[str]:
    rows = connection.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    ).scalars()
    return set(rows)


def test_creates_the_four_auth_tables_with_the_design_columns(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        assert _columns(connection, "session") == SESSION_COLUMNS
        assert _columns(connection, "refresh_token") == REFRESH_COLUMNS
        assert _columns(connection, "auth_event") == AUTH_EVENT_COLUMNS
        assert _columns(connection, "password_reset_token") == RESET_COLUMNS


def test_adds_the_auth_columns_to_user(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        assert _columns(connection, "user") >= NEW_USER_COLUMNS


def test_creates_indexes_uniques_and_checks(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        indexes = set(
            connection.exec_driver_sql(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
            ).scalars()
        )
        assert {
            "session_tenant_user_idx",
            "session_expires_at_idx",
            "refresh_token_family_idx",
            "refresh_token_tenant_session_idx",
            "refresh_token_expires_at_idx",
            "auth_event_tenant_created_idx",
            "auth_event_user_created_idx",
            "password_reset_token_user_idx",
            "password_reset_token_expires_at_idx",
        } <= indexes

        uniques = set(
            connection.exec_driver_sql(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid IN ('refresh_token'::regclass, 'password_reset_token'::regclass)
                  AND i.indisunique
                """
            ).scalars()
        )
        assert "token_hash" in uniques

        checks = set(
            connection.exec_driver_sql(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid IN ('session'::regclass, 'refresh_token'::regclass,
                                   'user'::regclass)
                  AND contype = 'c'
                """
            ).scalars()
        )
        assert {
            "ck_session_expires_at",
            "ck_refresh_token_not_self_replaced",
            "ck_refresh_token_rotated_fields",
            "ck_user_failed_login_count",
        } <= checks


def test_auth_tables_force_rls(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                WHERE c.relname IN ('session', 'refresh_token', 'auth_event',
                                    'password_reset_token')
                """
            )
        ).all()

    by_name = {row[0]: (row[1], row[2]) for row in rows}
    assert by_name["session"] == (True, True)
    assert by_name["refresh_token"] == (True, True)
    assert by_name["auth_event"] == (False, False)
    assert by_name["password_reset_token"] == (False, False)


def test_auth_event_trigger_is_append_only(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        trigger = connection.exec_driver_sql(
            """
            SELECT tgname FROM pg_trigger
            WHERE tgrelid = 'auth_event'::regclass AND NOT tgisinternal
            """
        ).scalar_one()

    assert trigger == "auth_event_append_only"


def test_app_grants_on_auth_event_and_password_reset_token(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                f"SELECT has_table_privilege('{APP_ROLE}', 'auth_event', 'INSERT')"
            ).scalar_one()
            is True
        )
        assert (
            connection.exec_driver_sql(
                f"SELECT has_table_privilege('{APP_ROLE}', 'auth_event', 'SELECT')"
            ).scalar_one()
            is False
        )
        assert (
            connection.exec_driver_sql(
                f"""
                SELECT has_column_privilege(
                    '{APP_ROLE}', 'password_reset_token', 'created_at', 'SELECT'
                )
                """
            ).scalar_one()
            is False
        )
        assert (
            connection.exec_driver_sql(
                f"""
                SELECT has_column_privilege(
                    '{APP_ROLE}', 'password_reset_token', 'token_hash', 'SELECT'
                )
                """
            ).scalar_one()
            is True
        )


def test_auth_resolver_role_is_bypass_nologin_noinherit(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT rolsuper, rolbypassrls, rolcanlogin, rolinherit
                FROM pg_roles WHERE rolname = :role
                """
            ),
            {"role": RESOLVER_ROLE},
        ).one()

    assert tuple(row) == (False, True, False, False)


def _function_row(connection: Connection, name: str) -> tuple[bool, str, list[str] | None, str]:
    row = connection.execute(
        text(
            """
            SELECT prosecdef, proowner::regrole::text, proconfig, prosrc
            FROM pg_proc WHERE proname = :name
            """
        ),
        {"name": name},
    ).one()
    return bool(row[0]), str(row[1]), row[2], str(row[3])


@pytest.mark.parametrize(
    ("name", "signature"),
    [
        ("auth_resolve_session_by_sid", "auth_resolve_session_by_sid(uuid)"),
        ("auth_resolve_session_by_refresh", "auth_resolve_session_by_refresh(text)"),
    ],
)
def test_resolver_functions_are_confined(
    db_engine: Engine, name: str, signature: str
) -> None:
    with db_engine.connect() as connection:
        security_definer, owner, proconfig, source = _function_row(connection, name)

        assert security_definer is True
        assert owner == RESOLVER_ROLE
        assert proconfig is not None
        assert "search_path=pg_catalog, public" in proconfig
        assert "EXECUTE" not in source.upper().replace("GRANT EXECUTE", "")
        assert "format(" not in source.lower()

        acl = connection.exec_driver_sql(
            f"SELECT proacl::text FROM pg_proc WHERE oid = '{signature}'::regprocedure"
        ).scalar_one()
        assert acl is not None
        entries = acl.strip("{}").split(",")
        assert not any(entry.startswith("=") for entry in entries)
        assert (
            connection.exec_driver_sql(
                f"SELECT has_function_privilege('{APP_ROLE}', '{signature}', 'EXECUTE')"
            ).scalar_one()
            is True
        )

        result = connection.exec_driver_sql(
            f"SELECT pg_get_function_result('{signature}'::regprocedure)"
        ).scalar_one()
        for column in (
            "session_id",
            "tenant_id",
            "user_id",
            "expires_at",
            "revoked_at",
            "credentials_version",
        ):
            assert column in result
        for forbidden in ("password_hash", "email", "mfa_secret", "token_hash"):
            assert forbidden not in result


# --- Resolver en ejecución (S8.7) -------------------------------------------


@contextmanager
def _rolled_back(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            if transaction.is_active:
                transaction.rollback()


@contextmanager
def _as_app(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        connection.exec_driver_sql(f"SET ROLE {APP_ROLE}")
        try:
            yield connection
        finally:
            connection.rollback()
            connection.exec_driver_sql("RESET ROLE")
            connection.commit()


def _seed_session(connection: Connection) -> tuple[UUID, UUID, str]:
    tenant_id = uuid4()
    user_id = uuid4()
    session_id = uuid4()
    token_hash = uuid4().hex + uuid4().hex
    connection.execute(
        text(
            """
            INSERT INTO tenant (id, slug, nombre_comercial, cuit, estado)
            VALUES (:id, :slug, 'Clínica Resolver', :cuit, 'active')
            """
        ),
        {
            "id": tenant_id,
            "slug": f"resolver-{uuid4().hex[:8]}",
            "cuit": f"{uuid4().int % 10**11:011d}",
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO "user" (id, email, nombre, apellido, activo)
            VALUES (:id, :email, 'Ana', 'Pérez', true)
            """
        ),
        {"id": user_id, "email": f"resolver-{uuid4().hex[:8]}@example.test"},
    )
    connection.execute(
        text(
            """
            INSERT INTO session (id, user_id, tenant_id, credentials_version, expires_at)
            VALUES (:id, :user_id, :tenant_id, 0, now() + interval '1 hour')
            """
        ),
        {"id": session_id, "user_id": user_id, "tenant_id": tenant_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO refresh_token
                (id, session_id, tenant_id, family_id, token_hash, expires_at)
            VALUES (:id, :session_id, :tenant_id, :family_id, :token_hash,
                    now() + interval '1 hour')
            """
        ),
        {
            "id": uuid4(),
            "session_id": session_id,
            "tenant_id": tenant_id,
            "family_id": uuid4(),
            "token_hash": token_hash,
        },
    )
    return session_id, tenant_id, token_hash


def test_resolver_returns_the_session_without_tenant_context(db_engine: Engine) -> None:
    with _rolled_back(db_engine) as connection:
        session_id, tenant_id, token_hash = _seed_session(connection)

        by_sid = connection.execute(
            text("SELECT * FROM auth_resolve_session_by_sid(:sid)"), {"sid": session_id}
        ).mappings().one()
        by_refresh = connection.execute(
            text("SELECT * FROM auth_resolve_session_by_refresh(:hash)"),
            {"hash": token_hash},
        ).mappings().one()

    assert by_sid["tenant_id"] == tenant_id
    assert by_refresh["session_id"] == session_id
    assert set(by_sid) == {
        "session_id",
        "tenant_id",
        "user_id",
        "expires_at",
        "revoked_at",
        "credentials_version",
    }


def test_resolver_is_executable_by_the_app_role(db_engine: Engine) -> None:
    with _rolled_back(db_engine):
        pass

    with db_engine.connect() as seed:
        transaction = seed.begin()
        session_id, tenant_id, token_hash = _seed_session(seed)
        transaction.commit()

    try:
        with _as_app(db_engine) as connection:
            resolved = connection.execute(
                text("SELECT tenant_id FROM auth_resolve_session_by_sid(:sid)"),
                {"sid": session_id},
            ).scalar_one()
            resolved_by_refresh = connection.execute(
                text("SELECT tenant_id FROM auth_resolve_session_by_refresh(:hash)"),
                {"hash": token_hash},
            ).scalar_one()

        assert resolved == tenant_id
        assert resolved_by_refresh == tenant_id
    finally:
        with db_engine.begin() as cleanup:
            cleanup.execute(
                text("DELETE FROM tenant WHERE id = :id"), {"id": tenant_id}
            )


def test_direct_session_select_without_context_returns_zero_rows(db_engine: Engine) -> None:
    with db_engine.connect() as seed:
        transaction = seed.begin()
        _, tenant_id, _ = _seed_session(seed)
        transaction.commit()

    try:
        with _as_app(db_engine) as connection:
            total = connection.execute(text("SELECT count(*) FROM session")).scalar_one()

        assert total == 0
    finally:
        with db_engine.begin() as cleanup:
            cleanup.execute(
                text("DELETE FROM tenant WHERE id = :id"), {"id": tenant_id}
            )
