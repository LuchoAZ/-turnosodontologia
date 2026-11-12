"""Esquema de C-06: `patient`, `patient_counter`, enum, índices y RLS (tasks 2.1/2.3).

Corre contra la base migrada del contenedor compartido y consulta el catálogo de
Postgres (no los modelos): si el DDL y el modelo se desincronizan, el test lo
delata. La reversibilidad vive en ``test_migration_reversibility.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

PATIENT_TABLES = ("patient", "patient_counter")

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "patient": {
        "id",
        "tenant_id",
        "user_id",
        "dni",
        "nombre",
        "apellido",
        "apellido_norm",
        "nombre_norm",
        "fecha_nacimiento",
        "sexo",
        "telefono",
        "telefono_norm",
        "email",
        "domicilio",
        "obra_social_id",
        "numero_historia_clinica",
        "alergias",
        "alerta_clinica",
        "activo",
        "deleted_at",
        "created_at",
        "updated_at",
    },
    "patient_counter": {"tenant_id", "ultimo_numero", "updated_at"},
}

# Columnas que existen en la tabla pero NO se exponen por la API (RN-CMP-04, D3).
CLINICAL_COLUMNS = ("alergias", "alerta_clinica")


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


@pytest.mark.parametrize("table", PATIENT_TABLES)
def test_las_tablas_de_pacientes_existen_con_sus_columnas(db_engine: Engine, table: str) -> None:
    columns = _columns(db_engine, table)
    assert set(columns) == EXPECTED_COLUMNS[table]
    if table == "patient":
        # Las columnas clínicas se persisten aunque C-06 no las exponga (PQ-17).
        assert set(CLINICAL_COLUMNS) <= set(columns)


def test_patient_tiene_las_columnas_criticas_en_el_shape_esperado(db_engine: Engine) -> None:
    columns = _columns(db_engine, "patient")
    # RLS fail-closed y HCE obligatoria.
    assert columns["tenant_id"] is False
    assert columns["numero_historia_clinica"] is False
    # Normalizadas obligatorias: alimentan dedupe y búsqueda.
    for column in ("apellido_norm", "nombre_norm", "telefono_norm", "telefono", "nombre"):
        assert columns[column] is False, column
    # Opcionales del negocio.
    for column in (
        "dni",
        "fecha_nacimiento",
        "sexo",
        "email",
        "domicilio",
        "obra_social_id",
        "deleted_at",
        "alergias",
    ):
        assert columns[column] is True, column
    # Columnas clínicas persistidas pero sin exposición: siguen existiendo.
    assert columns["activo"] is False
    assert columns["alerta_clinica"] is False  # NOT NULL DEFAULT false


def test_patient_counter_arranca_en_cero(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        column_default = connection.execute(
            text(
                """
                SELECT column_default, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'patient_counter'
                  AND column_name = 'ultimo_numero'
                """
            )
        ).mappings().one()
    assert column_default["is_nullable"] == "NO"
    assert "0" in column_default["column_default"]


def test_el_enum_sexo_paciente_tiene_los_cuatro_valores(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        values = list(
            connection.execute(
                text(
                    """
                    SELECT e.enumlabel
                    FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                    WHERE t.typname = 'sexo_paciente'
                    ORDER BY e.enumsortorder
                    """
                )
            ).scalars()
        )
    assert values == ["femenino", "masculino", "otro", "no_declara"]


def test_la_extension_pg_trgm_esta_instalada(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        installed = connection.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'")
        ).scalar_one()
    assert installed == 1


def test_hce_es_unica_por_tenant(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        definition = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) AS def
                FROM pg_constraint
                WHERE conrelid = 'patient'::regclass
                  AND conname = 'uq_patient_tenant_numero_historia_clinica'
                """
            )
        ).scalar_one_or_none()
    assert definition is not None
    assert "UNIQUE (tenant_id, numero_historia_clinica)" in definition


def test_el_dni_tiene_un_indice_unico_parcial(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        definition = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_patient_dni'")
        ).scalar_one_or_none()
    assert definition is not None
    assert "UNIQUE" in definition
    assert "(tenant_id, dni)" in definition
    assert "WHERE (dni IS NOT NULL)" in definition


def test_los_indices_de_busqueda_existen(db_engine: Engine) -> None:
    expected = {
        "ix_patient_nombre": ["tenant_id", "apellido_norm", "nombre_norm"],
        "ix_patient_telefono": ["tenant_id", "telefono_norm"],
    }
    with db_engine.connect() as connection:
        for index_name, columns in expected.items():
            rows = connection.execute(
                text(
                    """
                    SELECT a.attname
                    FROM pg_index i
                    JOIN pg_class c ON c.oid = i.indexrelid
                    JOIN pg_class t ON t.oid = i.indrelid
                    JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
                    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
                    WHERE c.relname = :index_name AND t.relname = 'patient'
                    ORDER BY k.ord
                    """
                ),
                {"index_name": index_name},
            ).scalars()
            assert list(rows) == columns, index_name

        partial = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_patient_activos'")
        ).scalar_one_or_none()
    assert partial is not None
    assert "(tenant_id)" in partial
    assert "WHERE (deleted_at IS NULL)" in partial


def test_la_gin_trigram_acelera_nombre_y_apellido(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        indexes: dict[str, Any] = {}
        rows = connection.execute(
            text(
                """
                SELECT indexname, indexdef FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'patient'
                """
            )
        ).mappings()
        for row in rows:
            indexes[row["indexname"]] = row["indexdef"]
    trigram = [
        definition
        for definition in indexes.values()
        if "gin" in definition.lower()
        and "gin_trgm_ops" in definition
        and "apellido_norm" in definition
        and "nombre_norm" in definition
    ]
    assert len(trigram) == 1, indexes


@pytest.mark.parametrize("table", PATIENT_TABLES)
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
                  AND table_name IN ('patient', 'patient_counter')
                """
            )
        ).all()
    by_table: dict[str, set[str]] = {}
    for table_name, privilege in grants:
        by_table.setdefault(table_name, set()).add(privilege)
    assert {"SELECT", "INSERT", "UPDATE", "DELETE"} <= by_table.get("patient", set())
    assert {"SELECT", "INSERT", "UPDATE"} <= by_table.get("patient_counter", set())
