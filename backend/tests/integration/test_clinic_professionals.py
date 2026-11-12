"""``/api/v1/clinic/professionals`` (tasks 4.1-4.6, escenarios S4.1-S6.4).

Cubre matrícula única por tenant, visibilidad del catálogo ``specialty`` (sin
RLS), ``user_not_member`` y la baja por ``activo = false`` (no existe
``professional.delete`` en la matriz).
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

PROS_URL = "/api/v1/clinic/professionals"
PRO_KEYS = {
    "id",
    "user_id",
    "nombre",
    "apellido",
    "matricula",
    "especialidad",
    "duracion_default_min",
    "porcentaje_liquidacion",
    "color_agenda",
    "activo",
}


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
    return seeder.tenant(slug=f"clinic-pros-{uuid4().hex[:8]}", nombre="Clínica Profesionales")


def _session_as(
    client: TestClient, settings: Settings, seeder: Any, tenant_id: UUID, rol: str
) -> UUID:
    user_id = seeder.user(email=f"{rol}-{uuid4().hex[:8]}@example.test", nombre=rol)
    seeder.membership(tenant_id, user_id, rol)
    _authenticate(client, settings, seeder, tenant_id, user_id)
    return user_id


def _tenant_specialty(seeder: Any, tenant_id: UUID, nombre: str) -> UUID:
    specialty_id = uuid4()
    with seeder.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO specialty (id, tenant_id, nombre, duracion_default_min)
                VALUES (:id, :tenant_id, :nombre, 30)
                """
            ),
            {"id": specialty_id, "tenant_id": tenant_id, "nombre": nombre},
        )
    return specialty_id


def _payload(especialidad_id: UUID, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "nombre": "Paula",
        "apellido": "Pérez",
        "matricula": "MP-1234",
        "especialidad_id": str(especialidad_id),
        "duracion_default_min": 30,
        "porcentaje_liquidacion": 40,
        "color_agenda": "#2563EB",
    }
    body.update(overrides)
    return body


def test_la_lista_trae_matricula_especialidad_y_duracion(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    specialty_id = _tenant_specialty(seeder, tenant_id, "Ortodoncia C-05")
    seeder.professional(
        tenant_id,
        nombre="Paula",
        apellido="Pérez",
        matricula="MP-1",
        especialidad_id=specialty_id,
        duracion_default_min=45,
    )
    _session_as(client, auth_settings, seeder, tenant_id, "front_desk")

    response = client.get(PROS_URL)

    assert response.status_code == 200, response.text
    professionals = response.json()["professionals"]
    assert len(professionals) == 1
    professional = professionals[0]
    assert set(professional) == PRO_KEYS
    assert professional["matricula"] == "MP-1"
    assert professional["especialidad"] == {"id": str(specialty_id), "nombre": "Ortodoncia C-05"}
    assert professional["duracion_default_min"] == 45
    assert "tenant_id" not in response.text


def test_sin_professional_read_la_lista_responde_403(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "billing")

    response = client.get(PROS_URL)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"


def test_un_profesional_externo_aparece_con_user_id_nulo(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.professional(tenant_id, matricula="EXT-1")
    _session_as(client, auth_settings, seeder, tenant_id, "professional")

    professional = client.get(PROS_URL).json()["professionals"][0]

    assert professional["user_id"] is None
    assert professional["matricula"] == "EXT-1"


def test_alta_completa_resuelve_la_especialidad(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    specialty_id = seeder.specialty()
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(PROS_URL, json=_payload(specialty_id))

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == PRO_KEYS
    assert created["activo"] is True
    assert created["matricula"] == "MP-1234"
    assert created["especialidad"]["nombre"] == "Odontología general"
    assert float(created["porcentaje_liquidacion"]) == 40

    listed = client.get(PROS_URL).json()["professionals"]
    assert [item["id"] for item in listed] == [created["id"]]


def test_matricula_repetida_en_el_tenant_responde_409(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    specialty_id = seeder.specialty()
    seeder.professional(tenant_id, matricula="MP-1234")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(PROS_URL, json=_payload(specialty_id))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "professional_matricula_taken"
    assert len(client.get(PROS_URL).json()["professionals"]) == 1


@pytest.mark.parametrize(
    "overrides",
    [{"duracion_default_min": 0}, {"porcentaje_liquidacion": 120}, {"matricula": ""}],
)
def test_rangos_invalidos_no_escriben_fila(
    client: TestClient, auth_settings: Settings, seeder: Any, overrides: dict[str, Any]
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(PROS_URL, json=_payload(seeder.specialty(), **overrides))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    assert client.get(PROS_URL).json()["professionals"] == []


def test_especialidad_inexistente_o_de_otro_tenant_es_indistinguible(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    foreign_specialty = _tenant_specialty(seeder, tenant_b, "Solo de B")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    foreign = client.post(PROS_URL, json=_payload(foreign_specialty))
    missing = client.post(PROS_URL, json=_payload(uuid4()))

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["code"] == "specialty_not_found"
    assert client.get(PROS_URL).json()["professionals"] == []


def test_un_user_id_sin_membership_se_rechaza(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    outsider = seeder.user(email=f"outsider-{uuid4().hex[:8]}@example.test")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(PROS_URL, json=_payload(seeder.specialty(), user_id=str(outsider)))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "user_not_member"
    assert client.get(PROS_URL).json()["professionals"] == []


def test_un_user_id_con_membership_inactiva_tambien_se_rechaza(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    inactive = seeder.user(email=f"inactive-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_id, inactive, "professional", activo=False)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(PROS_URL, json=_payload(seeder.specialty(), user_id=str(inactive)))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "user_not_member"


def test_la_misma_matricula_en_otro_tenant_no_colisiona(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    seeder.professional(tenant_a, matricula="MP-1234")
    _session_as(client, auth_settings, seeder, tenant_b, "owner")

    response = client.post(PROS_URL, json=_payload(seeder.specialty()))

    assert response.status_code == 201, response.text
    assert len(client.get(PROS_URL).json()["professionals"]) == 1


def test_desactivar_conserva_la_fila_y_sus_reglas(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    professional_id = seeder.professional(tenant_id, matricula="MP-77")
    seeder.availability_rule(tenant_id, professional_id=professional_id, dia_semana=1)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.patch(f"{PROS_URL}/{professional_id}", json={"activo": False})

    assert response.status_code == 200, response.text
    assert response.json()["activo"] is False
    listed = client.get(PROS_URL).json()["professionals"]
    assert len(listed) == 1
    assert listed[0]["matricula"] == "MP-77"
    assert listed[0]["especialidad"]["nombre"]
    with seeder.engine.connect() as connection:
        rules = connection.execute(
            text(
                "SELECT count(*) FROM availability_rule WHERE professional_id = :id"
            ),
            {"id": professional_id},
        ).scalar_one()
    assert rules == 1


def test_sin_professional_update_no_hay_modificacion(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    professional_id = seeder.professional(tenant_id, matricula="MP-88")
    _session_as(client, auth_settings, seeder, tenant_id, "front_desk")

    response = client.patch(f"{PROS_URL}/{professional_id}", json={"nombre": "Otro"})

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    assert client.get(PROS_URL).json()["professionals"][0]["nombre"] == "Paula"


def test_el_profesional_de_otro_tenant_es_indistinguible(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    foreign_id = seeder.professional(tenant_b, matricula="MP-999")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    foreign = client.patch(f"{PROS_URL}/{foreign_id}", json={"nombre": "Robado"})
    missing = client.patch(f"{PROS_URL}/{uuid4()}", json={"nombre": "Robado"})

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["code"] == "professional_not_found"
