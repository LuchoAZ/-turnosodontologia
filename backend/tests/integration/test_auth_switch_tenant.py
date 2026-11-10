"""Cambio de tenant con re-emisión de sesión (tasks 7.1/7.3, design D4.3/D5).

``switch-tenant`` es la única excepción a "el tenant sale de la sesión": lee el
destino del body y lo valida contra una membership activa. Un destino sin
membership no toca A; un destino con ``owner``/``billing`` exige step-up y A
sigue vigente hasta que el segundo factor complete.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pyotp
from app.domain.auth.totp import generate_secret
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

PASSWORD = "correct-horse-battery-staple"
LOGIN_URL = "/api/v1/auth/login"
SWITCH_URL = "/api/v1/auth/switch-tenant"
VERIFY_URL = "/api/v1/auth/mfa/verify"
ENROLL_START_URL = "/api/v1/auth/mfa/enroll/start"
ENROLL_CONFIRM_URL = "/api/v1/auth/mfa/enroll/confirm"
REFRESH_URL = "/api/v1/auth/refresh"
ME_URL = "/api/v1/auth/me"
MFA_COOKIE = "odontologia_mfa"
ACCESS_COOKIE = "odontologia_access"


def _cookie_header(response: Any, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header
    return None


def _challenge_id(response: Any) -> str:
    header = _cookie_header(response, MFA_COOKIE)
    assert header is not None, "la respuesta no trae cookie de desafío MFA"
    return header.split(";", 1)[0].split("=", 1)[1]


def _code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def _login(client: TestClient, slug: str, email: str) -> Any:
    return client.post(
        LOGIN_URL, json={"tenant_slug": slug, "email": email, "password": PASSWORD}
    )


def _sessions_of(engine: Engine, user_id: UUID, tenant_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id, mfa_satisfied, revoked_at, expires_at
                FROM session WHERE user_id = :user_id AND tenant_id = :tenant_id
                ORDER BY created_at
                """
            ),
            {"user_id": user_id, "tenant_id": tenant_id},
        ).mappings()
        return [dict(row) for row in rows]


def _families(engine: Engine, session_id: UUID) -> set[UUID]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT family_id FROM refresh_token WHERE session_id = :id"),
            {"id": session_id},
        ).scalars()
        return set(rows)


def _refresh_states(engine: Engine, session_id: UUID) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT estado::text FROM refresh_token WHERE session_id = :id"),
            {"id": session_id},
        ).scalars()
        return list(rows)


