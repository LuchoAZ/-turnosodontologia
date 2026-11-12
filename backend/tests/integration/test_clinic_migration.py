"""Esquema de C-05: tablas, enums, índices, CHECK y RLS (tasks 1.1/1.3/1.4).

Corre contra la base migrada del contenedor compartido y consulta el catálogo de
Postgres (no los modelos): si el DDL y el modelo se desincronizan, el test lo
delata. La reversibilidad vive en ``test_migration_reversibility.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

CLINIC_TABLES = ("chair", "professional", "availability_rule")

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "chair": {
        "id",
        "tenant_id",
        "nombre",
        "tipo",
        "activo",
        "ubicacion",
        "equipamiento",
        "created_at",
        "updated_at",
    },
    "professional": {
        "id",
        "tenant_id",
        "user_id",
        "nombre",
        "apellido",
        "matricula",
        "especialidad_id",
        "porcentaje_liquidacion",
        "duracion_default_min",
        "color_agenda",
        "activo",
        "created_at",
        "updated_at",
    },
    "availability_rule": {
        "id",
        "tenant_id",
        "professional_id",
        "chair_id",
        "dia_semana",
        "hora_inicio",
        "hora_fin",
        "slot_min",
        "buffer_previo_min",
        "buffer_posterior_min",
        "fecha_desde",
        "fecha_hasta",
        "tipo_practica",
        "created_at",
        "updated_at",
    },
}


def _columns(engine: Engine, table: str) -> dict[str, bool]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table
                """
            ),
            {"table": table},
        ).mappings()
        return {row["column_name"]: row["is_nullable"] == "YES" for row in rows}


@pytest.mark.parametrize("table", CLINIC_TABLES)
def test_las_tablas_de_clinica_existen_con_sus_columnas(db_engine: Engine, table: str) -> None:
    columns = _columns(db_engine, table)
    assert set(columns) == EXPECTED_COLUMNS[table]
    assert columns["tenant_id"] is False  # NOT NULL: RLS fail-closed
    assert columns["id"] is False


def test_el_enum_chair_tipo_tiene_los_cinco_valores(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        values = list(
            connection.execute(
                text(
                    """
                    SELECT e.enumlabel
                    FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                    WHERE t.typname = 'chair_tipo'
                    ORDER BY e.enumsortorder
                    """
                )
            ).scalars()
        )
    assert values == ["consultorio", "rx", "cirugia", "higiene", "otro"]


def test_los_indices_unicos_por_tenant_existen(db_engine: Engine) -> None:
    expected = {
        "uq_chair_tenant_nombre": ("chair", ["tenant_id", "nombre"]),
        "uq_professional_tenant_matricula": ("professional", ["tenant_id", "matricula"]),
        "uq_availability_rule_scope": (
            "availability_rule",
            ["tenant_id", "professional_id", "chair_id", "dia_semana", "fecha_desde"],
        ),
    }
    with db_engine.connect() as connection:
        for index_name, (table, columns) in expected.items():
            rows = connection.execute(
                text(
                    """
                    SELECT a.attname
                    FROM pg_index i
                    JOIN pg_class c ON c.oid = i.indexrelid
                    JOIN pg_class t ON t.oid = i.indrelid
                    JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
                    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
                    WHERE c.relname = :index_name AND t.relname = :table
                    ORDER BY k.ord
                    """
                ),
                {"index_name": index_name, "table": table},
            ).scalars()
            assert list(rows) == columns, index_name


def test_los_check_de_rango_viven_en_la_base(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        constraints = {
            row["conname"]: row["def"]
            for row in connection.execute(
                text(
                    """
                    SELECT conname, pg_get_constraintdef(oid) AS def
                    FROM pg_constraint
                    WHERE conrelid IN (
                        'chair'::regclass,
                        'professional'::regclass,
                        'availability_rule'::regclass
                    ) AND contype = 'c'
                    """
                )
            ).mappings()
        }
    joined = " ".join(constraints.values())
    assert "duracion_default_min" in joined
    assert "porcentaje_liquidacion" in joined
    assert "hora_fin > hora_inicio" in joined
    assert "slot_min > 0" in joined
    assert "dia_semana" in joined


def test_el_solape_de_reglas_es_nulls_not_distinct(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        definition = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_availability_rule_scope'")
        ).scalar_one()
    assert "UNIQUE" in definition
    assert "NULLS NOT DISTINCT" in definition


@pytest.mark.parametrize("table", CLINIC_TABLES)
def test_rls_habilitada_y_forzada_con_politica_por_tenant(db_engine: Engine, table: str) -> None:
    with db_engine.connect() as connection:
        flags: dict[str, Any] = dict(
            connection.execute(
                text(
                    """
                    SELECT c.relrowsecurity AS enabled, c.relforcerowsecurity AS forced
                    FROM pg_class c WHERE c.oid = to_regclass(:table)
                    """
                ),
                {"table": table},
            ).mappings().one()
        )
        policies = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT policyname, qual, with_check
                    FROM pg_policies WHERE schemaname = 'public' AND tablename = :table
                    """
                ),
                {"table": table},
            ).mappings()
        ]

    assert flags["enabled"] is True
    assert flags["forced"] is True
    assert len(policies) == 1, policies
    policy = policies[0]
    assert policy["policyname"] == f"{table}_tenant_isolation"
    for clause in (policy["qual"], policy["with_check"]):
        assert "current_setting('app.current_tenant'" in clause
        assert "tenant_id" in clause


def test_el_rol_de_app_tiene_permisos_sobre_las_tablas_nuevas(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        grants = connection.execute(
            text(
                """
                SELECT table_name, privilege_type
                FROM information_schema.role_table_grants
                WHERE grantee = 'odontologia_app'
                  AND table_name IN ('chair', 'professional', 'availability_rule')
                """
            )
        ).all()
    by_table: dict[str, set[str]] = {}
    for table_name, privilege in grants:
        by_table.setdefault(table_name, set()).add(privilege)
    for table in CLINIC_TABLES:
        assert {"SELECT", "INSERT", "UPDATE", "DELETE"} <= by_table.get(table, set())
