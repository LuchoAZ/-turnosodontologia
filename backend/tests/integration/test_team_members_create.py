"""``POST /api/v1/team/members`` — alta sin invitación (tasks 6.1/6.3, design D6).

El alta acepta un usuario existente o crea uno nuevo con contraseña temporal
(Argon2id). La contraseña **nunca** sale en la respuesta ni en el evento, y la
transacción es única: si falla el evento o la membership, no queda ``user``
huérfano. La lectura del evento va como superusuario porque ``odontologia_app``
no tiene ``SELECT`` sobre ``membership_event``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from app.domain.auth.passwords import verify_password
from app.domain.rbac.errors import RbacError, RbacErrorCode
from app.domain.team import service
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

CREATE_URL = "/api/v1/team/members"

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


def _user_row(engine: Engine, email: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                'SELECT id, email, password_hash, credentials_version FROM "user" '
                "WHERE email = :email"
            ),
            {"email": email},
        ).mappings().one_or_none()
    return dict(row) if row else None


def _memberships(engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id, user_id, rol::text AS rol, activo
                FROM membership WHERE tenant_id = :tenant_id ORDER BY rol
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


@contextmanager
def _app(settings: Settings) -> Iterator[TestClient]:
    application = create_app(settings)
    with TestClient(application) as client:
        yield client


def test_alta_de_usuario_existente_crea_membership_y_evento(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email="nuevo-miembro@example.test", nombre="Nora")
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        CREATE_URL, json={"email": "nuevo-miembro@example.test", "rol": "professional"}
    )

    assert response.status_code == 201, response.text
    member = response.json()
    assert set(member) == MEMBER_KEYS
    assert member["user_id"] == str(target_id)
    assert member["rol"] == "professional"
    assert member["activo"] is True
    assert member["nombre"] == "Nora"

    events = _events(db_engine, tenant_id)
    assert [event["tipo"] for event in events] == ["member_created"]
    assert events[0]["actor_user_id"] == owner_id
    assert events[0]["target_user_id"] == target_id
    assert events[0]["detail"] == {"rol": "professional"}


def test_alta_de_usuario_inexistente_hashea_la_password_temporal(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)
    temporal = "clave-temporal-2026"

    response = client.post(
        CREATE_URL,
        json={
            "email": "desde-cero@example.test",
            "rol": "front_desk",
            "password_temporal": temporal,
        },
    )

    assert response.status_code == 201, response.text
    assert temporal not in response.text
    assert "password" not in response.text.lower()

    created = _user_row(db_engine, "desde-cero@example.test")
    assert created is not None
    assert created["password_hash"].startswith("$argon2id$")
    assert verify_password(temporal, created["password_hash"])

    events = _events(db_engine, tenant_id)
    assert len(events) == 1
    assert temporal not in str(events[0]["detail"])
    assert "clave" not in str(events[0]["detail"]).lower()


@pytest.mark.parametrize("rol", ["patient", "external_lab"])
def test_los_roles_de_portal_no_se_asignan_por_esta_via(
    client: TestClient, auth_settings: Settings, seeder: Any, rol: str
) -> None:
    tenant_id, owner_id = _owner(seeder)
    seeder.user(email="portal@example.test")
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(CREATE_URL, json={"email": "portal@example.test", "rol": rol})

    assert response.status_code == 422
    assert response.json()["code"] == "role_not_assignable"


def test_owner_no_se_asigna_se_transfiere(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    seeder.user(email="aspirante@example.test")
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        CREATE_URL, json={"email": "aspirante@example.test", "rol": "owner"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "owner_must_be_transferred"
    assert _events(db_engine, tenant_id) == []


def test_membership_duplicada_responde_409(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email="ya-esta@example.test")
    seeder.membership(tenant_id, target_id, "assistant")
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        CREATE_URL, json={"email": "ya-esta@example.test", "rol": "assistant"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "membership_exists"
    assert _events(db_engine, tenant_id) == []


def test_el_actor_sin_team_create_recibe_403(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, _ = _owner(seeder)
    actor_id = seeder.user(email="recepcion@example.test")
    seeder.membership(tenant_id, actor_id, "front_desk")
    seeder.user(email="candidato@example.test")
    _authenticate(client, auth_settings, seeder, tenant_id, actor_id)

    response = client.post(
        CREATE_URL, json={"email": "candidato@example.test", "rol": "professional"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert _events(db_engine, tenant_id) == []


def test_si_falla_el_evento_no_queda_usuario_huerfano(
    auth_settings: Settings, seeder: Any, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id, owner_id = _owner(seeder)

    def _boom(*_: object, **__: object) -> None:
        raise RbacError(RbacErrorCode.invalid_request)

    monkeypatch.setattr(service, "_record_event", _boom)

    with _app(auth_settings) as client:
        _authenticate(client, auth_settings, seeder, tenant_id, owner_id)
        response = client.post(
            CREATE_URL,
            json={
                "email": "huerfano@example.test",
                "rol": "professional",
                "password_temporal": "clave-temporal-2026",
            },
        )

    assert response.status_code == 422
    assert _user_row(db_engine, "huerfano@example.test") is None
    rows = _memberships(db_engine, tenant_id)
    assert len(rows) == 1
    assert rows[0]["user_id"] == owner_id
    assert rows[0]["rol"] == "owner"
    assert _events(db_engine, tenant_id) == []


def test_un_usuario_de_otro_tenant_conserva_su_membership_y_su_password(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_a, owner_a = _owner(seeder)
    tenant_b = seeder.tenant()
    shared_email = "compartido@example.test"
    shared_id = seeder.user(email=shared_email)
    seeder.membership(tenant_b, shared_id, "professional")
    before = _user_row(db_engine, shared_email)

    _authenticate(client, auth_settings, seeder, tenant_a, owner_a)
    response = client.post(CREATE_URL, json={"email": shared_email, "rol": "front_desk"})

    assert response.status_code == 201, response.text
    assert response.json()["user_id"] == str(shared_id)

    in_b = _memberships(db_engine, tenant_b)
    assert len(in_b) == 1
    assert in_b[0]["rol"] == "professional"
    assert in_b[0]["activo"] is True
    assert _user_row(db_engine, shared_email) == before


def test_password_temporal_ausente_no_crea_usuario(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        CREATE_URL, json={"email": "sin-clave@example.test", "rol": "assistant"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert _user_row(db_engine, "sin-clave@example.test") is None
    assert _events(db_engine, tenant_id) == []


def test_password_temporal_corta_no_crea_usuario(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        CREATE_URL,
        json={
            "email": "clave-corta@example.test",
            "rol": "assistant",
            "password_temporal": "corta-12345",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert _user_row(db_engine, "clave-corta@example.test") is None


def test_readmision_reactiva_la_fila_existente_sin_duplicar(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id = seeder.user(email="vuelve@example.test")
    seeder.membership(tenant_id, target_id, "professional", activo=False)
    previous_id = next(
        row["id"] for row in _memberships(db_engine, tenant_id) if row["user_id"] == target_id
    )

    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)
    response = client.post(
        CREATE_URL, json={"email": "vuelve@example.test", "rol": "professional"}
    )

    assert response.status_code == 201, response.text
    assert response.json()["id"] == str(previous_id)
    assert response.json()["activo"] is True

    rows = _memberships(db_engine, tenant_id)
    assert len(rows) == 2
    reactivated = next(row for row in rows if row["user_id"] == target_id)
    assert reactivated["id"] == previous_id
    assert reactivated["activo"] is True

    events = _events(db_engine, tenant_id)
    assert [event["tipo"] for event in events] == ["member_reactivated"]
    assert "member_created" not in [event["tipo"] for event in events]
    assert events[0]["detail"] == {"rol": "professional"}