def test_switch_reemite_sesion_y_me_ignora_el_tenant_del_query(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S6.1/S6.3/S6.4: A queda revocada, B nace con family nueva y /me no lee B."""
    slug_a = f"switch-a-{uuid4().hex[:6]}"
    slug_b = f"switch-b-{uuid4().hex[:6]}"
    tenant_a = seeder.tenant(slug=slug_a)
    tenant_b = seeder.tenant(slug=slug_b)
    email = f"switch-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_b, user_id, "professional")

    assert _login(client, slug_a, email).status_code == 200
    session_a = _sessions_of(db_engine, user_id, tenant_a)[0]

    me = client.get(ME_URL, params={"tenant_id": str(tenant_b)})
    assert me.status_code == 200
    assert me.json()["tenant"]["slug"] == slug_a
    assert me.json()["roles"] == ["professional"]

    switched = client.post(SWITCH_URL, json={"tenant_slug": slug_b})

    assert switched.status_code == 200, switched.text
    assert switched.json()["tenant"]["slug"] == slug_b
    assert switched.json()["roles"] == ["professional"]
    assert _cookie_header(switched, ACCESS_COOKIE) is not None

    assert _sessions_of(db_engine, user_id, tenant_a)[0]["revoked_at"] is not None
    sessions_b = _sessions_of(db_engine, user_id, tenant_b)
    assert len(sessions_b) == 1
    assert sessions_b[0]["mfa_satisfied"] is True
    assert sessions_b[0]["revoked_at"] is None
    assert _families(db_engine, session_a["id"]).isdisjoint(
        _families(db_engine, sessions_b[0]["id"])
    )

    after = client.get(ME_URL)
    assert after.status_code == 200
    assert after.json()["tenant"]["slug"] == slug_b
    assert after.json()["roles"] == ["professional"]

    # La cookie rotada sigue siendo un refresh válido de la sesión de B.
    assert client.post(REFRESH_URL).status_code == 200


def test_switch_sin_membership_no_toca_la_sesion_de_a(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S6.2/S6.4: sin membership activa el switch no crea filas ni revoca A."""
    slug_a = f"sin-memb-a-{uuid4().hex[:6]}"
    tenant_a = seeder.tenant(slug=slug_a)
    slug_c = f"sin-memb-c-{uuid4().hex[:6]}"
    tenant_c = seeder.tenant(slug=slug_c)
    slug_d = f"sin-memb-d-{uuid4().hex[:6]}"
    tenant_d = seeder.tenant(slug=slug_d)
    email = f"sin-memb-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_d, user_id, "professional", activo=False)

    assert _login(client, slug_a, email).status_code == 200
    session_a = _sessions_of(db_engine, user_id, tenant_a)[0]

    for slug in (slug_c, slug_d):
        response = client.post(SWITCH_URL, json={"tenant_slug": slug})
        assert response.status_code == 403
        assert response.json()["code"] == "tenant_not_available"

    me = client.get(ME_URL)
    assert me.status_code == 200
    assert me.json()["tenant"]["slug"] == slug_a
    assert client.post(REFRESH_URL).status_code == 200
    assert _sessions_of(db_engine, user_id, tenant_c) == []
    assert _sessions_of(db_engine, user_id, tenant_d) == []
    assert _families(db_engine, session_a["id"])  # A conserva su familia


def test_switch_a_owner_exige_step_up_y_conserva_a_hasta_verificar(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S6.5: B nace pendiente, A sigue vigente y el step-up recién ahí la revoca."""
    slug_a = f"owner-a-{uuid4().hex[:6]}"
    slug_b = f"owner-b-{uuid4().hex[:6]}"
    tenant_a = seeder.tenant(slug=slug_a)
    tenant_b = seeder.tenant(slug=slug_b)
    email = f"owner-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    secret = generate_secret()
    seeder.enroll_mfa(user_id, secret=secret, encryption_key="m" * 32)
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_b, user_id, "owner")

    assert _login(client, slug_a, email).status_code == 200
    session_a = _sessions_of(db_engine, user_id, tenant_a)[0]

    step_up = client.post(SWITCH_URL, json={"tenant_slug": slug_b})

    assert step_up.status_code == 403
    assert step_up.json()["code"] == "mfa_required"
    assert _cookie_header(step_up, MFA_COOKIE) is not None
    assert _cookie_header(step_up, ACCESS_COOKIE) is None
    assert client.get(ME_URL).json()["tenant"]["slug"] == slug_a

    pending = _sessions_of(db_engine, user_id, tenant_b)
    assert len(pending) == 1
    assert pending[0]["mfa_satisfied"] is False
    assert _families(db_engine, pending[0]["id"]) == set()

    verified = client.post(VERIFY_URL, json={"code": _code(secret)})

    assert verified.status_code == 200, verified.text
    assert verified.json()["tenant"]["slug"] == slug_b
    assert verified.json()["roles"] == ["owner"]
    assert _sessions_of(db_engine, user_id, tenant_a)[0]["revoked_at"] is not None
    sessions_b = _sessions_of(db_engine, user_id, tenant_b)
    assert len(sessions_b) == 1
    assert sessions_b[0]["mfa_satisfied"] is True
    assert sessions_b[0]["revoked_at"] is None
    assert _families(db_engine, sessions_b[0]["id"]) != _families(
        db_engine, session_a["id"]
    )
    assert client.get(ME_URL).json()["tenant"]["slug"] == slug_b


def test_switch_a_owner_sin_secreto_enrola_antes_de_emitir(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S6.5: sin secreto el destino exige alta, no una simple verificación."""
    slug_a = f"enroll-a-{uuid4().hex[:6]}"
    slug_b = f"enroll-b-{uuid4().hex[:6]}"
    tenant_a = seeder.tenant(slug=slug_a)
    tenant_b = seeder.tenant(slug=slug_b)
    email = f"enroll-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_b, user_id, "billing")

    assert _login(client, slug_a, email).status_code == 200

    step_up = client.post(SWITCH_URL, json={"tenant_slug": slug_b})

    assert step_up.status_code == 403
    assert step_up.json()["code"] == "mfa_enrollment_required"
    assert _cookie_header(step_up, ACCESS_COOKIE) is None

    start = client.post(ENROLL_START_URL)
    assert start.status_code == 200
    secret = start.json()["secret"]

    confirmed = client.post(ENROLL_CONFIRM_URL, json={"code": _code(secret)})

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["tenant"]["slug"] == slug_b
    assert confirmed.json()["roles"] == ["billing"]
    assert confirmed.json()["mfa_enrolled"] is True
    assert _sessions_of(db_engine, user_id, tenant_b)[0]["mfa_satisfied"] is True


def test_step_up_de_switch_vencido_o_fallido_no_emite_sesion_b(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S6.6: el desafío de un solo uso no deja sesión usable de B ni revoca A."""
    slug_a = f"expira-a-{uuid4().hex[:6]}"
    slug_b = f"expira-b-{uuid4().hex[:6]}"
    tenant_a = seeder.tenant(slug=slug_a)
    tenant_b = seeder.tenant(slug=slug_b)
    email = f"expira-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    secret = generate_secret()
    seeder.enroll_mfa(user_id, secret=secret, encryption_key="m" * 32)
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_b, user_id, "owner")

    assert _login(client, slug_a, email).status_code == 200
    session_a = _sessions_of(db_engine, user_id, tenant_a)[0]

    step_up = client.post(SWITCH_URL, json={"tenant_slug": slug_b})
    assert step_up.status_code == 403
    challenge = _challenge_id(step_up)
    app_redis = client.app.state.redis
    assert app_redis.delete(f"auth:mfa:challenge:{challenge}") == 1

    expired = client.post(VERIFY_URL, json={"code": _code(secret)})

    assert expired.status_code == 401
    assert expired.json()["code"] == "mfa_step_up_expired"
    assert client.get(ME_URL).json()["tenant"]["slug"] == slug_a
    assert _no_usable_session_b(db_engine, user_id, tenant_b)

    retry = client.post(SWITCH_URL, json={"tenant_slug": slug_b})
    assert retry.status_code == 403
    valid = _code(secret)
    wrong = "000000" if valid != "000000" else "111111"

    failed = client.post(VERIFY_URL, json={"code": wrong})

    assert failed.status_code == 401
    assert failed.json()["code"] == "invalid_mfa_code"
    assert client.get(ME_URL).json()["tenant"]["slug"] == slug_a
    assert _no_usable_session_b(db_engine, user_id, tenant_b)
    assert _sessions_of(db_engine, user_id, tenant_a)[0]["revoked_at"] is None
    assert "revocado" not in _refresh_states(db_engine, session_a["id"])


def _no_usable_session_b(engine: Engine, user_id: UUID, tenant_id: UUID) -> bool:
    with engine.connect() as connection:
        count = connection.execute(
            text(
                """
                SELECT count(*) FROM session
                WHERE user_id = :user_id AND tenant_id = :tenant_id
                  AND mfa_satisfied AND revoked_at IS NULL
                """
            ),
            {"user_id": user_id, "tenant_id": tenant_id},
        ).scalar_one()
    return int(count) == 0
