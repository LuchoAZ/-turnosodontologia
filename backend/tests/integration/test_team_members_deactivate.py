"""``DELETE /api/v1/team/members/{membership_id}`` (tasks 7.3/7.4, design D6).

La baja es lógica (``activo = false``, RN-EX-03) y su efecto es inmediato:
``require_tenant`` ya no encuentra membership activa y responde ``401`` en el
siguiente request del usuario dado de baja. La operación es idempotente y nunca
deja a la clínica sin owner activo (RN-TEN-04).
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
ME_URL = "/api/v1/auth/me"


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


def test_la_baja_desactiva_y_expulsa_al_usuario(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email="se-va@example.test", nombre="Vera")
    seeder.membership(tenant_id, target_id, "professional")
    membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.delete(f"{MEMBERS_URL}/{membership['id']}")

    assert response.status_code == 204, response.text
    assert response.content == b""
    after = _membership_of(db_engine, tenant_id, target_id)
    assert after["activo"] is False
    assert after["rol"] == "professional"
    # La fila existe: es baja lógica, no borrado (RN-EX-03).
    assert after["id"] == membership["id"]

    events = _events(db_engine, tenant_id)
    assert [event["tipo"] for event in events] == ["member_deactivated"]
    assert events[0]["actor_user_id"] == owner_id
    assert events[0]["target_user_id"] == target_id
    assert events[0]["detail"] == {"rol": "professional"}

    # Efecto inmediato: el usuario dado de baja ya no tiene membership activa.
    _authenticate(client, auth_settings, seeder, tenant_id, target_id)
    me = client.get(ME_URL)
    assert me.status_code == 401
    assert me.json()["code"] == "not_authenticated"
    assert "permissions" not in me.json()


def test_el_ultimo_owner_no_puede_darse_de_baja(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    seeder.membership(
        tenant_id, seeder.user(email="ex-owner-baja@example.test"), "owner", activo=False
    )
    membership = _membership_of(db_engine, tenant_id, owner_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.delete(f"{MEMBERS_URL}/{membership['id']}")

    assert response.status_code == 409
    assert response.json()["code"] == "last_owner"
    after = _membership_of(db_engine, tenant_id, owner_id)
    assert after["activo"] is True
    assert after["rol"] == "owner"
    owners = [
        row
        for row in _memberships(db_engine, tenant_id)
        if row["rol"] == "owner" and row["activo"]
    ]
    assert len(owners) == 1
    assert _events(db_engine, tenant_id) == []


def test_reintentar_la_baja_es_idempotente_y_no_duplica_el_evento(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email="ya-baja@example.test")
    seeder.membership(tenant_id, target_id, "front_desk")
    membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    first = client.delete(f"{MEMBERS_URL}/{membership['id']}")
    state_after_first = _memberships(db_engine, tenant_id)
    second = client.delete(f"{MEMBERS_URL}/{membership['id']}")

    assert first.status_code == 204
    assert second.status_code == 204
    assert _memberships(db_engine, tenant_id) == state_after_first
    assert [event["tipo"] for event in _events(db_engine, tenant_id)] == [
        "member_deactivated"
    ]


def test_una_membership_inexistente_responde_404(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.delete(f"{MEMBERS_URL}/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "membership_not_found"
    assert _events(db_engine, tenant_id) == []


@pytest.mark.parametrize("rol_actor", ["clinical_admin", "billing"])
def test_sin_team_delete_no_hay_baja(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
    rol_actor: str,
) -> None:
    tenant_id, _ = _owner(seeder)
    actor_id = seeder.user(email=f"actor-baja-{rol_actor}@example.test")
    seeder.membership(tenant_id, actor_id, rol_actor)
    target_id = seeder.user(email=f"objetivo-baja-{rol_actor}@example.test")
    seeder.membership(tenant_id, target_id, "professional")
    membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, actor_id)

    response = client.delete(f"{MEMBERS_URL}/{membership['id']}")

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert _membership_of(db_engine, tenant_id, target_id)["activo"] is True
    assert _events(db_engine, tenant_id) == []
