"""Gate de aislamiento cross-tenant de la agenda (task 6.1, RN-TEN-02).

**Bloqueante de merge**: si algo de acá se pone rojo, el change no cuenta. Cubre
tres niveles:

* **HTTP + RLS** — con sesión del tenant A, referenciar un ``professional``,
  ``chair`` o ``patient`` del tenant B responde ``404`` (nunca ``403`` ni ``200``) y
  no crea nada en ninguno de los dos.
* **``tenant_id`` del cliente** — un ``tenant_id`` de B en body, query y header se
  ignora: con recursos de A el turno nace en A; con recursos de B responde ``404``.
* **SQL como ``odontologia_app``** (``SET ROLE``, RLS activa) — cada tenant ve
  exactamente sus turnos y los de B no generan conflicto para A.

La prueba de mutación (``DISABLE ROW LEVEL SECURITY`` + quitar el filtro de
``tenant_id`` del servicio → este archivo tiene que fallar) está documentada en
``docs/skills-mcp/evidencias/`` junto con la corrida que la demuestra.
"""

from __future__ import annotations

from typing import Any

import pytest
from _agenda import APPOINTMENTS_URL, agenda, authenticate, payload, rows
from app.config import Settings
from app.db.engine import create_db_engine
from app.db.tenant_context import set_tenant_context
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _dos_tenants(seeder: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    a = agenda(seeder, prefix="tenant-a")
    b = agenda(seeder, prefix="tenant-b")
    return a, b


@pytest.mark.parametrize("campo", ["professional_id", "chair_id", "patient_id"])
def test_6_1_un_recurso_de_otro_tenant_es_404_y_no_crea_nada(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine, campo: str
) -> None:
    a, b = _dos_tenants(seeder)
    authenticate(client, auth_settings, seeder, a["tenant_id"], a["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(a, **{campo: str(b[campo])}))

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "recurso_no_encontrado"
    assert rows(db_engine, a["tenant_id"]) == []
    assert rows(db_engine, b["tenant_id"]) == []


def test_6_1_un_tenant_id_ajeno_con_recursos_ajenos_es_404_y_no_escribe_en_b(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    a, b = _dos_tenants(seeder)
    authenticate(client, auth_settings, seeder, a["tenant_id"], a["user_id"])

    response = client.post(
        APPOINTMENTS_URL,
        params={"tenant_id": str(b["tenant_id"])},
        headers={"X-Tenant-Id": str(b["tenant_id"])},
        json=payload(b, tenant_id=str(b["tenant_id"])),
    )

    assert response.status_code == 404, response.text
    assert rows(db_engine, b["tenant_id"]) == []


def test_6_1_un_tenant_id_ajeno_con_recursos_propios_nace_en_el_tenant_de_la_sesion(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    a, b = _dos_tenants(seeder)
    authenticate(client, auth_settings, seeder, a["tenant_id"], a["user_id"])

    response = client.post(
        APPOINTMENTS_URL,
        params={"tenant_id": str(b["tenant_id"])},
        headers={"X-Tenant-Id": str(b["tenant_id"])},
        json=payload(a, tenant_id=str(b["tenant_id"])),
    )

    assert response.status_code == 201, response.text
    assert len(rows(db_engine, a["tenant_id"])) == 1
    assert rows(db_engine, b["tenant_id"]) == []


def test_6_1_turnos_homologos_de_dos_tenants_no_generan_conflicto_entre_si(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    a, b = _dos_tenants(seeder)
    # Mismos instantes en ambos tenants: los recursos son homólogos, no compartidos.
    authenticate(client, auth_settings, seeder, a["tenant_id"], a["user_id"])
    primero = client.post(APPOINTMENTS_URL, json=payload(a))
    assert primero.status_code == 201, primero.text

    authenticate(client, auth_settings, seeder, b["tenant_id"], b["user_id"])
    segundo = client.post(APPOINTMENTS_URL, json=payload(b))

    assert segundo.status_code == 201, segundo.text
    assert len(rows(db_engine, a["tenant_id"])) == 1
    assert len(rows(db_engine, b["tenant_id"])) == 1


def test_6_1_el_rol_de_app_solo_ve_los_turnos_de_su_tenant(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    a, b = _dos_tenants(seeder)
    authenticate(client, auth_settings, seeder, a["tenant_id"], a["user_id"])
    assert client.post(APPOINTMENTS_URL, json=payload(a)).status_code == 201
    authenticate(client, auth_settings, seeder, b["tenant_id"], b["user_id"])
    assert client.post(APPOINTMENTS_URL, json=payload(b)).status_code == 201

    engine = create_db_engine(auth_settings)
    try:
        vistos: dict[str, list[Any]] = {}
        for nombre, tenant_id in (("a", a["tenant_id"]), ("b", b["tenant_id"])):
            with engine.connect() as connection:
                set_tenant_context(connection, tenant_id)
                vistos[nombre] = list(
                    connection.execute(text("SELECT tenant_id FROM appointment")).scalars()
                )
                connection.rollback()
    finally:
        engine.dispose()

    assert vistos["a"] == [a["tenant_id"]]
    assert vistos["b"] == [b["tenant_id"]]


def test_6_1_el_gate_corre_con_el_rol_de_app_no_con_el_superusuario(
    client: TestClient, auth_settings: Settings
) -> None:
    """El superusuario del contenedor ignora RLS: el gate se corre como la app."""
    engine = create_db_engine(auth_settings)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == "odontologia_app"
            assert connection.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).scalar_one() is False
    finally:
        engine.dispose()
