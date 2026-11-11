"""Contrato de `require_permission` (tasks 2.3/2.4, design D3).

El guard es puro: resuelve los permisos de los roles ya validados por
`require_tenant` y no toca la base. Un permiso ausente corta **antes** de
ejecutar el handler (el contador queda en cero) y responde `403 forbidden`; el
permiso que faltó solo aparece en el log de aplicación, nunca en la respuesta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import cast
from uuid import uuid4

import pytest
from app.api.v1.deps import AuthContext, require_tenant
from app.config import Settings
from app.domain.auth.errors import AuthError, AuthErrorCode
from app.domain.rbac.guard import require_permission
from app.domain.rbac.matrix import Permission
from app.main import create_app
from app.models.auth import Session as SessionModel
from app.models.tenancy import Role, User
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


@dataclass
class _Calls:
    count: int = field(default=0)


def _context(roles: list[Role]) -> AuthContext:
    return AuthContext(
        user=User(
            id=uuid4(),
            email="guard@example.test",
            nombre="Guard",
            apellido="Test",
        ),
        session=cast(SessionModel, object()),
        tenant_id=uuid4(),
        roles=roles,
        mfa_satisfied=True,
    )


def _build_app(
    settings: Settings,
    roles: list[Role],
    calls: _Calls,
    permissions: tuple[Permission, ...],
) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[require_tenant] = lambda: _context(roles)

    @application.get("/_test/guard")
    async def _endpoint(
        _: AuthContext = Depends(require_permission(*permissions)),
    ) -> dict[str, int]:
        calls.count += 1
        return {"ok": 1}

    return application


@pytest.fixture
def calls() -> _Calls:
    return _Calls()


@pytest.mark.parametrize(
    ("role", "permission", "expected"),
    [
        (Role.front_desk, Permission.appointment_create, 200),
        (Role.front_desk, Permission.clinical_record_read, 403),
        (Role.professional, Permission.chart_finalize, 200),
        (Role.professional, Permission.team_create, 403),
        (Role.billing, Permission.invoice_create, 200),
        (Role.billing, Permission.clinical_record_update, 403),
        (Role.assistant, Permission.chart_read, 200),
        (Role.assistant, Permission.chart_finalize, 403),
    ],
)
def test_permiso_presente_pasa_y_ausente_corta(
    settings: Settings,
    role: Role,
    permission: Permission,
    expected: int,
    calls: _Calls,
) -> None:
    with TestClient(_build_app(settings, [role], calls, (permission,))) as client:
        response = client.get("/_test/guard")

    assert response.status_code == expected
    if expected == 403:
        assert response.json() == {
            "code": "forbidden",
            "message": "No tenés permiso para realizar esta operación.",
        }
        assert calls.count == 0
    else:
        assert calls.count == 1


def test_varios_permisos_exigen_todos(settings: Settings, calls: _Calls) -> None:
    # clinical_admin tiene chair.create pero no team.create: AND, no OR.
    with TestClient(
        _build_app(
            settings,
            [Role.clinical_admin],
            calls,
            (Permission.chair_create, Permission.team_create),
        )
    ) as client:
        assert client.get("/_test/guard").status_code == 403
        assert calls.count == 0

    # La unión con billing (team.read no es team.create) sigue faltando.
    with TestClient(
        _build_app(
            settings,
            [Role.clinical_admin, Role.billing],
            calls,
            (Permission.chair_create, Permission.team_create),
        )
    ) as client:
        assert client.get("/_test/guard").status_code == 403

    # owner tiene ambos: pasa y el handler corre una sola vez.
    with TestClient(
        _build_app(
            settings,
            [Role.owner],
            calls,
            (Permission.team_create, Permission.chair_create),
        )
    ) as client:
        assert client.get("/_test/guard").status_code == 200
        assert calls.count == 1


def test_sin_membership_activa_el_401_gana_al_403(settings: Settings, calls: _Calls) -> None:
    application = create_app(settings)

    def _unauthenticated() -> AuthContext:
        raise AuthError(AuthErrorCode.not_authenticated)

    application.dependency_overrides[require_tenant] = _unauthenticated

    @application.get("/_test/guard")
    async def _endpoint(
        _: AuthContext = Depends(require_permission(Permission.team_read)),
    ) -> None:
        calls.count += 1

    with TestClient(application) as client:
        response = client.get("/_test/guard")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert calls.count == 0


def test_roles_vacios_fallan_cerrado(settings: Settings, calls: _Calls) -> None:
    with TestClient(_build_app(settings, [], calls, (Permission.team_read,))) as client:
        assert client.get("/_test/guard").status_code == 403
        assert calls.count == 0


def test_el_permiso_faltante_solo_aparece_en_el_log(
    settings: Settings, calls: _Calls, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="app.domain.rbac.guard")

    with TestClient(
        _build_app(settings, [Role.billing], calls, (Permission.clinical_record_update,))
    ) as client:
        response = client.get("/_test/guard")

    assert response.status_code == 403
    assert "clinical_record.update" not in response.text
    assert "clinical_record.update" in caplog.text
