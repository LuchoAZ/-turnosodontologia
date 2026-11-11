"""Fronteras duras clínicas por HTTP (RN-CMP-04, design D4).

La frontera es la **ausencia del permiso** en la matriz, no un `if rol == …`. La
sonda reservada no consulta ni crea tablas: solo demuestra que la guarda corre
antes de la lógica y responde `501 capability_pending` a quien tiene el permiso.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from fastapi.testclient import TestClient

PATIENTS_URL = "/api/v1/clinical/patients"
FINALIZE_URL = "/api/v1/clinical/charts/finalize"

NO_CLINICAL_ROLES = ("front_desk", "billing", "accountant", "external_lab")
CLINICAL_READERS = ("professional", "clinical_admin", "owner")


def _authenticated_client(
    client: TestClient,
    settings: Settings,
    *,
    tenant_id: UUID,
    user_id: UUID,
    session_id: UUID,
) -> None:
    client.cookies.clear()
    client.cookies.set(
        ACCESS_COOKIE,
        create_access_token(
            settings,
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
            mfa=True,
            now=datetime.now(UTC),
        ),
        path="/",
    )


def _session_for(
    client: TestClient,
    settings: Settings,
    seeder: Any,
    roles: tuple[str, ...],
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    for role in roles:
        seeder.membership(tenant_id, user_id, role)
    seeded = seeder.session(tenant_id, user_id)
    _authenticated_client(
        client,
        settings,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=seeded.session_id,
    )


@pytest.mark.parametrize("role", NO_CLINICAL_ROLES)
def test_roles_sin_permiso_clinico_reciben_403(
    client: TestClient, auth_settings: Settings, seeder: Any, role: str
) -> None:
    _session_for(client, auth_settings, seeder, (role,))

    response = client.get(PATIENTS_URL)

    assert response.status_code == 403
    assert response.json() == {
        "code": "forbidden",
        "message": "No tenés permiso para realizar esta operación.",
    }
    # Ni pacientes, ni conteos, ni pistas de si el recurso existe.
    assert "patients" not in response.text
    assert "detail" not in response.text


@pytest.mark.parametrize("role", CLINICAL_READERS)
def test_roles_clinicos_pasan_la_guarda_y_la_capacidad_sigue_pendiente(
    client: TestClient, auth_settings: Settings, seeder: Any, role: str
) -> None:
    _session_for(client, auth_settings, seeder, (role,))

    response = client.get(PATIENTS_URL)

    assert response.status_code == 501
    assert response.json()["code"] == "capability_pending"
    assert "patients" not in response.text


def test_solo_el_profesional_satisface_chart_finalize(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    _session_for(client, auth_settings, seeder, ("assistant",))
    assistant = client.post(FINALIZE_URL)

    assert assistant.status_code == 403
    assert assistant.json()["code"] == "forbidden"

    _session_for(client, auth_settings, seeder, ("professional",))
    professional = client.post(FINALIZE_URL)

    assert professional.status_code == 501
    assert professional.json()["code"] == "capability_pending"


def test_la_union_de_los_roles_no_clinicos_sigue_sin_permiso(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    # Un usuario multi-rol acumula memberships: la unión de cuatro roles sin
    # acceso clínico no fabrica el permiso (la frontera es por permiso, no por
    # rol, y ningún rol interno "presta" los del paciente).
    _session_for(client, auth_settings, seeder, NO_CLINICAL_ROLES)

    patients = client.get(PATIENTS_URL)
    finalize = client.post(FINALIZE_URL)

    for response in (patients, finalize):
        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"


def test_la_union_con_un_rol_clinico_concede_la_lectura(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    _session_for(client, auth_settings, seeder, ("front_desk", "professional"))

    assert client.get(PATIENTS_URL).status_code == 501
