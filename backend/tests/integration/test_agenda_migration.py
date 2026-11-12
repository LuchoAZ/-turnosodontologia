"""Esquema de la agenda: `appointment`, enums, `EXCLUDE` y RLS (tasks 0.1/0.2).

Corre contra la base migrada del contenedor compartido y consulta el catálogo de
Postgres (no los modelos): si el DDL y el modelo se desincronizan, el test lo
delata. Las inserciones de solape corren con ``SET ROLE odontologia_app`` y el GUC
del tenant fijado: el superusuario del contenedor ignora RLS y el verde sería
falso.

**Desviación declarada de la task 0.1** — el `EXCLUDE` no puede expresarse como
``tstzrange(inicio - make_interval(mins => buffer_previo_min), ...)`` porque
``timestamptz - interval`` es ``STABLE`` en PostgreSQL 16 y el planner lo rechaza
dentro de un índice (*"functions in index expression must be marked IMMUTABLE"*).
La expresión equivalente e inmutable es
``tsrange((inicio AT TIME ZONE 'UTC') - make_interval(...), (fin AT TIME ZONE
'UTC') + make_interval(...))``: compara exactamente los mismos instantes y
conserva el rango semiabierto ``[inicio - buffer_previo, fin + buffer_posterior)``
que usan el pre-chequeo de aplicación y RN-AG-03. La reversibilidad vive en
``test_migration_reversibility.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.db.engine import APP_ROLE, create_db_engine
from app.db.tenant_context import set_tenant_context
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, ProgrammingError

APPOINTMENT_COLUMNS: dict[str, bool] = {
    "id": False,
    "tenant_id": False,
    "patient_id": True,
    "professional_id": False,
    "chair_id": False,
    "inicio": False,
    "fin": False,
    "duracion_min": False,
    "buffer_previo_min": False,
    "buffer_posterior_min": False,
    "estado": False,
    "tipo_practica": True,
    "motivo": True,
    "origen": False,
    "creado_por": True,
    "recordatorio_24h_enviado_at": True,
    "recordatorio_2h_enviado_at": True,
    "cancelado_motivo": True,
    "version": False,
    "created_at": False,
    "updated_at": False,
}

EXCLUSION_CONSTRAINTS = {
    "ex_appointment_professional_no_overlap": "professional_id",
    "ex_appointment_chair_no_overlap": "chair_id",
}

INSERT_SQL = text(
    """
    INSERT INTO appointment
        (id, tenant_id, patient_id, professional_id, chair_id, inicio, fin,
         duracion_min, buffer_previo_min, buffer_posterior_min, estado, origen)
    VALUES (:id, :tenant_id, :patient_id, :professional_id, :chair_id, :inicio, :fin,
            :duracion_min, :buffer_previo_min, :buffer_posterior_min,
            CAST(:estado AS appointment_estado), CAST(:origen AS appointment_origen))
    """
)


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


def _enum_values(engine: Engine, type_name: str) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    """
                    SELECT e.enumlabel
                    FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                    WHERE t.typname = :type_name
                    ORDER BY e.enumsortorder
                    """
                ),
                {"type_name": type_name},
            ).scalars()
        )


def _constraint_def(engine: Engine, name: str) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) AS def
                FROM pg_constraint
                WHERE conrelid = 'appointment'::regclass AND conname = :name
                """
            ),
            {"name": name},
        ).scalar_one_or_none()


def _index_def(engine: Engine, name: str) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": name},
        ).scalar_one_or_none()


def _app_engine(settings: Settings) -> Engine:
    return create_db_engine(settings)


def _insert(connection: Connection, **values: Any) -> None:
    payload = {
        "id": uuid4(),
        "patient_id": None,
        "estado": "pendiente",
        "origen": "recepcion",
        "duracion_min": 30,
        "buffer_previo_min": 0,
        "buffer_posterior_min": 0,
    }
    payload.update(values)
    connection.execute(INSERT_SQL, payload)


def _agenda(seeder: Any, *, prefix: str = "agenda") -> dict[str, UUID]:
    """Un tenant con un sillón, un profesional y un paciente sembrados."""
    tenant_id = seeder.tenant(slug=f"{prefix}-{uuid4().hex[:8]}", nombre=f"Clínica {prefix}")
    chair_id = seeder.chair(tenant_id, nombre="Sillón agenda")
    professional_id = seeder.professional(tenant_id)
    patient_id = seeder.patient(tenant_id, dni=None)
    return {
        "tenant_id": tenant_id,
        "chair_id": chair_id,
        "professional_id": professional_id,
        "patient_id": patient_id,
    }


