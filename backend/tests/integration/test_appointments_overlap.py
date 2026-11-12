"""Solape por profesional y por sillón (task 3.1; RN-AG-02, escenarios S2.1-S2.4).

El setup siembra los turnos **ya existentes** con ``patient_id = None``: los turnos
sin paciente identificado son legales y así RN-AG-10 no se dispara de rebote, que
es lo que se quiere aislar acá. Cada caso compara el contrato ``409`` completo
(``code``, ``recurso``, ``motivo`` y ``rangoEnConflicto``) y verifica que no se
persistió la fila nueva.

Los dos buffers se prueban por separado: el del turno **existente** (lo reserva su
propia fila) y el del turno **nuevo** (lo aporta la ``availability_rule``
aplicable). Un solo caso de buffers no cubre los dos caminos del ``EXCLUDE``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from _agenda import APPOINTMENTS_URL, agenda, authenticate, payload, rows
from app.config import Settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

# Lunes 16/11/2026: 09:00 local (UTC-3) = 12:00 UTC.
LUNES_9 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def _iso(momento: datetime) -> datetime:
    return datetime.fromisoformat(momento.isoformat())


def test_s2_1_un_solape_por_profesional_es_409_y_nombra_el_recurso(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="solape-profesional")
    otro_sillon = seeder.chair(data["tenant_id"], nombre="Sillón B")
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=data["chair_id"],
        inicio=LUNES_9,
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    # Mismo profesional, sillón libre: el conflicto es del recurso humano.
    response = client.post(APPOINTMENTS_URL, json=payload(data, chair_id=str(otro_sillon)))

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "turno_solapado"
    assert body["recurso"] == "professional"
    assert body["motivo"] == "turno_solapado"
    assert _iso(datetime.fromisoformat(body["rangoEnConflicto"]["inicio"])) == LUNES_9
    assert _iso(datetime.fromisoformat(body["rangoEnConflicto"]["fin"])) == datetime(
        2026, 11, 16, 12, 30, tzinfo=UTC
    )
    assert len(rows(db_engine, data["tenant_id"])) == 1


def test_s2_2_un_solape_por_sillon_es_409_y_nombra_el_recurso(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="solape-sillon")
    otro_profesional = seeder.professional(data["tenant_id"], nombre="Beto")
    seeder.appointment(
        data["tenant_id"],
        professional_id=otro_profesional,
        chair_id=data["chair_id"],
        inicio=LUNES_9,
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    # Profesional libre, sillón ocupado: el conflicto es del recurso físico.
    response = client.post(APPOINTMENTS_URL, json=payload(data))

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["recurso"] == "chair"
    assert body["motivo"] == "turno_solapado"
    assert body["rangoEnConflicto"]["inicio"]
    assert len(rows(db_engine, data["tenant_id"])) == 1


@pytest.mark.parametrize("estado", ["cancelado", "no_asistio"])
def test_s2_3_un_turno_cancelado_o_no_asistio_no_bloquea(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine, estado: str
) -> None:
    data = agenda(seeder, prefix=f"libera-{estado}")
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=data["chair_id"],
        inicio=LUNES_9,
        estado=estado,
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data))

    assert response.status_code == 201, response.text
    assert len(rows(db_engine, data["tenant_id"])) == 2


def test_s2_4_un_turno_contiguo_se_crea_porque_el_rango_es_semiabierto(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="contiguo")
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=data["chair_id"],
        inicio=LUNES_9,
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    # Nuevo inicio == fin del existente (12:30 UTC): extremo final exclusivo.
    response = client.post(APPOINTMENTS_URL, json=payload(data, inicio="2026-11-16T09:30:00-03:00"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert _iso(datetime.fromisoformat(body["inicio"])) == datetime(
        2026, 11, 16, 12, 30, tzinfo=UTC
    )
    assert _iso(datetime.fromisoformat(body["fin"])) == datetime(2026, 11, 16, 13, 0, tzinfo=UTC)
    assert len(rows(db_engine, data["tenant_id"])) == 2


def test_el_buffer_posterior_del_turno_existente_tambien_bloquea(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="buffer-posterior")
    otro_sillon = seeder.chair(data["tenant_id"], nombre="Sillón B")
    # El turno existente reserva hasta 12:45 por su buffer de higiene.
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=data["chair_id"],
        inicio=LUNES_9,
        buffer_posterior_min=15,
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data, chair_id=str(otro_sillon),
                                                          inicio="2026-11-16T09:35:00-03:00"))

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["recurso"] == "professional"
    # El rango informado es el del turno, no el bloqueado con buffers.
    assert _iso(datetime.fromisoformat(body["rangoEnConflicto"]["fin"])) == datetime(
        2026, 11, 16, 12, 30, tzinfo=UTC
    )
    assert len(rows(db_engine, data["tenant_id"])) == 1


def test_el_buffer_previo_de_la_regla_del_turno_nuevo_tambien_bloquea(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="buffer-previo")
    otro_sillon = seeder.chair(data["tenant_id"], nombre="Sillón B")
    seeder.availability_rule(
        data["tenant_id"],
        professional_id=data["professional_id"],
        dia_semana=0,
        hora_inicio=time(9, 0),
        hora_fin=time(12, 0),
        slot_min=30,
        buffer_previo_min=10,
        fecha_desde=date(2026, 1, 1),
    )
    # Existente 11:30-11:55 UTC; el nuevo bloquea desde 11:50 (12:00 - 10 min).
    seeder.appointment(
        data["tenant_id"],
        professional_id=data["professional_id"],
        chair_id=otro_sillon,
        inicio=datetime(2026, 11, 16, 11, 30, tzinfo=UTC),
        duracion_min=25,
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data))

    assert response.status_code == 409, response.text
    assert response.json()["recurso"] == "professional"
    assert len(rows(db_engine, data["tenant_id"])) == 1
