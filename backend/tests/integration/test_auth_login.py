"""Contrato HTTP del login (tasks 3.1/3.9, design D3 y D9).

El HTTP corre como ``odontologia_app``; las aserciones directas sobre ``session``
y ``auth_event`` usan el superusuario del contenedor (el rol de app no tiene
``SELECT`` sobre ``auth_event``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

PASSWORD = "correct-horse-battery-staple"
LOGIN_URL = "/api/v1/auth/login"


def _cookies(response: Any) -> list[str]:
    return response.headers.get_list("set-cookie")


def _session_tenants(engine: Engine) -> list[UUID]:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT tenant_id FROM session")).scalars()
    return list(rows)


def _events_since(
    engine: Engine, since: datetime
) -> list[tuple[str, UUID | None, UUID | None, dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tipo::text, user_id, tenant_id, detail
                FROM auth_event WHERE created_at >= :since
                """
            ),
            {"since": since},
        ).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows]


def test_login_valido_emite_cookies_http_only_y_sesion_en_el_tenant(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant(slug="clinica-demo")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_id, user_id, "professional")

    response = client.post(
        LOGIN_URL,
        json={
            "tenant_slug": "clinica-demo",
            "email": "ana@example.test",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "ana@example.test"
    assert body["tenant"]["slug"] == "clinica-demo"
    assert body["roles"] == ["professional"]
    assert body["mfa_enrolled"] is False

    for forbidden in ("password_hash", "mfa_secret", "refresh_token", "access_token"):
        assert forbidden not in response.text

    cookies = _cookies(response)
    access = next(cookie for cookie in cookies if cookie.startswith("odontologia_access="))
    refresh = next(cookie for cookie in cookies if cookie.startswith("odontologia_refresh="))
    assert "HttpOnly" in access
    assert "SameSite=lax" in access or "SameSite=Lax" in access
    assert "Path=/" in access
    assert "Secure" not in access
    assert "HttpOnly" in refresh
    assert "Path=/api/v1/auth" in refresh
    assert "Secure" not in refresh

    assert _session_tenants(db_engine) == [tenant_id]


def test_las_cinco_formas_de_fallo_son_indistinguibles(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    started_at = datetime.now(UTC)
    tenant_id = seeder.tenant(slug="clinica-a")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_id, user_id, "professional")
    inactive_user = seeder.user(email="inactivo@example.test", activo=False)
    seeder.membership(tenant_id, inactive_user, "professional")
    inactive_membership_user = seeder.user(email="sin-membership@example.test")
    seeder.membership(tenant_id, inactive_membership_user, "professional", activo=False)

    cases = [
        {"tenant_slug": "clinica-a", "email": "ana@example.test", "password": "wrong-password"},
        {"tenant_slug": "clinica-a", "email": "nadie@example.test", "password": PASSWORD},
        {"tenant_slug": "clinica-a", "email": "inactivo@example.test", "password": PASSWORD},
        {"tenant_slug": "clinica-a", "email": "sin-membership@example.test", "password": PASSWORD},
        {"tenant_slug": "no-existe", "email": "ana@example.test", "password": PASSWORD},
    ]

    responses = [client.post(LOGIN_URL, json=payload) for payload in cases]

    first = responses[0].json()
    for response in responses:
        assert response.status_code == 401
        assert response.json() == first
        assert first["code"] == "invalid_credentials"
        assert "set-cookie" not in response.headers

    assert _session_tenants(db_engine) == []
    failures = [event for event in _events_since(db_engine, started_at) if event[0] == "login_fail"]
    assert len(failures) == 5


def test_con_memberships_en_a_y_b_el_login_queda_en_el_tenant_pedido(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_a = seeder.tenant(slug="clinica-a")
    tenant_b = seeder.tenant(slug="clinica-b")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_b, user_id, "front_desk")

    response = client.post(
        LOGIN_URL,
        json={"tenant_slug": "clinica-b", "email": "ana@example.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["tenant"]["slug"] == "clinica-b"
    assert response.json()["roles"] == ["front_desk"]

    tenants = _session_tenants(db_engine)
    assert tenants == [tenant_b]
    assert tenant_a not in set(tenants)


def test_un_tenant_suspendido_no_permite_iniciar_sesion(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    started_at = datetime.now(UTC)
    tenant_id = seeder.tenant(slug="clinica-suspendida", estado="suspended")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_id, user_id, "professional")

    response = client.post(
        LOGIN_URL,
        json={
            "tenant_slug": "clinica-suspendida",
            "email": "ana@example.test",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "tenant_not_available"
    assert "set-cookie" not in response.headers
    assert _session_tenants(db_engine) == []

    events = _events_since(db_engine, started_at)
    suspended = [event for event in events if event[2] == tenant_id]
    assert len(suspended) == 1
    assert suspended[0][3]["reason"] == "tenant_suspended"


def _login_payload() -> dict[str, str]:
    return {
        "tenant_slug": "clinica-cookies",
        "email": "ana@example.test",
        "password": PASSWORD,
    }


def _assert_cookie_attributes(access: str, refresh: str, *, secure: bool) -> None:
    for header in (access, refresh):
        assert "HttpOnly" in header
        assert "SameSite=lax" in header or "SameSite=Lax" in header
    assert "Path=/" in access
    assert "Path=/api/v1/auth" in refresh
    assert ("Secure" in access) is secure
    assert ("Secure" in refresh) is secure


def test_las_cookies_llevan_secure_en_produccion_y_no_en_test(
    client: TestClient,
    secure_client: TestClient,
    seeder: Any,
) -> None:
    tenant_id = seeder.tenant(slug="clinica-cookies")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_id, user_id, "professional")

    test_response = client.post(LOGIN_URL, json=_login_payload())
    production_response = secure_client.post(LOGIN_URL, json=_login_payload())

    assert test_response.status_code == 200
    assert production_response.status_code == 200

    def _headers(response: Any) -> tuple[str, str]:
        cookies = response.headers.get_list("set-cookie")
        access = next(c for c in cookies if c.startswith("odontologia_access="))
        refresh = next(c for c in cookies if c.startswith("odontologia_refresh="))
        return access, refresh

    _assert_cookie_attributes(*_headers(test_response), secure=False)
    _assert_cookie_attributes(*_headers(production_response), secure=True)