# --- 0.1a: catálogo ---------------------------------------------------------


def test_la_tabla_appointment_existe_con_su_shape(db_engine: Engine) -> None:
    columns = _columns(db_engine, "appointment")
    assert set(columns) == set(APPOINTMENT_COLUMNS)
    for column, nullable in APPOINTMENT_COLUMNS.items():
        assert columns[column] is nullable, column


def test_los_enums_de_estado_y_origen_tienen_los_valores_de_la_kb(db_engine: Engine) -> None:
    assert _enum_values(db_engine, "appointment_estado") == [
        "pendiente",
        "confirmado",
        "en_curso",
        "atendido",
        "cancelado",
        "no_asistio",
        "reprogramado",
    ]
    assert _enum_values(db_engine, "appointment_origen") == [
        "recepcion",
        "portal",
        "whatsapp",
        "api",
        "importacion",
    ]


@pytest.mark.parametrize(
    ("constraint", "resource_column"), EXCLUSION_CONSTRAINTS.items()
)
def test_hay_un_exclude_gist_por_profesional_y_por_sillon(
    db_engine: Engine, constraint: str, resource_column: str
) -> None:
    definition = _constraint_def(db_engine, constraint)
    assert definition is not None, constraint
    assert "EXCLUDE USING gist" in definition
    assert resource_column in definition
    # Rango bloqueado: [inicio - buffer_previo, fin + buffer_posterior) en UTC.
    assert "tsrange(" in definition
    assert "AT TIME ZONE 'UTC'" in definition
    assert "make_interval(" in definition
    assert "buffer_previo_min" in definition
    assert "buffer_posterior_min" in definition
    assert "WITH &&" in definition
    # Los estados que liberan el recurso no bloquean.
    assert "cancelado" in definition
    assert "no_asistio" in definition


def test_fin_debe_ser_posterior_a_inicio(db_engine: Engine) -> None:
    definition = _constraint_def(db_engine, "ck_appointment_fin_posterior_a_inicio")
    assert definition is not None
    assert "fin > inicio" in definition


def test_los_indices_de_agenda_existen(db_engine: Engine) -> None:
    assert _installed_extension(db_engine, "btree_gist") == "btree_gist"
    for name, columns in {
        "ix_appointment_tenant_inicio": ["tenant_id", "inicio"],
        "ix_appointment_patient_inicio": ["patient_id", "inicio"],
    }.items():
        definition = _index_def(db_engine, name)
        assert definition is not None, name
        assert f"({', '.join(columns)})" in definition, definition


def _installed_extension(engine: Engine, name: str) -> str | None:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = :name"), {"name": name}
        ).scalar_one_or_none()
    return None if row is None else str(row)


