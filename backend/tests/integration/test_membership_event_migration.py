"""Migración `004_rbac`: auditoría `membership_event` append-only (design D5).

Los tests de estructura corren contra la base migrada compartida. La
reversibilidad usa un contenedor **propio** porque `downgrade 003_auth` borra el
tipo, la tabla y la función: hacerlo sobre la base compartida dejaría al resto de
la suite sin el esquema. El append-only se prueba también como **superusuario**:
si el trigger no existe, el superusuario podría mutar la auditoría y el test
fallaría (RLS no protege de eso).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.db.tenant_context import TENANT_SETTING_SQL
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from testcontainers.community.postgres import PostgresContainer

APP_ROLE = "odontologia_app"

TIPOS_ESPERADOS: tuple[str, ...] = (
    "member_created",
    "member_reactivated",
    "member_role_changed",
    "member_deactivated",
    "ownership_transferred",
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


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


def _detalle(engine: Engine, event_id: int) -> tuple[str, str | None, str | None]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT tipo::text, actor_user_id::text, target_user_id::text
                FROM membership_event WHERE id = :id
                """
            ),
            {"id": event_id},
        ).one()
    return row[0], row[1], row[2]


def _insert_event(
    engine: Engine,
    tenant_id: UUID,
    *,
    actor_user_id: UUID | None,
    target_user_id: UUID | None,
    tipo: str = "member_created",
) -> int:
    """Inserta como superusuario (el rol de app no puede leer ni usar ``RETURNING``)."""
    with engine.begin() as connection:
        return int(
            connection.execute(
                text(
                    """
                    INSERT INTO membership_event
                        (tenant_id, actor_user_id, target_user_id, tipo, detail)
                    VALUES (:tenant_id, :actor, :target,
                            CAST(:tipo AS membership_event_tipo), '{"rol": "front_desk"}')
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "actor": actor_user_id,
                    "target": target_user_id,
                    "tipo": tipo,
                },
            ).scalar_one()
        )


def test_el_tipo_membership_event_tiene_los_cinco_valores(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        labels = tuple(
            connection.execute(
                text(
                    """
                    SELECT e.enumlabel
                    FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                    WHERE t.typname = 'membership_event_tipo'
                    ORDER BY e.enumsortorder
                    """
                )
            ).scalars()
        )

    assert labels == TIPOS_ESPERADOS


def test_la_tabla_tiene_las_columnas_y_nulabilidad_del_diseno(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT column_name, is_nullable, udt_name, column_default, is_identity
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'membership_event'
                """
            )
        ).mappings()
        columns = {row["column_name"]: dict(row) for row in rows}

    assert set(columns) == {
        "id",
        "tenant_id",
        "actor_user_id",
        "target_user_id",
        "tipo",
        "detail",
        "created_at",
    }
    # ``tenant_id`` es dato de negocio: siempre presente (a diferencia de auth_event).
    assert columns["tenant_id"]["is_nullable"] == "NO"
    assert columns["tenant_id"]["udt_name"] == "uuid"
    # Los ids de usuario sobreviven a la baja del usuario.
    assert columns["actor_user_id"]["is_nullable"] == "YES"
    assert columns["target_user_id"]["is_nullable"] == "YES"
    assert columns["actor_user_id"]["udt_name"] == "uuid"
    assert columns["target_user_id"]["udt_name"] == "uuid"
    # ``tipo`` es el enum recién creado, no texto libre.
    assert columns["tipo"]["is_nullable"] == "NO"
    assert columns["tipo"]["udt_name"] == "membership_event_tipo"
    assert columns["detail"]["is_nullable"] == "NO"
    assert columns["detail"]["udt_name"] == "jsonb"
    assert columns["detail"]["column_default"] == "'{}'::jsonb"
    assert columns["created_at"]["is_nullable"] == "NO"
    assert "now()" in columns["created_at"]["column_default"]
    # ``id`` es identidad generada por la base.
    assert columns["id"]["is_identity"] == "YES"


def test_las_claves_foraneas_borran_en_null_y_en_cascada(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT conname, confdeltype, confrelid::regclass::text AS referencia
                FROM pg_constraint
                WHERE conrelid = 'membership_event'::regclass AND contype = 'f'
                """
            )
        ).mappings()
        fks = {row["conname"]: dict(row) for row in rows}

    assert len(fks) == 3
    por_columna = {
        "membership_event_actor_user_id_fkey": "actor_user_id",
        "membership_event_target_user_id_fkey": "target_user_id",
        "membership_event_tenant_id_fkey": "tenant_id",
    }
    for nombre, columna in por_columna.items():
        assert nombre in fks, f"falta la FK {nombre} de {columna}"
    assert fks["membership_event_actor_user_id_fkey"]["confdeltype"] == "n"
    assert fks["membership_event_target_user_id_fkey"]["confdeltype"] == "n"
    assert fks["membership_event_tenant_id_fkey"]["confdeltype"] == "c"


def test_el_indice_por_tenant_y_fecha_existe(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        indexdef = connection.execute(
            text(
                """
                SELECT indexdef FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'membership_event'
                  AND indexname = 'membership_event_tenant_created_idx'
                """
            )
        ).scalar_one_or_none()

    assert indexdef is not None, "falta membership_event_tenant_created_idx"
    assert "(tenant_id, created_at)" in indexdef


def test_rls_esta_habilitada_y_forzada_con_la_politica_del_tenant(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        rls = connection.execute(
            text(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class WHERE oid = 'membership_event'::regclass
                """
            )
        ).one()
        policy = connection.execute(
            text(
                """
                SELECT permissive, qual, with_check
                FROM pg_policies
                WHERE schemaname = 'public' AND tablename = 'membership_event'
                """
            )
        ).mappings().all()

    assert rls[0] is True
    assert rls[1] is True, "FORCE ROW LEVEL SECURITY es obligatorio (RN-TEN-02)"
    assert len(policy) == 1
    assert policy[0]["permissive"] == "PERMISSIVE"
    for expression in (policy[0]["qual"], policy[0]["with_check"]):
        assert "NULLIF" in expression
        assert "app.current_tenant" in expression
        assert "tenant_id" in expression


