"""``GET /api/v1/auth/me`` y guardas de sesión (tasks 3.6/3.8, design D4.3).

El access token se emite con el mismo ``SESSION_SECRET`` que usa la app; el
endpoint nunca lee ``tenant_id`` del cliente, lo toma del ``sid`` de la sesión y
lo revalida contra la ``membership`` bajo RLS.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.config import Settings
from app.core.security import ACCESS_COOKIE, REFRESH_COOKIE, create_access_token
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

ME_URL = "/api/v1/auth/me"
REFRESH_URL = "/api/v1/auth/refresh"


def _access_token(
    settings: Settings,
    *,
    user_id: UUID,
    session_id: UUID,
    tenant_id: UUID,
    now: datetime | None = None,
) -> str:
    return create_access_token(
        settings,
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        mfa=True,
        now=now or datetime.now(UTC),
    )


def _authenticated_client(
    client: TestClient,
    settings: Settings,
    *,
    tenant_id: UUID,
    user_id: UUID,
    session_id: UUID,
    now: datetime | None = None,
) -> None:
    client.cookies.clear()
    client.cookies.set(
        ACCESS_COOKIE,
        _access_token(
            settings,
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
            now=now,
        ),
        path="/",
    )


def _session_revoked_at(engine: Engine, session_id: UUID) -> datetime | None:
    with engine.connect() as connection:
        value = connection.execute(
            text("SELECT revoked_at FROM session WHERE id = :id"), {"id": session_id}
        ).scalar_one()
    return value


def test_me_devuelve_usuario_tenant_y_roles_sin_secretos(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
) -> None:
    tenant_id = seeder.tenant(slug="clinica-demo")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_id, user_id, "professional")
    seeded = seeder.session(tenant_id, user_id)

    _authenticated_client(
        client,
        auth_settings,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=seeded.session_id,
    )
    response = client.get(ME_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "ana@example.test"
    assert body["tenant"]["slug"] == "clinica-demo"
    assert body["roles"] == ["professional"]
    assert body["mfa_enrolled"] is False
    for forbidden in ("password_hash", "mfa_secret", "refresh_token", "access_token"):
        assert forbidden not in response.text


def test_sin_cookie_o_con_sesion_revocada_responde_not_authenticated(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    revoked = seeder.session(tenant_id, user_id, revoked=True)

    client.cookies.clear()
    without_cookie = client.get(ME_URL)

    _authenticated_client(
        client,
        auth_settings,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=revoked.session_id,
    )
    with_revoked_session = client.get(ME_URL)

    for response in (without_cookie, with_revoked_session):
        assert response.status_code == 401
        assert response.json()["code"] == "not_authenticated"


def test_cookie_alterada_en_un_byte_es_401_y_no_500(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    seeded = seeder.session(tenant_id, user_id)
    token = _access_token(
        auth_settings, user_id=user_id, session_id=seeded.session_id, tenant_id=tenant_id
    )
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    client.cookies.clear()
    client.cookies.set(ACCESS_COOKIE, tampered, path="/")
    response = client.get(ME_URL)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_access_expirado_responde_session_expired_y_el_refresh_recupera(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    seeded = seeder.session(tenant_id, user_id)

    _authenticated_client(
        client,
        auth_settings,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=seeded.session_id,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    expired = client.get(ME_URL)

    assert expired.status_code == 401
    assert expired.json()["code"] == "session_expired"

    client.cookies.set(REFRESH_COOKIE, seeded.refresh_token, path="/api/v1/auth")
    refreshed = client.post(REFRESH_URL)

    assert refreshed.status_code == 200
    recovered = client.get(ME_URL)

    assert recovered.status_code == 200
    assert recovered.json()["user"]["id"] == str(user_id)
    assert recovered.json()["roles"] == ["professional"]


def test_membership_desactivada_despues_del_login_invalida_y_revoca(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    seeded = seeder.session(tenant_id, user_id)
    seeder.set_membership_active(tenant_id, user_id, activo=False)

    _authenticated_client(
        client,
        auth_settings,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=seeded.session_id,
    )
    response = client.get(ME_URL)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert _session_revoked_at(db_engine, seeded.session_id) is not None


def test_credencial_vieja_responde_credentials_changed_y_revoca_la_sesion(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user(credentials_version=1)
    seeder.membership(tenant_id, user_id, "professional")
    stale = seeder.session(tenant_id, user_id, credentials_version=0)

    _authenticated_client(
        client,
        auth_settings,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=stale.session_id,
    )
    response = client.get(ME_URL)

    assert response.status_code == 401
    assert response.json()["code"] == "credentials_changed"
    assert _session_revoked_at(db_engine, stale.session_id) is not None


def test_tenant_id_en_query_es_ignorado_y_no_lee_el_otro_tenant(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
) -> None:
    tenant_a = seeder.tenant(slug="clinica-a")
    tenant_b = seeder.tenant(slug="clinica-b")
    user_id = seeder.user()
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_b, user_id, "front_desk")
    seeded = seeder.session(tenant_a, user_id)

    _authenticated_client(
        client,
        auth_settings,
        tenant_id=tenant_a,
        user_id=user_id,
        session_id=seeded.session_id,
    )
    injected = client.get(ME_URL, params={"tenant_id": str(tenant_b)})

    assert injected.status_code == 200
    assert injected.json()["tenant"]["id"] == str(tenant_a)
    assert injected.json()["roles"] == ["professional"]

    # Un ``tenant_id`` inventado tampoco cambia el resultado.
    unknown = client.get(ME_URL, params={"tenant_id": str(uuid4())})

    assert unknown.status_code == 200
    assert unknown.json()["tenant"]["id"] == str(tenant_a)


def test_tenant_id_en_body_es_ignorado(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
) -> None:
    tenant_a = seeder.tenant(slug="clinica-a")
    tenant_b = seeder.tenant(slug="clinica-b")
    user_id = seeder.user()
    seeder.membership(tenant_a, user_id, "owner")
    seeder.membership(tenant_b, user_id, "professional")
    seeded = seeder.session(tenant_a, user_id)

    _authenticated_client(
        client,
        auth_settings,
        tenant_id=tenant_a,
        user_id=user_id,
        session_id=seeded.session_id,
    )
    injected = client.request(
        "GET",
        ME_URL,
        json={"tenant_id": str(tenant_b)},
    )

    assert injected.status_code == 200
    assert injected.json()["tenant"]["id"] == str(tenant_a)
    assert injected.json()["roles"] == ["owner"]
