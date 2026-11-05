"""Integración del modelo base y la migración 002_core_tenancy.

Corre contra Postgres 16 real (Testcontainers). Los tests de RLS usan
``SET ROLE odontologia_app`` porque el usuario del contenedor es superusuario y
un superusuario **ignora** Row Level Security: sin ese ``SET ROLE`` el verde
sería falso.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.db.tenant_context import TENANT_SETTING_SQL
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

APP_ROLE = "odontologia_app"

TENANT_INSERT = text(
    """
    INSERT INTO tenant (id, slug, nombre_comercial, cuit, estado)
    VALUES (:id, :slug, :nombre, :cuit, 'active')
    """
)

USER_INSERT = text(
    """
    INSERT INTO "user" (id, email, nombre, apellido, activo)
    VALUES (:id, :email, :nombre, :apellido, true)
    """
)

MEMBERSHIP_INSERT = text(
    """
    INSERT INTO membership (id, tenant_id, user_id, rol, activo)
    VALUES (:id, :tenant_id, :user_id, 'owner', true)
    """
)

PRICE_INSERT = text(
    """
    INSERT INTO price_concept
        (id, tenant_id, codigo, descripcion, precio_default, alicuota_impuesto, activo)
    VALUES
        (:id, :tenant_id, :codigo, :descripcion, 1000.0000, 21.000, true)
    """
)


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


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
def _committed(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection, connection.begin():
        yield connection


@contextmanager
def _as_app(engine: Engine, tenant_id: UUID | None = None) -> Iterator[Connection]:
    with engine.connect() as connection:
        connection.exec_driver_sql(f"SET ROLE {APP_ROLE}")
        if tenant_id is not None:
            connection.execute(TENANT_SETTING_SQL, {"tenant_id": str(tenant_id)})
        try:
            yield connection
        finally:
            # Si el test provocó un error de RLS, la transacción quedó abortada:
            # hay que hacer rollback antes de RESET ROLE.
            connection.rollback()
            connection.exec_driver_sql("RESET ROLE")


def _unique_cuit() -> str:
    return f"{uuid4().int % 10**11:011d}"


def _create_tenant(connection: Connection, slug: str) -> UUID:
    tenant_id = uuid4()
    connection.execute(
        TENANT_INSERT,
        {
            "id": tenant_id,
            "slug": slug,
            "nombre": f"Clínica {slug}",
            "cuit": _unique_cuit(),
        },
    )
    return tenant_id


def _create_user(connection: Connection, email: str) -> UUID:
    user_id = uuid4()
    connection.execute(
        USER_INSERT,
        {
            "id": user_id,
            "email": email,
            "nombre": "Ana",
            "apellido": "Pérez",
        },
    )
    return user_id


def _create_membership(connection: Connection, tenant_id: UUID, user_id: UUID) -> UUID:
    membership_id = uuid4()
    connection.execute(
        MEMBERSHIP_INSERT,
        {"id": membership_id, "tenant_id": tenant_id, "user_id": user_id},
    )
    return membership_id


def _seed_two_tenants(
    connection: Connection,
) -> tuple[UUID, UUID, UUID, UUID, UUID, UUID]:
    """Crea A y B con un usuario y una membership cada uno.

    Devuelve ``(tenant_a, tenant_b, user_a, user_b, membership_a, membership_b)``.
    """
    tenant_a = _create_tenant(connection, f"a-{uuid4().hex[:8]}")
    tenant_b = _create_tenant(connection, f"b-{uuid4().hex[:8]}")
    user_a = _create_user(connection, f"a-{uuid4().hex[:8]}@example.com")
    user_b = _create_user(connection, f"b-{uuid4().hex[:8]}@example.com")
    membership_a = _create_membership(connection, tenant_a, user_a)
    membership_b = _create_membership(connection, tenant_b, user_b)
    return tenant_a, tenant_b, user_a, user_b, membership_a, membership_b


def test_la_migracion_crea_las_seis_tablas_y_el_enum_de_roles(db_engine: Engine) -> None:
    with _rolled_back(db_engine) as connection:
        tables = set(
            connection.exec_driver_sql(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).scalars()
        )
        assert {
            "tenant",
            "user",
            "membership",
            "specialty",
            "price_concept",
            "currency",
        } <= tables

        roles = list(
            connection.exec_driver_sql(
                """
                SELECT e.enumlabel
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'role'
                ORDER BY e.enumsortorder
                """
            ).scalars()
        )
        assert roles == [
            "owner",
            "clinical_admin",
            "professional",
            "assistant",
            "front_desk",
            "billing",
            "patient",
            "external_lab",
            "accountant",
        ]


def test_membership_sin_tenant_es_rechazada(db_engine: Engine) -> None:
    with _rolled_back(db_engine) as connection:
        user_id = _create_user(connection, f"x-{uuid4().hex[:8]}@example.com")

        with pytest.raises(IntegrityError) as exc:
            connection.execute(
                text(
                    """
                    INSERT INTO membership (id, tenant_id, user_id, rol, activo)
                    VALUES (:id, NULL, :user_id, 'owner', true)
                    """
                ),
                {"id": uuid4(), "user_id": user_id},
            )

        assert _sqlstate(exc.value) == "23502"


def test_membership_con_usuario_inexistente_es_rechazada(db_engine: Engine) -> None:
    with _rolled_back(db_engine) as connection:
        tenant_id = _create_tenant(connection, f"c-{uuid4().hex[:8]}")

        with pytest.raises(IntegrityError) as exc:
            connection.execute(
                MEMBERSHIP_INSERT,
                {"id": uuid4(), "tenant_id": tenant_id, "user_id": uuid4()},
            )

        assert _sqlstate(exc.value) == "23503"


def test_codigo_global_duplicado_es_rechazado_y_el_override_del_tenant_es_permitido(
    db_engine: Engine,
) -> None:
    with _rolled_back(db_engine) as connection:
        codigo = f"TEST-{uuid4().hex[:8]}"
        tenant_id = _create_tenant(connection, f"d-{uuid4().hex[:8]}")
        params: dict[str, Any] = {
            "codigo": codigo,
            "descripcion": "Concepto de prueba",
        }

        connection.execute(PRICE_INSERT, {**params, "id": uuid4(), "tenant_id": None})

        with (
            pytest.raises(IntegrityError) as exc,
            connection.begin_nested(),
        ):
            connection.execute(PRICE_INSERT, {**params, "id": uuid4(), "tenant_id": None})
        assert _sqlstate(exc.value) == "23505"

        # El mismo código global y en un tenant sí coexisten (override).
        connection.execute(PRICE_INSERT, {**params, "id": uuid4(), "tenant_id": tenant_id})


def test_segundo_owner_activo_es_rechazado(db_engine: Engine) -> None:
    """RN-TEN-04: a lo sumo un ``owner`` activo por tenant."""
    with _rolled_back(db_engine) as connection:
        tenant_a, _, _, user_b, _, _ = _seed_two_tenants(connection)

        with pytest.raises(IntegrityError) as exc:
            connection.execute(
                MEMBERSHIP_INSERT,
                {"id": uuid4(), "tenant_id": tenant_a, "user_id": user_b},
            )

        assert _sqlstate(exc.value) == "23505"


def test_owner_inactivo_no_bloquea_al_owner_activo(db_engine: Engine) -> None:
    with _rolled_back(db_engine) as connection:
        tenant_a, _, _, user_b, membership_a, _ = _seed_two_tenants(connection)

        connection.execute(
            text("UPDATE membership SET activo = false WHERE id = :id"),
            {"id": membership_a},
        )
        # El índice parcial solo cubre filas activas: el owner nuevo se acepta.
        _create_membership(connection, tenant_a, user_b)


def test_el_seed_deja_los_catalogos_minimos(db_engine: Engine) -> None:
    with _rolled_back(db_engine) as connection:
        currencies = connection.exec_driver_sql(
            "SELECT codigo FROM currency ORDER BY codigo"
        ).scalars()
        assert list(currencies) == ["ARS", "USD"]

        specialties = connection.exec_driver_sql(
            "SELECT count(*) FROM specialty WHERE tenant_id IS NULL"
        ).scalar_one()
        assert specialties == 9

        global_prices = connection.exec_driver_sql(
            "SELECT count(*) FROM price_concept WHERE tenant_id IS NULL"
        ).scalar_one()
        assert global_prices == 80


def test_rls_un_tenant_solo_ve_sus_filas(db_engine: Engine) -> None:
    with _committed(db_engine) as setup:
        tenant_a, tenant_b, *_ = _seed_two_tenants(setup)

    with _as_app(db_engine, tenant_a) as connection:
        visible = set(connection.execute(text("SELECT tenant_id FROM membership")).scalars())

    assert visible == {tenant_a}
    assert tenant_b not in visible


def test_rls_sin_contexto_es_fail_closed(db_engine: Engine) -> None:
    with _committed(db_engine) as setup:
        _seed_two_tenants(setup)

    with _as_app(db_engine) as connection:
        count = connection.execute(text("SELECT count(*) FROM membership")).scalar_one()

    assert count == 0


def test_rls_update_y_delete_cross_tenant_no_afectan_filas(db_engine: Engine) -> None:
    with _committed(db_engine) as setup:
        tenant_a, _, _, _, _, membership_b = _seed_two_tenants(setup)

    with _as_app(db_engine, tenant_a) as connection:
        updated = connection.execute(
            text("UPDATE membership SET activo = false WHERE id = :id"),
            {"id": membership_b},
        ).rowcount
        deleted = connection.execute(
            text("DELETE FROM membership WHERE id = :id"), {"id": membership_b}
        ).rowcount

    assert updated == 0
    assert deleted == 0

    with _rolled_back(db_engine) as check:
        still_there = check.execute(
            text("SELECT count(*) FROM membership WHERE id = :id"),
            {"id": membership_b},
        ).scalar_one()
    assert still_there == 1


def test_rls_escritura_cross_tenant_es_rechazada(db_engine: Engine) -> None:
    with _committed(db_engine) as setup:
        tenant_a, tenant_b, _, user_b, _, _ = _seed_two_tenants(setup)

    with (
        _as_app(db_engine, tenant_a) as connection,
        pytest.raises(DBAPIError) as exc,
    ):
        connection.execute(
            MEMBERSHIP_INSERT,
            {"id": uuid4(), "tenant_id": tenant_b, "user_id": user_b},
        )

    assert _sqlstate(exc.value) == "42501"


def test_rls_el_tenant_no_puede_escribir_en_el_catalogo_global(db_engine: Engine) -> None:
    with _committed(db_engine) as setup:
        tenant_a, *_ = _seed_two_tenants(setup)

    with (
        _as_app(db_engine, tenant_a) as connection,
        pytest.raises(DBAPIError) as exc,
    ):
        connection.execute(
            PRICE_INSERT,
            {
                "id": uuid4(),
                "tenant_id": None,
                "codigo": f"GLOBAL-{uuid4().hex[:8]}",
                "descripcion": "Intento de escribir el catálogo global",
            },
        )

    assert _sqlstate(exc.value) == "42501"


def test_rls_catalogo_global_visible_para_todos_y_override_solo_para_su_tenant(
    db_engine: Engine,
) -> None:
    with _committed(db_engine) as setup:
        tenant_a, tenant_b, *_ = _seed_two_tenants(setup)
        codigo_b = f"OVR-{uuid4().hex[:8]}"
        setup.execute(
            PRICE_INSERT,
            {
                "id": uuid4(),
                "tenant_id": tenant_b,
                "codigo": codigo_b,
                "descripcion": "Override de B",
            },
        )

    with _as_app(db_engine, tenant_a) as connection:
        globals_visible = connection.execute(
            text("SELECT count(*) FROM price_concept WHERE tenant_id IS NULL")
        ).scalar_one()
        override_b_visible = connection.execute(
            text("SELECT count(*) FROM price_concept WHERE codigo = :codigo"),
            {"codigo": codigo_b},
        ).scalar_one()

    assert globals_visible == 80
    assert override_b_visible == 0


def test_mutacion_sin_rls_el_mismo_query_filtraria(db_engine: Engine) -> None:
    """Prueba de mutación del gate RN-TEN-02.

    El mismo ``SELECT`` como owner/superusuario (sin ``SET ROLE``) ve filas de A
    **y** de B; con ``SET ROLE odontologia_app`` ve solo A. Demuestra que el
    verde depende de la política RLS y no de un ``WHERE`` accidental.
    """
    with _committed(db_engine) as setup:
        tenant_a, tenant_b, *_ = _seed_two_tenants(setup)

    with _rolled_back(db_engine) as owner:
        without_rls = set(owner.execute(text("SELECT tenant_id FROM membership")).scalars())

    with _as_app(db_engine, tenant_a) as connection:
        with_rls = set(connection.execute(text("SELECT tenant_id FROM membership")).scalars())

    assert {tenant_a, tenant_b} <= without_rls
    assert with_rls == {tenant_a}


def test_el_contexto_de_tenant_no_se_filtra_entre_transacciones_del_pool(
    db_engine: Engine,
) -> None:
    with _committed(db_engine) as setup:
        tenant_a, *_ = _seed_two_tenants(setup)

    with db_engine.connect() as connection:
        # SET ROLE se commitea y persiste durante la sesión de la conexión.
        with connection.begin():
            connection.exec_driver_sql(f"SET ROLE {APP_ROLE}")

        with connection.begin():
            connection.execute(TENANT_SETTING_SQL, {"tenant_id": str(tenant_a)})
            inside = connection.execute(text("SELECT count(*) FROM membership")).scalar_one()

        # Misma conexión del pool, nueva transacción, sin fijar tenant.
        with connection.begin():
            outside = connection.execute(text("SELECT count(*) FROM membership")).scalar_one()

        connection.exec_driver_sql("RESET ROLE")
        connection.commit()

    assert inside == 1
    assert outside == 0
