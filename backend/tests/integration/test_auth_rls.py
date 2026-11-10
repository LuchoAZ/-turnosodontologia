"""Aislamiento cross-tenant de sesiones y refresh (RN-TEN-02, tasks 2.5-2.8).

Los tests hacen ``SET ROLE odontologia_app`` porque el usuario del contenedor es
superusuario y un superusuario ignora RLS: sin ese ``SET ROLE`` el verde sería
falso (``docs/core-tenancy.md``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from app.db.tenant_context import TENANT_SETTING_SQL
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

APP_ROLE = "odontologia_app"


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


@contextmanager
def _as_app(engine: Engine, tenant_id: UUID | None = None) -> Iterator[Connection]:
    with engine.connect() as connection:
        connection.exec_driver_sql(f"SET ROLE {APP_ROLE}")
        if tenant_id is not None:
            connection.execute(TENANT_SETTING_SQL, {"tenant_id": str(tenant_id)})
        try:
            yield connection
        finally:
            connection.rollback()
            connection.exec_driver_sql("RESET ROLE")
            connection.commit()


@contextmanager
def _two_tenants(engine: Engine) -> Iterator[tuple[UUID, UUID, UUID, UUID, UUID, UUID]]:
    """Siembra A y B con un usuario y una sesión/refresh cada una (commit real)."""
    tenant_a, tenant_b = uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    session_a, session_b = uuid4(), uuid4()
    refresh_a, refresh_b = uuid4(), uuid4()

    with engine.begin() as connection:
        for tenant_id, label in ((tenant_a, "a"), (tenant_b, "b")):
            connection.execute(
                text(
                    """
                    INSERT INTO tenant (id, slug, nombre_comercial, cuit, estado)
                    VALUES (:id, :slug, :nombre, :cuit, 'active')
                    """
                ),
                {
                    "id": tenant_id,
                    "slug": f"rls-{label}-{uuid4().hex[:8]}",
                    "nombre": f"Clínica {label.upper()}",
                    "cuit": f"{uuid4().int % 10**11:011d}",
                },
            )
        for user_id, label in ((user_a, "a"), (user_b, "b")):
            connection.execute(
                text(
                    """
                    INSERT INTO "user" (id, email, nombre, apellido, activo)
                    VALUES (:id, :email, 'Ana', 'Pérez', true)
                    """
                ),
                {"id": user_id, "email": f"rls-{label}-{uuid4().hex[:8]}@example.test"},
            )
        for session_id, tenant_id, user_id in (
            (session_a, tenant_a, user_a),
            (session_b, tenant_b, user_b),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO session (id, user_id, tenant_id, credentials_version, expires_at)
                    VALUES (:id, :user_id, :tenant_id, 0, now() + interval '1 hour')
                    """
                ),
                {"id": session_id, "user_id": user_id, "tenant_id": tenant_id},
            )
        for refresh_id, session_id, tenant_id in (
            (refresh_a, session_a, tenant_a),
            (refresh_b, session_b, tenant_b),
        ):
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
                    "id": refresh_id,
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "family_id": uuid4(),
                    "token_hash": uuid4().hex + uuid4().hex,
                },
            )

    try:
        yield tenant_a, tenant_b, user_a, user_b, session_a, session_b
    finally:
        with engine.begin() as connection:
            connection.execute(
                text('DELETE FROM "user" WHERE id IN (:a, :b)'),
                {"a": user_a, "b": user_b},
            )
            connection.execute(
                text("DELETE FROM tenant WHERE id IN (:a, :b)"),
                {"a": tenant_a, "b": tenant_b},
            )


def test_select_only_returns_the_context_tenant(db_engine: Engine) -> None:
    with _two_tenants(db_engine) as (tenant_a, _, _, _, session_a, session_b):
        with _as_app(db_engine, tenant_a) as connection:
            sessions = set(connection.execute(text("SELECT id FROM session")).scalars())
            refreshes = set(
                connection.execute(text("SELECT session_id FROM refresh_token")).scalars()
            )

        assert sessions == {session_a}
        assert refreshes == {session_a}
        assert session_b not in sessions


def test_select_without_context_returns_zero_rows(db_engine: Engine) -> None:
    with _two_tenants(db_engine):
        with _as_app(db_engine) as connection:
            sessions = connection.execute(text("SELECT count(*) FROM session")).scalar_one()
            refreshes = connection.execute(
                text("SELECT count(*) FROM refresh_token")
            ).scalar_one()

        assert sessions == 0
        assert refreshes == 0


def test_insert_with_a_foreign_tenant_is_rejected(db_engine: Engine) -> None:
    with (
        _two_tenants(db_engine) as (tenant_a, tenant_b, _, user_b, _, _),
        _as_app(db_engine, tenant_a) as connection,
    ):
        with pytest.raises(DBAPIError) as excinfo:
            connection.execute(
                text(
                    """
                    INSERT INTO session
                        (id, user_id, tenant_id, credentials_version, expires_at)
                    VALUES (:id, :user_id, :tenant_id, 0, now() + interval '1 hour')
                    """
                ),
                {"id": uuid4(), "user_id": user_b, "tenant_id": tenant_b},
            )
        assert _sqlstate(excinfo.value) == "42501"


def test_update_cannot_move_a_session_to_another_tenant(db_engine: Engine) -> None:
    with (
        _two_tenants(db_engine) as (tenant_a, tenant_b, _, _, session_a, _),
        _as_app(db_engine, tenant_a) as connection,
    ):
        with pytest.raises(DBAPIError) as excinfo:
            connection.execute(
                text("UPDATE session SET tenant_id = :tenant WHERE id = :id"),
                {"tenant": tenant_b, "id": session_a},
            )
        assert _sqlstate(excinfo.value) == "42501"


