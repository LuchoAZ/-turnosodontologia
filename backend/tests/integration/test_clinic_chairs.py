"""``/api/v1/clinic/chairs`` (tasks 3.1-3.5, escenarios S1.1-S3.5).

El HTTP corre como ``odontologia_app`` con el GUC del tenant fijado por
``require_auth``: la lista sale filtrada por RLS y el endpoint nunca recibe el
``tenant_id``. Las sesiones se emiten con ``create_access_token`` (patrón de
``test_team_members_read``), porque lo que se prueba es autorización, no MFA.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from fastapi.testclient import TestClient
from sqlalchemy import text

CHAIRS_URL = "/api/v1/clinic/chairs"
CHAIR_KEYS = {"id", "nombre", "tipo", "ubicacion", "equipamiento", "activo"}


def _authenticate(
    client: TestClient,
    settings: Settings,
    seeder: Any,
    tenant_id: UUID,
    user_id: UUID,
) -> None:
    seeded = seeder.session(tenant_id, user_id)
    client.cookies.clear()
    client.cookies.set(
        ACCESS_COOKIE,
        create_access_token(
            settings,
            user_id=user_id,
            session_id=seeded.session_id,
            tenant_id=tenant_id,
            mfa=True,
            now=datetime.now(UTC),
        ),
        path="/",
    )


def _tenant(seeder: Any) -> UUID:
    return seeder.tenant(slug=f"clinic-chairs-{uuid4().hex[:8]}", nombre="Clínica Sillones")


def _member(seeder: Any, tenant_id: UUID, rol: str) -> UUID:
    user_id = seeder.user(
        email=f"{rol}-{uuid4().hex[:8]}@example.test", nombre=rol, apellido="Prueba"
    )
    seeder.membership(tenant_id, user_id, rol)
    return user_id


def _session_as(
    client: TestClient, settings: Settings, seeder: Any, tenant_id: UUID, rol: str
) -> UUID:
    user_id = _member(seeder, tenant_id, rol)
    _authenticate(client, settings, seeder, tenant_id, user_id)
    return user_id


def test_el_owner_ve_activos_e_inactivos_sin_tenant_id(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.chair(tenant_id, "Sillón 1", "consultorio")
    seeder.chair(tenant_id, "Sillón RX", "rx")
    seeder.chair(tenant_id, "Sillón Viejo", "otro", activo=False)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    first = client.get(CHAIRS_URL)
    second = client.get(CHAIRS_URL)

    assert first.status_code == 200, first.text
    body = first.json()
    assert set(body) == {"chairs"}
    chairs = body["chairs"]
    assert len(chairs) == 3
    assert {chair["nombre"] for chair in chairs} == {"Sillón 1", "Sillón RX", "Sillón Viejo"}
    inactive = next(chair for chair in chairs if chair["nombre"] == "Sillón Viejo")
    assert inactive["activo"] is False
    for chair in chairs:
        assert set(chair) == CHAIR_KEYS
        assert "tenant_id" not in chair
    # Orden estable: por tipo (orden del enum) y luego por nombre.
    assert [chair["id"] for chair in chairs] == [chair["id"] for chair in second.json()["chairs"]]
    assert [chair["tipo"] for chair in chairs] == ["consultorio", "rx", "otro"]


def test_sin_chair_read_la_lista_responde_403(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.chair(tenant_id, "Sillón Secreto", "consultorio")
    _session_as(client, auth_settings, seeder, tenant_id, "billing")

    response = client.get(CHAIRS_URL)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    assert "Sillón Secreto" not in response.text


def test_un_tenant_sin_sillones_devuelve_lista_vacia(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(CHAIRS_URL)

    assert response.status_code == 200, response.text
    assert response.json() == {"chairs": []}


def test_alta_completa_persiste_el_equipamiento(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(
        CHAIRS_URL,
        json={
            "nombre": "Sillón RX",
            "tipo": "rx",
            "ubicacion": "Planta alta",
            "equipamiento": {"intraoral_camera": True},
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["activo"] is True
    assert created["equipamiento"] == {"intraoral_camera": True}
    assert set(created) == CHAIR_KEYS

    listed = client.get(CHAIRS_URL).json()["chairs"]
    assert listed == [created]


def test_nombre_repetido_en_el_tenant_responde_409(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.chair(tenant_id, "Sillón 1", "consultorio")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(CHAIRS_URL, json={"nombre": "Sillón 1", "tipo": "rx"})

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "chair_name_taken"
    assert len(client.get(CHAIRS_URL).json()["chairs"]) == 1


def test_tipo_fuera_del_catalogo_responde_422_sin_ecos(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(CHAIRS_URL, json={"nombre": "Sillón X", "tipo": "resonador"})

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    assert "resonador" not in response.text
    assert "detail" not in response.json()


def test_dos_sillones_de_rx_conviven(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.chair(tenant_id, "RX 1", "rx")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(CHAIRS_URL, json={"nombre": "RX 2", "tipo": "rx"})

    assert response.status_code == 201, response.text
    assert response.json()["tipo"] == "rx"


def test_el_mismo_nombre_en_otro_tenant_no_colisiona(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    seeder.chair(tenant_a, "Sillón 1", "consultorio")
    _session_as(client, auth_settings, seeder, tenant_b, "owner")

    response = client.post(CHAIRS_URL, json={"nombre": "Sillón 1", "tipo": "consultorio"})

    assert response.status_code == 201, response.text
    assert len(client.get(CHAIRS_URL).json()["chairs"]) == 1


def test_patch_actualiza_los_atributos_editables(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    chair_id = seeder.chair(tenant_id, "Sillón 1", "consultorio")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.patch(
        f"{CHAIRS_URL}/{chair_id}",
        json={"ubicacion": "Planta baja", "equipamiento": {"rx": False, "luz": True}},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == str(chair_id)
    assert updated["ubicacion"] == "Planta baja"
    assert updated["equipamiento"] == {"rx": False, "luz": True}


def test_la_baja_es_logica_y_conserva_la_fila(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    chair_id = seeder.chair(tenant_id, "Sillón 1", "consultorio")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.delete(f"{CHAIRS_URL}/{chair_id}")

    assert response.status_code == 204, response.text
    chairs = client.get(CHAIRS_URL).json()["chairs"]
    assert [chair["id"] for chair in chairs] == [str(chair_id)]
    assert chairs[0]["activo"] is False


def test_repetir_la_baja_es_idempotente(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    chair_id = seeder.chair(tenant_id, "Sillón 1", "consultorio")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    assert client.delete(f"{CHAIRS_URL}/{chair_id}").status_code == 204
    second = client.delete(f"{CHAIRS_URL}/{chair_id}")

    assert second.status_code == 204, second.text
    assert client.get(CHAIRS_URL).json()["chairs"][0]["activo"] is False


def test_sin_chair_delete_no_hay_baja(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    chair_id = seeder.chair(tenant_id, "Sillón 1", "consultorio")
    _session_as(client, auth_settings, seeder, tenant_id, "clinical_admin")

    response = client.delete(f"{CHAIRS_URL}/{chair_id}")

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    assert client.get(CHAIRS_URL).json()["chairs"][0]["activo"] is True


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_el_sillon_de_otro_tenant_es_indistinguible_de_uno_inexistente(
    client: TestClient, auth_settings: Settings, seeder: Any, method: str
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    foreign_id = seeder.chair(tenant_b, "Ajeno", "consultorio")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")
    payload = {"ubicacion": "robado"} if method == "patch" else None

    foreign = getattr(client, method)(
        f"{CHAIRS_URL}/{foreign_id}", **({"json": payload} if payload else {})
    )
    random = getattr(client, method)(
        f"{CHAIRS_URL}/{uuid4()}", **({"json": payload} if payload else {})
    )

    assert foreign.status_code == random.status_code == 404
    assert foreign.json() == random.json()
    assert foreign.json()["code"] == "chair_not_found"
    with seeder.engine.connect() as connection:
        row = connection.execute(
            text("SELECT ubicacion, activo FROM chair WHERE id = :id"), {"id": foreign_id}
        ).one()
    assert row.activo is True
    assert row.ubicacion is None
