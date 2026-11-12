"""Gate de aislamiento cross-tenant de pacientes (task 2.5, RN-TEN-02).

**Bloqueante de merge**: si algo de acá se pone rojo, C-06 no cuenta. Cubre el
nivel SQL con una conexión real como ``odontologia_app`` (``SET ROLE``): el rol de
la app no es superusuario, no hace ``BYPASSRLS`` y ve exactamente las filas de su
``app.current_tenant``. El nivel HTTP y la prueba de mutación
(``DISABLE ROW LEVEL SECURITY``) se completan en 4.8/4.9 con la API ya montada.

``patient_counter`` también es una tabla de negocio (tiene ``tenant_id``), así que
se prueba igual que ``patient``: cada clínica ve su contador y solo el suyo.
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
from sqlalchemy.exc import ProgrammingError

PATIENT_TABLES = ("patient", "patient_counter")


def _app_engine(settings: Settings) -> Engine:
    return create_db_engine(settings)


def _visible_patient_ids(connection: Connection, tenant_id: UUID | None = None) -> set[UUID]:
    if tenant_id is not None:
        set_tenant_context(connection, tenant_id)
    return set(connection.execute(text("SELECT id FROM patient")).scalars())


def _two_patients(seeder: Any) -> dict[str, Any]:
    """Dos clínicas con un paciente cada una (el contador también queda con fila)."""
    tenant_a = seeder.tenant(slug=f"rls-patients-a-{uuid4().hex[:8]}", nombre="Clínica A")
    tenant_b = seeder.tenant(slug=f"rls-patients-b-{uuid4().hex[:8]}", nombre="Clínica B")
    patient_a = seeder.patient(
        tenant_a, nombre="Ana", apellido="Aria", dni="30111222", telefono="11 5555-1111"
    )
    patient_b = seeder.patient(
        tenant_b, nombre="Bruno", apellido="Berra", dni="30999888", telefono="11 5555-2222"
    )
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "patient_a": patient_a,
        "patient_b": patient_b,
    }


# --- 2.5a: nivel SQL -------------------------------------------------------


def test_a_nunca_ve_los_pacientes_de_b(auth_settings: Settings, seeder: Any) -> None:
    data = _two_patients(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            visible = _visible_patient_ids(connection, data["tenant_a"])
            assert connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE

        assert visible == {data["patient_a"]}
        assert data["patient_b"] not in visible
    finally:
        engine.dispose()


def test_cada_tenant_ve_solo_su_contador(auth_settings: Settings, seeder: Any) -> None:
    data = _two_patients(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            set_tenant_context(connection, data["tenant_a"])
            contadores = list(
                connection.execute(text("SELECT tenant_id FROM patient_counter")).scalars()
            )
            ultimo = connection.execute(
                text("SELECT ultimo_numero FROM patient_counter")
            ).scalar_one_or_none()

        assert contadores == [data["tenant_a"]]
        assert ultimo == 1  # un paciente sembrado en A
    finally:
        engine.dispose()


def test_update_y_delete_con_id_de_b_afectan_cero_filas(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_patients(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            set_tenant_context(connection, data["tenant_a"])
            updated = connection.execute(
                text("UPDATE patient SET nombre = 'robado' WHERE id = :id"),
                {"id": data["patient_b"]},
            )
            deleted = connection.execute(
                text("DELETE FROM patient WHERE id = :id"), {"id": data["patient_b"]}
            )
            # RLS filtra en el USING: la fila no existe "para" el tenant A.
            assert updated.rowcount == 0
            assert deleted.rowcount == 0
            connection.rollback()
    finally:
        engine.dispose()

    with db_engine.connect() as connection:
        assert connection.execute(
            text("SELECT nombre FROM patient WHERE id = :id"), {"id": data["patient_b"]}
        ).scalar_one() == "Bruno"


@pytest.mark.parametrize("table", PATIENT_TABLES)
def test_sin_contexto_rls_es_fail_closed(
    auth_settings: Settings, seeder: Any, table: str
) -> None:
    data = _two_patients(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            # Sin ``app.current_tenant`` el predicado es NULL: cero filas, nunca todas.
            assert connection.execute(
                text(f"SELECT count(*) FROM {table}")
            ).scalar_one() == 0
            assert connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tenant_id"),
                {"tenant_id": data["tenant_a"]},
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_insert_de_paciente_sin_contexto_lo_frena_el_with_check(
    auth_settings: Settings, seeder: Any
) -> None:
    data = _two_patients(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            with pytest.raises(ProgrammingError) as error:
                connection.execute(
                    text(
                        """
                        INSERT INTO patient
                            (id, tenant_id, nombre, apellido, apellido_norm, nombre_norm,
                             telefono, telefono_norm, numero_historia_clinica)
                        VALUES (:id, :tenant_id, 'Sin', 'Contexto', 'contexto', 'sin',
                                '11', '11', '000999')
                        """
                    ),
                    {"id": uuid4(), "tenant_id": data["tenant_a"]},
                )
            assert "row-level security" in str(error.value)
            connection.rollback()
    finally:
        engine.dispose()


def test_con_contexto_de_a_no_se_puede_insertar_un_paciente_en_b(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_patients(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            set_tenant_context(connection, data["tenant_a"])
            with pytest.raises(ProgrammingError) as error:
                connection.execute(
                    text(
                        """
                        INSERT INTO patient
                            (id, tenant_id, nombre, apellido, apellido_norm, nombre_norm,
                             telefono, telefono_norm, numero_historia_clinica)
                        VALUES (:id, :tenant_id, 'Intruso', 'Frontera', 'frontera', 'intruso',
                                '11', '11', '000999')
                        """
                    ),
                    {"id": uuid4(), "tenant_id": data["tenant_b"]},
                )
            # Lo frena el WITH CHECK, no el USING.
            assert "row-level security" in str(error.value)
            connection.rollback()
    finally:
        engine.dispose()

    with db_engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM patient WHERE tenant_id = :tenant_id"),
            {"tenant_id": data["tenant_b"]},
        ).scalar_one() == 1


# --- 4.9: prueba de mutación ----------------------------------------------


@pytest.mark.parametrize("table", PATIENT_TABLES)
def test_mutar_rls_desactivada_rompe_el_gate_y_restaurarla_lo_deja_verde(
    auth_settings: Settings, seeder: Any, db_engine: Engine, table: str
) -> None:
    """Receta 4.9: ``DISABLE ROW LEVEL SECURITY`` -> fuga; restaurar -> verde.

    Mutación **de gate**, no de código: si el test de aislamiento siguiera verde
    con RLS desactivada, no estaría probando nada. Se muta el flag, nunca se hace
    ``DROP POLICY``; el ``finally`` restaura ``ENABLE`` + ``FORCE`` pase lo que pase.
    """
    data = _two_patients(seeder)
    engine = _app_engine(auth_settings)

    def visible_for_a() -> set[UUID]:
        with engine.connect() as connection:
            set_tenant_context(connection, data["tenant_a"])
            return set(connection.execute(text(f"SELECT tenant_id FROM {table}")).scalars())

    try:
        assert visible_for_a() == {data["tenant_a"]}
        print(f"[4.9] {table} RLS ON  -> la app ve solo el tenant A")

        with db_engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        try:
            leaked = visible_for_a()
            # Sin RLS la conexión de la app ve las filas de los dos tenants.
            assert leaked == {data["tenant_a"], data["tenant_b"]}
            print(f"[4.9] {table} RLS OFF -> la app ve {len(leaked)} tenants: el ajeno se filtra")
        finally:
            with db_engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))

        assert visible_for_a() == {data["tenant_a"]}
        print(f"[4.9] {table} RLS ON  -> gate VERDE otra vez: cross-tenant leak = 0")
    finally:
        with db_engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        engine.dispose()

