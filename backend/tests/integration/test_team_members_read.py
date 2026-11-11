"""``GET /api/v1/team/members`` (tasks 5.1/5.3, design D6).

El HTTP corre como ``odontologia_app`` con el GUC del tenant ya fijado por
``require_auth``, así que la lista sale filtrada por RLS sin que el endpoint
mande ``tenant_id``. El DTO es la lista blanca de lo que sale: ni hash, ni
secreto MFA, ni ``tenant_id`` ajeno, ni permisos.

La sesión se emite con el mismo ``create_access_token`` que usa el login (patrón
de ``test_auth_me``): ``owner`` y ``billing`` exigen MFA enrolado al iniciar
sesión real, y acá lo que se prueba es la autorización de la lista, no el flujo
de MFA (que ya tiene su propia suite).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from fastapi.testclient import TestClient

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

READERS = ("owner", "clinical_admin", "billing")
NOT_READERS = (
    "professional",
    "assistant",
    "front_desk",
    "patient",
    "external_lab",
    "accountant",
)


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


def _seed_tenant(seeder: Any) -> tuple[UUID, str]:
    slug = f"team-read-{uuid4().hex[:8]}"
    return seeder.tenant(slug=slug, nombre="Clínica Lectura"), slug


def _seed_member(
    seeder: Any,
    tenant_id: UUID,
    rol: str,
    *,
    activo: bool = True,
    nombre: str = "Ana",
    apellido: str = "Pérez",
) -> tuple[UUID, str]:
    email = f"{rol}-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email, nombre=nombre, apellido=apellido)
    seeder.membership(tenant_id, user_id, rol, activo=activo)
    return user_id, email


def _assert_no_secrets(payload: object) -> None:
    serialized = str(payload).lower()
    for forbidden in ("password_hash", "mfa_secret", "tenant_id", "permissions", "token"):
        assert forbidden not in serialized


def test_el_owner_lee_activos_e_inactivos_sin_datos_sensibles(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id, _ = _seed_tenant(seeder)
    owner_id, _ = _seed_member(
        seeder, tenant_id, "owner", nombre="Olivia", apellido="Owner"
    )
    professional_id, _ = _seed_member(seeder, tenant_id, "professional", nombre="Pablo")
    inactive_id, _ = _seed_member(
        seeder, tenant_id, "front_desk", activo=False, nombre="Fran"
    )

    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)
    response = client.get(MEMBERS_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"members"}
    members = body["members"]
    assert len(members) == 3
    for member in members:
        assert set(member) == MEMBER_KEYS
    # ``professional_id`` todavía no existe en C-04: viaja siempre en ``null``.
    assert all(member["professional_id"] is None for member in members)

    by_user = {member["user_id"]: member for member in members}
    assert by_user[str(professional_id)]["rol"] == "professional"
    assert by_user[str(professional_id)]["activo"] is True
    assert by_user[str(inactive_id)]["rol"] == "front_desk"
    assert by_user[str(inactive_id)]["activo"] is False
    assert by_user[str(inactive_id)]["nombre"] == "Fran"
    _assert_no_secrets(body)


@pytest.mark.parametrize("role", READERS)
def test_los_tres_roles_con_team_read_leen(
    client: TestClient, auth_settings: Settings, seeder: Any, role: str
) -> None:
    tenant_id, _ = _seed_tenant(seeder)
    if role != "owner":
        _seed_member(seeder, tenant_id, "owner")
    actor_id, _ = _seed_member(seeder, tenant_id, role, nombre="Actor")

    _authenticate(client, auth_settings, seeder, tenant_id, actor_id)
    response = client.get(MEMBERS_URL)

    assert response.status_code == 200, response.text
    assert len(response.json()["members"]) >= 1


@pytest.mark.parametrize("role", NOT_READERS)
def test_los_roles_sin_team_read_reciben_403(
    client: TestClient, auth_settings: Settings, seeder: Any, role: str
) -> None:
    tenant_id, _ = _seed_tenant(seeder)
    _seed_member(seeder, tenant_id, "owner")
    actor_id, _ = _seed_member(seeder, tenant_id, role)

    _authenticate(client, auth_settings, seeder, tenant_id, actor_id)
    response = client.get(MEMBERS_URL)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert "members" not in response.json()
    _assert_no_secrets(response.json())


def test_el_orden_es_estable_entre_llamadas(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id, _ = _seed_tenant(seeder)
    owner_id, _ = _seed_member(seeder, tenant_id, "owner")
    _seed_member(seeder, tenant_id, "professional", nombre="Pablo")
    _seed_member(seeder, tenant_id, "assistant", nombre="Aldo")
    _seed_member(seeder, tenant_id, "front_desk", nombre="Fran")

    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)
    first = client.get(MEMBERS_URL).json()["members"]
    second = client.get(MEMBERS_URL).json()["members"]

    # Cuatro memberships sembradas: owner + professional + assistant + front_desk.
    # Si RLS no filtrara, el tenant vería las memberships de los demás tests.
    assert len(first) == 4
    assert len(second) == 4
    assert [member["id"] for member in first] == [member["id"] for member in second]


def test_una_membership_owner_inactiva_aparece_pero_no_cuenta(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    """Dos filas ``owner``: la invariante cuenta solo la activa (design D7)."""
    tenant_id, _ = _seed_tenant(seeder)
    owner_id, _ = _seed_member(seeder, tenant_id, "owner")
    _seed_member(seeder, tenant_id, "owner", activo=False)

    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)
    members = client.get(MEMBERS_URL).json()["members"]

    owners = [member for member in members if member["rol"] == "owner"]
    assert len(owners) == 2
    assert sum(1 for member in owners if member["activo"]) == 1


def test_un_tenant_con_un_solo_miembro_devuelve_un_elemento(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id, _ = _seed_tenant(seeder)
    actor_id, _ = _seed_member(seeder, tenant_id, "owner")

    _authenticate(client, auth_settings, seeder, tenant_id, actor_id)
    members = client.get(MEMBERS_URL).json()["members"]

    assert len(members) == 1
    assert members[0]["user_id"] == str(actor_id)
    assert members[0]["rol"] == "owner"