def test_update_and_delete_of_another_tenant_affect_zero_rows(db_engine: Engine) -> None:
    with _two_tenants(db_engine) as (tenant_a, _, _, _, _, session_b):
        with _as_app(db_engine, tenant_a) as connection:
            updated = connection.execute(
                text("UPDATE session SET last_used_step = 99 WHERE id = :id"),
                {"id": session_b},
            )
            deleted = connection.execute(
                text("DELETE FROM session WHERE id = :id"), {"id": session_b}
            )

        assert updated.rowcount == 0
        assert deleted.rowcount == 0

        with db_engine.connect() as check:
            remaining = check.execute(
                text("SELECT count(*) FROM session WHERE id = :id"), {"id": session_b}
            ).scalar_one()
        assert remaining == 1


def test_mutation_proof_superuser_sees_both_tenants(db_engine: Engine) -> None:
    """La receta de C-02: el mismo SELECT como superusuario ve A y B."""
    with _two_tenants(db_engine) as (tenant_a, _, _, _, session_a, session_b):
        with db_engine.connect() as superuser:
            visible = set(superuser.execute(text("SELECT id FROM session")).scalars())

        with _as_app(db_engine, tenant_a) as connection:
            with_context = set(connection.execute(text("SELECT id FROM session")).scalars())

    assert {session_a, session_b} <= visible
    assert with_context == {session_a}


def _insert_auth_event(engine: Engine, user_id: UUID, tenant_id: UUID) -> int:
    with _as_app(engine) as connection:
        connection.execute(
            text(
                """
                INSERT INTO auth_event (tipo, user_id, tenant_id, detail)
                VALUES ('login_success', :user_id, :tenant_id, '{"reason": "test"}')
                """
            ),
            {"user_id": user_id, "tenant_id": tenant_id},
        )
        connection.commit()

    # El rol de app no tiene SELECT (ni RETURNING): el id se lee como superusuario.
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(
                    """
                    SELECT id FROM auth_event
                    WHERE user_id = :user_id AND tenant_id = :tenant_id
                    ORDER BY id DESC LIMIT 1
                    """
                ),
                {"user_id": user_id, "tenant_id": tenant_id},
            ).scalar_one()
        )


def test_auth_event_cannot_be_read_by_the_app_role(db_engine: Engine) -> None:
    with _two_tenants(db_engine) as (tenant_a, _, user_a, _, _, _):
        _insert_auth_event(db_engine, user_a, tenant_a)

        with _as_app(db_engine) as connection:
            with pytest.raises(DBAPIError) as excinfo:
                connection.execute(text("SELECT count(*) FROM auth_event"))
            assert _sqlstate(excinfo.value) == "42501"


def test_auth_event_cannot_be_updated_or_deleted_even_by_superuser(
    db_engine: Engine,
) -> None:
    with _two_tenants(db_engine) as (tenant_a, _, user_a, _, _, _):
        event_id = _insert_auth_event(db_engine, user_a, tenant_a)

        with db_engine.connect() as connection:
            detail = connection.execute(
                text("SELECT detail FROM auth_event WHERE id = :id"), {"id": event_id}
            ).scalar_one()
        assert detail == {"reason": "test"}

        with db_engine.connect() as connection:
            with pytest.raises(DBAPIError) as update_error:
                connection.execute(
                    text("UPDATE auth_event SET detail = '{}' WHERE id = :id"),
                    {"id": event_id},
                )
            assert _sqlstate(update_error.value) == "55000"

        with db_engine.connect() as connection:
            with pytest.raises(DBAPIError) as delete_error:
                connection.execute(
                    text("DELETE FROM auth_event WHERE id = :id"), {"id": event_id}
                )
            assert _sqlstate(delete_error.value) == "55000"


def test_password_reset_token_grants_are_column_scoped(db_engine: Engine) -> None:
    with _two_tenants(db_engine) as (_, _, user_a, _, _, _):
        reset_id = uuid4()
        token_hash = uuid4().hex + uuid4().hex

        with _as_app(db_engine) as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO password_reset_token
                        (id, user_id, token_hash, expires_at, created_at)
                    VALUES (:id, :user_id, :token_hash, now() + interval '30 minutes', now())
                    """
                ),
                {"id": reset_id, "user_id": user_a, "token_hash": token_hash},
            )
            connection.commit()

        with _as_app(db_engine) as connection:
            selected = connection.execute(
                text(
                    """
                    SELECT id, user_id, token_hash, expires_at, used_at
                    FROM password_reset_token WHERE token_hash = :hash
                    """
                ),
                {"hash": token_hash},
            ).mappings().one()
            assert selected["id"] == reset_id

        with _as_app(db_engine) as connection:
            with pytest.raises(DBAPIError) as excinfo:
                connection.execute(text("SELECT created_at FROM password_reset_token"))
            assert _sqlstate(excinfo.value) == "42501"

        with _as_app(db_engine) as connection:
            updated = connection.execute(
                text("UPDATE password_reset_token SET used_at = now() WHERE id = :id"),
                {"id": reset_id},
            )
            assert updated.rowcount == 1

        with _as_app(db_engine) as connection:
            with pytest.raises(DBAPIError) as excinfo:
                connection.execute(
                    text(
                        "UPDATE password_reset_token SET expires_at = now() + interval '1 day' "
                        "WHERE id = :id"
                    ),
                    {"id": reset_id},
                )
            assert _sqlstate(excinfo.value) == "42501"
