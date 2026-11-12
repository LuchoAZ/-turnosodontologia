"""``/api/v1/clinic/availability`` (tasks 5.1-5.7, escenarios S7.1-S7.8).

La validación de ventana corre **antes** de escribir: una regla inválida no deja
fila. El solape del mismo alcance y día es regla de negocio (409
``availability_overlap``); el duplicado exacto además lo bloquea el índice único
``NULLS NOT DISTINCT``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from fastapi.testclient import TestClient
from sqlalchemy import text

AVAILABILITY_URL = "/api/v1/clinic/availability"
RULE_KEYS = {
    "id",
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
    return seeder.tenant(slug=f"clinic-avail-{uuid4().hex[:8]}", nombre="Clínica Horarios")


def _session_as(
    client: TestClient, settings: Settings, seeder: Any, tenant_id: UUID, rol: str
) -> UUID:
    user_id = seeder.user(email=f"{rol}-{uuid4().hex[:8]}@example.test", nombre=rol)
    seeder.membership(tenant_id, user_id, rol)
    _authenticate(client, settings, seeder, tenant_id, user_id)
    return user_id


def _payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "dia_semana": 1,
        "hora_inicio": "09:00",
        "hora_fin": "12:00",
        "slot_min": 30,
        "buffer_previo_min": 10,
        "buffer_posterior_min": 15,
        "fecha_desde": "2026-11-16",
    }
    body.update(overrides)
    return body


def _count_rules(seeder: Any) -> int:
    with seeder.engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM availability_rule")).scalar_one())


def test_alta_completa_persiste_buffers_y_slot(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    professional_id = seeder.professional(tenant_id)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(
        AVAILABILITY_URL,
        json=_payload(professional_id=str(professional_id), tipo_practica="Endodoncia"),
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == RULE_KEYS
    assert created["professional_id"] == str(professional_id)
    assert created["slot_min"] == 30
    assert created["buffer_previo_min"] == 10
    assert created["buffer_posterior_min"] == 15
    assert created["dia_semana"] == 1
    assert created["hora_inicio"].startswith("09:00")
    assert created["hora_fin"].startswith("12:00")

    listed = client.get(AVAILABILITY_URL).json()["availability"]
    assert listed == [created]


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"hora_inicio": "12:00", "hora_fin": "12:00"}, "posterior"),
        ({"hora_inicio": "13:00", "hora_fin": "12:00"}, "posterior"),
        ({"hora_fin": "10:10"}, "múltiplo"),
        ({"slot_min": 0}, None),  # lo rechaza el DTO antes del servicio
        ({"buffer_posterior_min": -5}, None),  # idem
        ({"buffer_previo_min": 20, "buffer_posterior_min": 10}, "buffer"),
        ({"fecha_desde": "2026-12-01", "fecha_hasta": "2026-11-01"}, "fecha"),
    ],
)
def test_ventanas_invalidas_no_escriben_fila(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    changes: dict[str, Any],
    fragment: str | None,
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(AVAILABILITY_URL, json=_payload(**changes))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    if fragment is not None:
        assert fragment in response.json()["message"].lower()
    assert _count_rules(seeder) == 0


def test_dos_reglas_del_mismo_alcance_no_pueden_solaparse(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    professional_id = seeder.professional(tenant_id)
    seeder.availability_rule(
        tenant_id,
        professional_id=professional_id,
        dia_semana=1,
        hora_inicio=time(9, 0),
        hora_fin=time(12, 0),
    )
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(
        AVAILABILITY_URL,
        json=_payload(
            professional_id=str(professional_id),
            hora_inicio="11:00",
            hora_fin="14:00",
            fecha_hasta="2026-12-31",
        ),
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "availability_overlap"
    assert _count_rules(seeder) == 1
    with seeder.engine.connect() as connection:
        window = connection.execute(
            text("SELECT count(*) FROM availability_rule WHERE hora_inicio = '09:00'")
        ).scalar_one()
    assert window == 1


def test_reglas_que_solo_se_tocan_en_el_extremo_no_solapan(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    professional_id = seeder.professional(tenant_id)
    seeder.availability_rule(
        tenant_id,
        professional_id=professional_id,
        dia_semana=1,
        hora_inicio=time(9, 0),
        hora_fin=time(12, 0),
        fecha_desde=date(2026, 11, 16),
        fecha_hasta=date(2026, 11, 30),
    )
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(
        AVAILABILITY_URL,
        json=_payload(
            professional_id=str(professional_id),
            hora_inicio="12:00",
            hora_fin="15:00",
            fecha_desde="2026-11-30",
        ),
    )

    assert response.status_code == 201, response.text


def test_otro_dia_no_solapa(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    professional_id = seeder.professional(tenant_id)
    seeder.availability_rule(tenant_id, professional_id=professional_id, dia_semana=1)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(
        AVAILABILITY_URL, json=_payload(professional_id=str(professional_id), dia_semana=2)
    )

    assert response.status_code == 201, response.text


def test_regla_sin_professional_aplica_a_toda_la_clinica(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(AVAILABILITY_URL, json=_payload())

    assert response.status_code == 201, response.text
    assert response.json()["professional_id"] is None
    assert client.get(AVAILABILITY_URL).json()["availability"][0]["professional_id"] is None


def test_el_duplicado_exacto_del_alcance_nulo_tambien_se_rechaza(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.availability_rule(tenant_id, dia_semana=1)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.post(AVAILABILITY_URL, json=_payload())

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "availability_overlap"


def test_professional_o_chair_de_otro_tenant_no_crea_la_regla(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    foreign_professional = seeder.professional(tenant_b)
    foreign_chair = seeder.chair(tenant_b, "Ajeno")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    professional = client.post(
        AVAILABILITY_URL, json=_payload(professional_id=str(foreign_professional))
    )
    chair = client.post(
        AVAILABILITY_URL, json=_payload(chair_id=str(foreign_chair), dia_semana=3)
    )
    missing = client.post(AVAILABILITY_URL, json=_payload(professional_id=str(uuid4())))

    assert professional.status_code == 404, professional.text
    assert professional.json()["code"] == "professional_not_found"
    assert chair.status_code == 404, chair.text
    assert chair.json()["code"] == "chair_not_found"
    assert missing.status_code == 404
    assert missing.json()["code"] == "professional_not_found"
    assert _count_rules(seeder) == 0


def test_sin_professional_read_la_lista_responde_403(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "billing")

    response = client.get(AVAILABILITY_URL)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"


def test_patch_mueve_la_ventana_y_rechaza_solape(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    professional_id = seeder.professional(tenant_id)
    first = seeder.availability_rule(
        tenant_id, professional_id=professional_id, dia_semana=1,
        hora_inicio=time(9, 0), hora_fin=time(12, 0),
    )
    second = seeder.availability_rule(
        tenant_id, professional_id=professional_id, dia_semana=2,
        hora_inicio=time(9, 0), hora_fin=time(12, 0),
    )
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    ok = client.patch(f"{AVAILABILITY_URL}/{first}", json={"hora_fin": "11:00"})
    clash = client.patch(f"{AVAILABILITY_URL}/{first}", json={"dia_semana": 2})
    missing = client.patch(f"{AVAILABILITY_URL}/{uuid4()}", json={"dia_semana": 3})

    assert ok.status_code == 200, ok.text
    assert ok.json()["hora_fin"].startswith("11:00")
    assert clash.status_code == 409, clash.text
    assert clash.json()["code"] == "availability_overlap"
    assert missing.status_code == 404
    assert missing.json()["code"] == "availability_not_found"
    with seeder.engine.connect() as connection:
        untouched = connection.execute(
            text("SELECT dia_semana FROM availability_rule WHERE id = :id"), {"id": second}
        ).scalar_one()
    assert untouched == 2


def test_patch_con_ventana_invalida_no_toca_la_fila(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    rule_id = seeder.availability_rule(tenant_id)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.patch(f"{AVAILABILITY_URL}/{rule_id}", json={"slot_min": 7})

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    assert "múltiplo" in response.json()["message"].lower()
    with seeder.engine.connect() as connection:
        slot = connection.execute(
            text("SELECT slot_min FROM availability_rule WHERE id = :id"), {"id": rule_id}
        ).scalar_one()
    assert slot == 30
