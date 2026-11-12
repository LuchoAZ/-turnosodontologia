"""Recursos inactivos o inexistentes en la creación del turno (task 3.2; S1.3).

Un recurso desactivado no recibe turnos (``409 recurso_inactivo``) y el chequeo es
independiente del solape: el turno ni siquiera tiene un horario válido contra el
que comparar cuando el profesional está inactivo. Un id que no existe en el tenant
es ``404`` indistinguible de un id de otro tenant (RN-EX-06); el caso cross-tenant
completo vive en el gate de aislamiento (task 6.1).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from _agenda import APPOINTMENTS_URL, agenda, authenticate, payload, rows
from app.config import Settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine


@pytest.mark.parametrize("recurso", ["professional", "chair"])
def test_s1_3_un_recurso_inactivo_es_409_con_su_motivo(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine, recurso: str
) -> None:
    data = agenda(
        seeder,
        prefix=f"inactivo-{recurso}",
        professional_activo=recurso != "professional",
        chair_activo=recurso != "chair",
    )
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data))

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "recurso_inactivo"
    assert body["recurso"] == recurso
    assert body["motivo"] == "recurso_inactivo"
    assert "rangoEnConflicto" not in body
    assert rows(db_engine, data["tenant_id"]) == []


def test_un_recurso_inexistente_es_404_y_no_crea_el_turno(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="inexistente")
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data, chair_id=str(uuid4())))

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["code"] == "recurso_no_encontrado"
    assert body["recurso"] == "chair"
    assert rows(db_engine, data["tenant_id"]) == []


def test_un_professional_inexistente_es_404_y_nombra_el_recurso(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = agenda(seeder, prefix="prof-inexistente")
    authenticate(client, auth_settings, seeder, data["tenant_id"], data["user_id"])

    response = client.post(APPOINTMENTS_URL, json=payload(data, professional_id=str(uuid4())))

    assert response.status_code == 404, response.text
    assert response.json()["recurso"] == "professional"
