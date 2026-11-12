"""RN-AG-10 — paciente con otro turno del mismo profesional (task 5.1).

La regla compara el **rango clínico** ``[inicio, fin)`` del turno pedido contra los
turnos del mismo paciente y mismo profesional en estado ``pendiente``,
``confirmado`` o ``en_curso`` (lista explícita, nunca "activo" como comodín).

**Precedencia declarada**: cuando el paciente ya tiene un turno solapado con el
mismo profesional, también se viola RN-AG-02 (el profesional está ocupado). El
servicio evalúa RN-AG-10 **antes** del solape de recursos para que el ``409``
nombre la regla accionable con ese paciente (``paciente_solapado``). Por eso el
escenario de la spec "``patient_id = NULL`` y ya existe otro turno solapado del
mismo profesional → ``201``" es **inalcanzable** tal como está escrito: RN-AG-02
lo rechaza igual (regla dura, garantía de base). Los tests de abajo fijan el
comportamiento real: sin paciente la regla no aplica y el rechazo, si existe, es
``turno_solapado`` por el profesional.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from _agenda import APPOINTMENTS_URL, agenda, authenticate, payload, rows
from app.config import Settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

LUNES_9 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
LUNEZ_9_30 = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)


@pytest.mark.parametrize("estado", ["pendiente", "confirmado", "en_curso"])
def test_rn_ag_10_un_turno_solapado_del_mismo_paciente_y_profesional_es_409(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine, estado: str
) -> None:
    data = agenda(seeder, prefix=f"rnag10-{estado}")
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=data["chair_id"],
        inicio=LUNES_9,
        estado=estado,
        patient_id=data["patient_id"],
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data))

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "paciente_solapado"
    assert body["motivo"] == "paciente_solapado"
    assert body["rangoEnConflicto"]["inicio"]
    assert len(rows(db_engine, data["tenant_id"])) == 1


@pytest.mark.parametrize("estado", ["cancelado", "no_asistio"])
def test_rn_ag_10_un_turno_cancelado_del_paciente_no_bloquea(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine, estado: str
) -> None:
    data = agenda(seeder, prefix=f"rnag10-libre-{estado}")
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=data["chair_id"],
        inicio=LUNES_9,
        estado=estado,
        patient_id=data["patient_id"],
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data))

    assert response.status_code == 201, response.text
    assert len(rows(db_engine, data["tenant_id"])) == 2


def test_rn_ag_10_un_turno_contiguo_del_paciente_no_es_solape(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="rnag10-contiguo")
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=data["chair_id"],
        inicio=LUNES_9,
        patient_id=data["patient_id"],
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data, inicio="2026-11-16T09:30:00-03:00"))

    assert response.status_code == 201, response.text
    assert datetime.fromisoformat(response.json()["inicio"]) == LUNEZ_9_30


def test_rn_ag_10_el_mismo_paciente_con_otro_profesional_se_crea(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="rnag10-otro-prof")
    otro_profesional = seeder.professional(data["tenant_id"], nombre="Beto")
    otro_sillon = seeder.chair(data["tenant_id"], nombre="Sillón B")
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=otro_sillon,
        inicio=LUNES_9,
        patient_id=data["patient_id"],
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(
        APPOINTMENTS_URL,
        json=payload(data, professional_id=str(otro_profesional), chair_id=str(data["chair_id"])),
    )

    assert response.status_code == 201, response.text
    assert len(rows(db_engine, data["tenant_id"])) == 2


def test_sin_paciente_identificado_rn_ag_10_no_aplica_y_gana_rn_ag_02(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    """Sin paciente la regla no aplica; el profesional ocupado lo rechaza RN-AG-02."""
    data = agenda(seeder, prefix="rnag10-null", con_paciente=False)
    paciente_ajeno = seeder.patient(data["tenant_id"], dni=None)
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=data["chair_id"],
        inicio=LUNES_9,
        patient_id=paciente_ajeno,
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])
    assert data["patient_id"] is None

    response = client.post(APPOINTMENTS_URL, json=payload(data))

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "turno_solapado"
    assert body["recurso"] == "professional"
    assert len(rows(db_engine, data["tenant_id"])) == 1
