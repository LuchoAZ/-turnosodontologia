"""``PATCH /api/v1/team/members/{membership_id}`` (tasks 7.1/7.2, design D6).

El cambio de rol es la única vía para mover a alguien dentro del equipo, y el
único camino legítimo para dejar de ser ``owner`` es la transferencia (RN-TEN-04):
por eso la autodemoción del último owner activo se rechaza con ``409 last_owner``
antes de escribir cualquier fila.

La sesión se emite con ``create_access_token`` (patrón de ``test_auth_me``):
``owner`` exige MFA enrolado en el login real y acá se prueba autorización de
equipo, no el flujo de MFA.
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
from sqlalchemy.engine import Engine

MEMBERS_URL = "/api/v1/team/members"

MEMBER_KEYS = {
    "id",
    "user_id",
    "email",
    "nombre",
    "apellido",
    "rol",
    "activo",
    "professional_id",
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


def _events(engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tipo::text AS tipo, actor_user_id, target_user_id, detail
                FROM membership_event WHERE tenant_id = :tenant_id ORDER BY id
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings()
        return [dict(row) for row in rows]


def _memberships(engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id, user_id, rol::text AS rol, activo
                FROM membership WHERE tenant_id = :tenant_id ORDER BY rol, id
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings()
        return [dict(row) for row in rows]


def _owner(seeder: Any) -> tuple[UUID, UUID]:
    tenant_id = seeder.tenant()
    owner_id = seeder.user(email=f"owner-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_id, owner_id, "owner")
    return tenant_id, owner_id


def _membership_of(engine: Engine, tenant_id: UUID, user_id: UUID) -> dict[str, Any]:
    return next(
        row for row in _memberships(engine, tenant_id) if row["user_id"] == user_id
    )


def test_el_owner_cambia_el_rol_y_queda_auditado(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email="profe@example.test", nombre="Paula")
    seeder.membership(tenant_id, target_id, "professional")
    membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.patch(
        f"{MEMBERS_URL}/{membership['id']}", json={"rol": "clinical_admin"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == MEMBER_KEYS
    assert body["rol"] == "clinical_admin"
    assert body["user_id"] == str(target_id)
    assert body["activo"] is True

    events = _events(db_engine, tenant_id)
    assert [event["tipo"] for event in events] == ["member_role_changed"]
    assert events[0]["actor_user_id"] == owner_id
    assert events[0]["target_user_id"] == target_id
    assert events[0]["detail"] == {
        "rol_anterior": "professional",
        "rol_nuevo": "clinical_admin",
    }


def test_el_ultimo_owner_no_puede_autodemoverse(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    # Un owner inactivo no cuenta para la invariante: sigue habiendo uno solo.
    seeder.membership(
        tenant_id, seeder.user(email="ex-owner@example.test"), "owner", activo=False
    )
    membership = _membership_of(db_engine, tenant_id, owner_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.patch(
        f"{MEMBERS_URL}/{membership['id']}", json={"rol": "clinical_admin"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "last_owner"

    after = _membership_of(db_engine, tenant_id, owner_id)
    assert after["rol"] == "owner"
    assert after["activo"] is True
    assert _events(db_engine, tenant_id) == []


def test_una_membership_de_otro_tenant_responde_404_igual_que_un_id_inexistente(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_a, owner_a = _owner(seeder)
    tenant_b = seeder.tenant()
    foreign_id = seeder.user(email=f"ajeno-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_b, foreign_id, "professional")
    foreign_membership = _membership_of(db_engine, tenant_b, foreign_id)
    _authenticate(client, auth_settings, seeder, tenant_a, owner_a)

    foreign = client.patch(
        f"{MEMBERS_URL}/{foreign_membership['id']}", json={"rol": "clinical_admin"}
    )
    missing = client.patch(
        f"{MEMBERS_URL}/{uuid4()}", json={"rol": "clinical_admin"}
    )

    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["code"] == "membership_not_found"
    # La membership de B queda intacta.
    assert _membership_of(db_engine, tenant_b, foreign_id)["rol"] == "professional"
    assert _events(db_engine, tenant_a) == []
    assert _events(db_engine, tenant_b) == []


def test_repetir_el_mismo_rol_es_idempotente_y_no_audita(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email="mismo@example.test")
    seeder.membership(tenant_id, target_id, "assistant")
    before = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.patch(
        f"{MEMBERS_URL}/{before['id']}", json={"rol": "assistant"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["rol"] == "assistant"
    assert _membership_of(db_engine, tenant_id, target_id) == before
    assert _events(db_engine, tenant_id) == []


def test_el_rol_destino_ya_existe_en_otra_membership_del_usuario(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email="multi-rol@example.test")
    seeder.membership(tenant_id, target_id, "professional")
    seeder.membership(tenant_id, target_id, "clinical_admin")
    target_membership = next(
        row
        for row in _memberships(db_engine, tenant_id)
        if row["user_id"] == target_id and row["rol"] == "professional"
    )
    before = _memberships(db_engine, tenant_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.patch(
        f"{MEMBERS_URL}/{target_membership['id']}", json={"rol": "clinical_admin"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "membership_exists"
    assert _memberships(db_engine, tenant_id) == before
    assert _events(db_engine, tenant_id) == []


@pytest.mark.parametrize(
    ("rol", "status", "code"),
    [
        ("owner", 409, "owner_must_be_transferred"),
        ("patient", 422, "role_not_assignable"),
        ("external_lab", 422, "role_not_assignable"),
    ],
)
def test_el_patch_no_es_una_via_para_owner_ni_roles_de_portal(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
    rol: str,
    status: int,
    code: str,
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email=f"destino-{rol}@example.test")
    seeder.membership(tenant_id, target_id, "professional")
    membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.patch(f"{MEMBERS_URL}/{membership['id']}", json={"rol": rol})

    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert _membership_of(db_engine, tenant_id, target_id)["rol"] == "professional"
    owners = [
        row
        for row in _memberships(db_engine, tenant_id)
        if row["rol"] == "owner" and row["activo"]
    ]
    assert len(owners) == 1
    assert _events(db_engine, tenant_id) == []


@pytest.mark.parametrize("rol_actor", ["clinical_admin", "billing"])
def test_sin_team_update_no_hay_cambio_de_rol(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
    rol_actor: str,
) -> None:
    tenant_id, _ = _owner(seeder)
    actor_id = seeder.user(email=f"actor-{rol_actor}@example.test")
    seeder.membership(tenant_id, actor_id, rol_actor)
    target_id = seeder.user(email=f"objetivo-{rol_actor}@example.test")
    seeder.membership(tenant_id, target_id, "professional")
    membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, actor_id)

    response = client.patch(
        f"{MEMBERS_URL}/{membership['id']}", json={"rol": "assistant"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert _membership_of(db_engine, tenant_id, target_id)["rol"] == "professional"
    assert _events(db_engine, tenant_id) == []