def test_el_rol_de_app_puede_insertar_y_no_leer(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        privileges = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT privilege_type FROM information_schema.table_privileges
                    WHERE table_schema = 'public' AND table_name = 'membership_event'
                      AND grantee = :grantee
                    """
                ),
                {"grantee": APP_ROLE},
            )
        }

    assert privileges == {"INSERT"}, "la auditoría solo se escribe: ni SELECT ni UPDATE/DELETE"


def test_el_trigger_append_only_dispara_antes_de_update_y_delete(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        triggers = connection.execute(
            text(
                """
                SELECT tgname, tgtype FROM pg_trigger
                WHERE tgrelid = 'membership_event'::regclass AND NOT tgisinternal
                """
            )
        ).mappings().all()
        public_execute = connection.execute(
            text(
                """
                SELECT count(*)
                FROM pg_proc p,
                     aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
                WHERE p.proname = 'membership_event_forbid_mutation'
                  AND a.grantee = 0 AND a.privilege_type = 'EXECUTE'
                """
            )
        ).scalar_one()

    assert len(triggers) == 1
    assert triggers[0]["tgname"] == "membership_event_append_only"
    # bits: 2 = BEFORE, 8 = DELETE, 16 = UPDATE, 1 = ROW.
    assert triggers[0]["tgtype"] & 2, "el trigger debe ser BEFORE"
    assert triggers[0]["tgtype"] & 8, "el trigger debe cubrir DELETE"
    assert triggers[0]["tgtype"] & 16, "el trigger debe cubrir UPDATE"
    assert public_execute == 0, "la función del trigger no se expone a PUBLIC"


def test_el_rol_de_app_no_puede_leer_ni_con_contexto(db_engine: Engine, seeder: Any) -> None:
    tenant_id = seeder.tenant()

    with _as_app(db_engine) as connection, pytest.raises(DBAPIError) as sin_contexto:
        connection.execute(text("SELECT count(*) FROM membership_event"))
    assert _sqlstate(sin_contexto.value) == "42501"

    with _as_app(db_engine, tenant_id) as connection, pytest.raises(DBAPIError) as con_contexto:
        connection.execute(text("SELECT count(*) FROM membership_event"))
    assert _sqlstate(con_contexto.value) == "42501"


def test_el_insert_del_rol_de_app_exige_contexto_del_tenant(
    db_engine: Engine, seeder: Any
) -> None:
    tenant_id = seeder.tenant()
    actor = seeder.user()

    # Sin contexto: la política RLS rechaza el WITH CHECK.
    with _as_app(db_engine) as connection, pytest.raises(DBAPIError) as sin_contexto:
        connection.execute(
            text(
                """
                    INSERT INTO membership_event
                        (tenant_id, actor_user_id, tipo, detail)
                    VALUES (:tenant_id, :actor,
                            CAST('member_created' AS membership_event_tipo), '{}')
                    """
            ),
            {"tenant_id": tenant_id, "actor": actor},
        )
    assert _sqlstate(sin_contexto.value) == "42501"

    # Con contexto: se escribe (la app nunca lee la fila que acaba de crear).
    with _as_app(db_engine, tenant_id) as connection:
        connection.execute(
            text(
                """
                INSERT INTO membership_event (tenant_id, actor_user_id, tipo, detail)
                VALUES (:tenant_id, :actor,
                        CAST('member_created' AS membership_event_tipo), '{}')
                """
            ),
            {"tenant_id": tenant_id, "actor": actor},
        )
        connection.commit()

    with db_engine.connect() as connection:
        written = connection.execute(
            text("SELECT count(*) FROM membership_event WHERE tenant_id = :id"),
            {"id": tenant_id},
        ).scalar_one()
    assert written == 1


def test_update_y_delete_directos_fallan_incluso_para_el_superusuario(
    db_engine: Engine, seeder: Any
) -> None:
    tenant_id = seeder.tenant()
    actor = seeder.user()
    event_id = _insert_event(
        db_engine, tenant_id, actor_user_id=actor, target_user_id=actor
    )

    with db_engine.connect() as connection, pytest.raises(DBAPIError) as update_error:
        connection.execute(
            text("UPDATE membership_event SET detail = '{}' WHERE id = :id"),
            {"id": event_id},
        )
    assert _sqlstate(update_error.value) == "55000"

    with db_engine.connect() as connection, pytest.raises(DBAPIError) as delete_error:
        connection.execute(
            text("DELETE FROM membership_event WHERE id = :id"), {"id": event_id}
        )
    assert _sqlstate(delete_error.value) == "55000"

    # La fila sigue intacta: el trigger no dejó pasar nada.
    assert _detalle(db_engine, event_id)[0] == "member_created"


def test_el_delete_del_usuario_referenciado_deja_los_ids_en_null(
    db_engine: Engine, seeder: Any
) -> None:
    tenant_id = seeder.tenant()
    actor = seeder.user()
    target = seeder.user()
    event_id = _insert_event(
        db_engine, tenant_id, actor_user_id=actor, target_user_id=target
    )

    # ``ON DELETE SET NULL`` es un UPDATE interno: ``pg_trigger_depth() > 1`` lo deja pasar.
    with db_engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": target})

    tipo, actor_id, target_id = _detalle(db_engine, event_id)
    assert tipo == "member_created"
    assert actor_id == str(actor)
    assert target_id is None


def test_el_delete_del_tenant_borra_sus_eventos(db_engine: Engine, seeder: Any) -> None:
    tenant_id = seeder.tenant()
    event_id = _insert_event(
        db_engine, tenant_id, actor_user_id=None, target_user_id=None
    )

    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM tenant WHERE id = :id"), {"id": tenant_id})

    with db_engine.connect() as connection:
        remaining = connection.execute(
            text("SELECT count(*) FROM membership_event WHERE id = :id"), {"id": event_id}
        ).scalar_one()
    assert remaining == 0


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


def test_la_migracion_004_rbac_es_reversible(docker_services: dict[str, str]) -> None:
    with PostgresContainer("postgres:16-alpine") as pg:
        url = _normalize_postgres_url(pg.get_connection_url(driver=None))

        config = Config()
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", url)

        tipo = (
            "SELECT count(*) FROM pg_type WHERE typname = 'membership_event_tipo'"
        )
        tabla = (
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename = 'membership_event'"
        )
        trigger = (
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'membership_event_append_only' "
            "AND NOT tgisinternal"
        )
        funcion = (
            "SELECT count(*) FROM pg_proc WHERE proname = 'membership_event_forbid_mutation'"
        )
        politica = (
            "SELECT count(*) FROM pg_policies WHERE policyname = 'membership_event_tenant_insert'"
        )

        command.upgrade(config, "head")
        assert _count(url, tipo) == 1
        assert _count(url, tabla) == 1
        assert _count(url, trigger) == 1
        assert _count(url, funcion) == 1
        assert _count(url, politica) == 1

        # ``downgrade 003_auth`` debe dejar el esquema como estaba: sin tipo, tabla,
        # trigger, función ni política.
        command.downgrade(config, "003_auth")
        assert _count(url, tipo) == 0
        assert _count(url, tabla) == 0
        assert _count(url, trigger) == 0
        assert _count(url, funcion) == 0
        assert _count(url, politica) == 0

        command.upgrade(config, "head")
        assert _count(url, tipo) == 1
        assert _count(url, tabla) == 1
        assert _count(url, trigger) == 1
        assert _count(url, funcion) == 1
        assert _count(url, politica) == 1


def test_la_migracion_004_rbac_tiene_la_revision_correcta() -> None:
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)

    revision = script.get_revision("004_rbac")

    assert revision is not None
    assert revision.down_revision == "003_auth"


def test_el_tipo_no_admite_valores_fuera_del_catalogo(db_engine: Engine, seeder: Any) -> None:
    tenant_id = seeder.tenant()
    assert uuid4()  # el tenant se siembra antes del insert inválido

    with db_engine.connect() as connection, pytest.raises(DBAPIError) as excinfo:
        connection.execute(
            text(
                """
                    INSERT INTO membership_event (tenant_id, tipo, detail)
                    VALUES (:tenant_id,
                            CAST('rol_inventado' AS membership_event_tipo), '{}')
                    """
            ),
            {"tenant_id": tenant_id},
        )
    # 22P02 invalid_text_representation: el enum rechaza el valor.
    assert _sqlstate(excinfo.value) == "22P02"
