"""``POST /api/v1/appointments`` (tasks 2.1-2.3; escenarios S1.1-S1.5, S4.3, S3.4).

El HTTP corre como ``odontologia_app`` con el GUC del tenant fijado por
``require_auth``: el ``tenant_id`` sale de la sesión y RLS lo vuelve a exigir. Las
sesiones se emiten con ``create_access_token`` (mismo patrón que
``test_patients_http.py``) porque lo que se prueba es el contrato del endpoint, no
el login.

La concurrencia vive en ``test_appointments_service.py`` (dos transacciones
reales) y el gate cross-tenant en ``test_appointments_rls.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from _agenda import APPOINTMENT_KEYS, APPOINTMENTS_URL, agenda, authenticate, payload, rows
from app.config import Settings
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

# --- helpers ---------------------------------------------------------------


def _authenticate(
    client: TestClient, settings: Settings, seeder: Any, tenant_id: Any, user_id: Any
) -> None:
    authenticate(client, settings, seeder, tenant_id, user_id)


def _agenda(seeder: Any, **kwargs: Any) -> dict[str, Any]:
    return agenda(seeder, **kwargs)


def _payload(data: dict[str, Any], **overrides: object) -> dict[str, object]:
    return payload(data, **overrides)


def _rows(db_engine: Engine, tenant_id: Any) -> list[dict[str, Any]]:
    return rows(db_engine, tenant_id)


# --- 2.1: 201 y contrato ---------------------------------------------------


def test_s1_1_un_turno_valido_se_crea_con_fin_y_duracion_derivados(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _agenda(seeder)
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=_payload(data, tipo_practica="consulta"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == APPOINTMENT_KEYS
    assert body["estado"] == "pendiente"
    assert body["origen"] == "recepcion"
    assert body["duracion_min"] == 30
    assert datetime.fromisoformat(body["inicio"]) == datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    assert datetime.fromisoformat(body["fin"]) == datetime(2026, 11, 16, 12, 30, tzinfo=UTC)
    assert body["tipo_practica"] == "consulta"

    rows = _rows(db_engine, data["tenant_id"])
    assert len(rows) == 1
    assert rows[0]["id"] == UUID(body["id"])
    assert rows[0]["tenant_id"] == data["tenant_id"]
    assert rows[0]["creado_por"] == data["user_id"]


def test_s1_1_la_respuesta_no_expone_tenant_id_ni_deleted_at(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder)
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    body = client.post(APPOINTMENTS_URL, json=_payload(data)).json()

    for forbidden in ("tenant_id", "deleted_at", "creado_por", "version"):
        assert forbidden not in body, forbidden


def test_s1_1_un_tenant_id_ajeno_en_body_query_y_header_se_ignora(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _agenda(seeder, prefix="tenant-ignorado")
    tenant_b = seeder.tenant(slug=f"b-{uuid4().hex[:8]}", nombre="Clínica B")
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(
        APPOINTMENTS_URL,
        params={"tenant_id": str(tenant_b)},
        headers={"X-Tenant-Id": str(tenant_b)},
        json=_payload(data, tenant_id=str(tenant_b)),
    )

    assert response.status_code == 201, response.text
    rows = _rows(db_engine, data["tenant_id"])
    assert len(rows) == 1
    assert _rows(db_engine, tenant_b) == []


def test_s4_3_un_turno_que_cruza_la_medianoche_persiste_fin_al_dia_siguiente(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, duracion_default_min=60, prefix="medianoche")
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(
        APPOINTMENTS_URL, json=_payload(data, inicio="2026-11-17T23:30:00-03:00")
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert datetime.fromisoformat(body["inicio"]) == datetime(2026, 11, 18, 2, 30, tzinfo=UTC)
    assert datetime.fromisoformat(body["fin"]) == datetime(2026, 11, 18, 3, 30, tzinfo=UTC)


@contextmanager
def _check_de_duracion_relajado(engine: Engine) -> Iterator[None]:
    """Permite sembrar ``duracion_default_min <= 0`` y repone el CHECK al salir.

    Con el esquema vigente la duración inválida **no** es alcanzable (``CHECK
    professional.duracion_default_min BETWEEN 5 AND 480`` y ``slot_min > 0`` en
    ``availability_rule``): ``409 duracion_invalida`` es una guarda defensiva del
    dominio. Para probar el camino HTTP se muta el esquema dentro del test —la
    misma técnica que usa el gate cross-tenant— y se restaura en el ``finally``.
    """
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE professional DROP CONSTRAINT ck_professional_duracion_default_min")
        )
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM professional WHERE duracion_default_min <= 0"))
            connection.execute(
                text(
                    "ALTER TABLE professional ADD CONSTRAINT "
                    "ck_professional_duracion_default_min "
                    "CHECK (duracion_default_min BETWEEN 5 AND 480)"
                )
            )


# --- 2.3: 401 y 409 de duración -------------------------------------------


def test_2_3_sin_sesion_es_401(client: TestClient) -> None:
    response = client.post(
        APPOINTMENTS_URL,
        json={
            "professional_id": str(uuid4()),
            "chair_id": str(uuid4()),
            "inicio": "2026-11-16T09:00:00-03:00",
        },
    )
    assert response.status_code == 401


def test_2_3_una_sesion_sin_membership_activa_es_401(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="sin-membership")
    seeder.set_membership_active(data["tenant_id"], data["user_id"], activo=False)
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=_payload(data))

    assert response.status_code == 401


def test_s3_4_una_duracion_cero_responde_409_sin_crear_el_turno(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    with _check_de_duracion_relajado(db_engine):
        data = _agenda(seeder, prefix="duracion", duracion_default_min=0)
        _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

        response = client.post(APPOINTMENTS_URL, json=_payload(data))

        assert response.status_code == 409, response.text
        body = response.json()
        assert body["code"] == "duracion_invalida"
        assert body["motivo"] == "duracion_invalida"
        assert _rows(db_engine, data["tenant_id"]) == []


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("fin", "2026-11-16T10:00:00-03:00"),
        ("duracion_min", 60),
        ("inicio", "2026-11-16T09:00:00"),
        ("tipo_practica", "blanqueamiento"),
    ],
)
def test_s1_2_un_payload_invalido_es_422_sin_crear_el_turno(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
    campo: str,
    valor: object,
) -> None:
    data = _agenda(seeder, prefix=f"422-{campo}")
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=_payload(data, **{campo: valor}))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    assert _rows(db_engine, data["tenant_id"]) == []


def test_s1_2_un_professional_id_mal_formado_es_422(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="uuid-malo")
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=_payload(data, professional_id="no-es-uuid"))

    assert response.status_code == 422


def test_el_turno_se_puede_crear_sin_paciente_identificado(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="sin-paciente")
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    body = _payload(data)
    del body["patient_id"]
    response = client.post(APPOINTMENTS_URL, json=body)

    assert response.status_code == 201, response.text
    assert response.json()["patient_id"] is None


def test_el_fin_no_puede_venir_del_cliente_pero_si_sale_en_la_respuesta(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _agenda(seeder, prefix="fin")
    _authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    ok = client.post(APPOINTMENTS_URL, json=_payload(data))
    assert ok.status_code == 201
    fin = datetime.fromisoformat(ok.json()["fin"])
    assert fin - datetime.fromisoformat(ok.json()["inicio"]) == timedelta(minutes=30)