def test_rls_habilitada_y_forzada_con_politica_por_tenant(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        flags: dict[str, Any] = dict(
            connection.execute(
                text(
                    """
                    SELECT c.relrowsecurity AS enabled, c.relforcerowsecurity AS forced
                    FROM pg_class c WHERE c.oid = to_regclass('appointment')
                    """
                )
            ).mappings().one()
        )
        policies = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT policyname, qual, with_check
                    FROM pg_policies WHERE schemaname = 'public' AND tablename = 'appointment'
                    """
                )
            ).mappings()
        ]

    assert flags["enabled"] is True
    assert flags["forced"] is True
    assert len(policies) == 1, policies
    policy = policies[0]
    assert policy["policyname"] == "appointment_tenant_isolation"
    for clause in (policy["qual"], policy["with_check"]):
        assert "current_setting('app.current_tenant'" in clause
        assert "tenant_id" in clause


def test_el_rol_de_app_tiene_permisos_sobre_appointment(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        grants = set(
            connection.execute(
                text(
                    """
                    SELECT privilege_type
                    FROM information_schema.role_table_grants
                    WHERE grantee = 'odontologia_app' AND table_name = 'appointment'
                    """
                )
            ).scalars()
        )
    assert {"SELECT", "INSERT", "UPDATE", "DELETE"} <= grants


# --- 0.1b: la garantía dura, con el rol de la app ---------------------------


def test_odontologia_app_no_puede_insertar_un_solape_del_mismo_profesional(
    auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="overlap-prof")
    other_chair = seeder.chair(data["tenant_id"], nombre="Sillón 2")
    engine = _app_engine(auth_settings)
    try:
        with engine.begin() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE
            set_tenant_context(connection, data["tenant_id"])
            _insert(
                connection,
                tenant_id=data["tenant_id"],
                chair_id=data["chair_id"],
                professional_id=data["professional_id"],
                inicio="2026-11-16T09:00:00+00:00",
                fin="2026-11-16T09:30:00+00:00",
            )
            with pytest.raises(IntegrityError) as failure:
                _insert(
                    connection,
                    tenant_id=data["tenant_id"],
                    chair_id=other_chair,
                    professional_id=data["professional_id"],
                    inicio="2026-11-16T09:15:00+00:00",
                    fin="2026-11-16T09:45:00+00:00",
                )
    finally:
        engine.dispose()

    assert failure.value.orig.sqlstate == "23P01"  # type: ignore[attr-defined]
    assert (
        failure.value.orig.diag.constraint_name  # type: ignore[attr-defined]
        == "ex_appointment_professional_no_overlap"
    )


def test_odontologia_app_puede_insertar_un_turno_contiguo(
    auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="contiguo")
    engine = _app_engine(auth_settings)
    try:
        with engine.begin() as connection:
            set_tenant_context(connection, data["tenant_id"])
            _insert(
                connection,
                tenant_id=data["tenant_id"],
                chair_id=data["chair_id"],
                professional_id=data["professional_id"],
                inicio="2026-11-16T09:00:00+00:00",
                fin="2026-11-16T09:30:00+00:00",
            )
            _insert(
                connection,
                tenant_id=data["tenant_id"],
                chair_id=data["chair_id"],
                professional_id=data["professional_id"],
                inicio="2026-11-16T09:30:00+00:00",
                fin="2026-11-16T10:00:00+00:00",
            )
    finally:
        engine.dispose()


def test_el_buffer_del_turno_existente_tambien_bloquea(
    auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="buffer")
    other_chair = seeder.chair(data["tenant_id"], nombre="Sillón 2")
    engine = _app_engine(auth_settings)
    try:
        with engine.begin() as connection:
            set_tenant_context(connection, data["tenant_id"])
            _insert(
                connection,
                tenant_id=data["tenant_id"],
                chair_id=data["chair_id"],
                professional_id=data["professional_id"],
                inicio="2026-11-16T09:00:00+00:00",
                fin="2026-11-16T09:30:00+00:00",
                buffer_posterior_min=15,
            )
            with pytest.raises(IntegrityError) as failure:
                _insert(
                    connection,
                    tenant_id=data["tenant_id"],
                    chair_id=other_chair,
                    professional_id=data["professional_id"],
                    inicio="2026-11-16T09:35:00+00:00",
                    fin="2026-11-16T10:05:00+00:00",
                )
    finally:
        engine.dispose()

    assert failure.value.orig.sqlstate == "23P01"  # type: ignore[attr-defined]


def test_un_turno_cancelado_o_no_asistio_no_bloquea(
    auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="cancelado")
    engine = _app_engine(auth_settings)
    try:
        with engine.begin() as connection:
            set_tenant_context(connection, data["tenant_id"])
            for estado in ("cancelado", "no_asistio"):
                _insert(
                    connection,
                    tenant_id=data["tenant_id"],
                    chair_id=data["chair_id"],
                    professional_id=data["professional_id"],
                    inicio=f"2026-11-16T{9 + int(estado == 'no_asistio')}:00:00+00:00",
                    fin=f"2026-11-16T{9 + int(estado == 'no_asistio')}:30:00+00:00",
                    estado=estado,
                )
            # El mismo horario, ahora activo, no choca con los liberados.
            _insert(
                connection,
                tenant_id=data["tenant_id"],
                chair_id=data["chair_id"],
                professional_id=data["professional_id"],
                inicio="2026-11-16T09:00:00+00:00",
                fin="2026-11-16T09:30:00+00:00",
            )
    finally:
        engine.dispose()


def test_sin_contexto_de_tenant_el_insert_es_fail_closed(
    auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="fail-closed")
    engine = _app_engine(auth_settings)
    try:
        with engine.begin() as connection, pytest.raises(ProgrammingError):
            # RLS fail-closed: sin GUC el ``WITH CHECK`` rechaza el INSERT.
            _insert(
                connection,
                tenant_id=data["tenant_id"],
                chair_id=data["chair_id"],
                professional_id=data["professional_id"],
                inicio="2026-11-16T09:00:00+00:00",
                fin="2026-11-16T09:30:00+00:00",
            )
    finally:
        engine.dispose()
