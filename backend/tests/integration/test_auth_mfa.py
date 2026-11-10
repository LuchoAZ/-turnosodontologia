"""MFA TOTP obligatorio para ``owner``/``billing`` (tasks 5.1 a 5.4, design D5).

El desafío vive en Redis (``GETDEL`` atómico, TTL 300) y viaja en una cookie
``HttpOnly`` con ``Path=/api/v1/auth/mfa``. El secreto TOTP se persiste cifrado
y nunca sale en ``/me`` ni en logs; los fallos de MFA cuentan para el lockout.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pyotp
from app.config import Settings
from app.core.crypto import decrypt_secret
from app.domain.auth.totp import generate_secret
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy.engine import Engine

PASSWORD = "correct-horse-battery-staple"
LOGIN_URL = "/api/v1/auth/login"
VERIFY_URL = "/api/v1/auth/mfa/verify"
ENROLL_START_URL = "/api/v1/auth/mfa/enroll/start"
ENROLL_CONFIRM_URL = "/api/v1/auth/mfa/enroll/confirm"
ME_URL = "/api/v1/auth/me"
MFA_COOKIE = "odontologia_mfa"
ACCESS_COOKIE = "odontologia_access"
REFRESH_COOKIE = "odontologia_refresh"
KEY_VERSION = 1


def _cookie_header(response: Any, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header
    return None


def _cookie_value(response: Any, name: str) -> str | None:
    header = _cookie_header(response, name)
    if header is None:
        return None
    return header.split(";", 1)[0].split("=", 1)[1]


def _challenge_id(response: Any) -> str:
    value = _cookie_value(response, MFA_COOKIE)
    assert value, "la respuesta no trae cookie de desafío MFA"
    return value


def _code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def _login(
    client: TestClient,
    *,
    tenant_slug: str,
    email: str,
    password: str = PASSWORD,
    extra: dict[str, Any] | None = None,
) -> Any:
    payload: dict[str, Any] = {
        "tenant_slug": tenant_slug,
        "email": email,
        "password": password,
    }
    payload.update(extra or {})
    return client.post(LOGIN_URL, json=payload)


def _verify(client: TestClient, code: str) -> Any:
    return client.post(VERIFY_URL, json={"code": code})


def _owner_with_secret(
    seeder: Any, settings: Settings, *, slug: str, email: str, secret: str
) -> tuple[UUID, UUID]:
    tenant_id = seeder.tenant(slug=slug)
    user_id = seeder.user(email=email)
    seeder.membership(tenant_id, user_id, "owner")
    seeder.enroll_mfa(
        user_id, secret=secret, encryption_key=settings.mfa_encryption_key
    )
    return tenant_id, user_id


def _user_row(engine: Engine, user_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT mfa_secret, mfa_secret_key_version, mfa_enrolled_at,
                       failed_login_count, lockout_strikes, locked_until,
                       last_totp_step, last_login_at, credentials_version
                FROM "user" WHERE id = :id
                """
            ),
            {"id": user_id},
        ).mappings().one()
    return dict(row)


def _session_row(engine: Engine, session_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT mfa_satisfied, last_used_step, revoked_at, tenant_id
                FROM session WHERE id = :id
                """
            ),
            {"id": session_id},
        ).mappings().one()
    return dict(row)


def _session_ids(engine: Engine, tenant_id: UUID) -> list[UUID]:
    with engine.connect() as connection:
        return [
            row[0]
            for row in connection.execute(
                text("SELECT id FROM session WHERE tenant_id = :t ORDER BY created_at"),
                {"t": tenant_id},
            ).all()
        ]


def _refresh_count(engine: Engine, session_id: UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT count(*) FROM refresh_token WHERE session_id = :id"),
                {"id": session_id},
            ).scalar_one()
        )


def _events(engine: Engine, since: datetime) -> list[tuple[str, UUID | None, dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tipo::text, user_id, detail FROM auth_event
                WHERE created_at >= :since ORDER BY id
                """
            ),
            {"since": since},
        ).all()
    return [(row[0], row[1], row[2]) for row in rows]


def _mfa_failures(engine: Engine, since: datetime, user_id: UUID) -> list[dict[str, Any]]:
    return [
        detail
        for tipo, event_user, detail in _events(engine, since)
        if tipo == "mfa_fail" and event_user == user_id
    ]


class _BrokenRedis:
    """Cliente que falla como Redis caído; ningún estado queda en memoria."""

    def getdel(self, *args: Any, **kwargs: Any) -> Any:
        raise RedisConnectionError("redis down")

    def set(self, *args: Any, **kwargs: Any) -> Any:
        raise RedisConnectionError("redis down")

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise RedisConnectionError("redis down")


def test_owner_enrolado_recibe_desafio_y_verify_emite_sesion(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    secret = generate_secret()
    tenant_id, user_id = _owner_with_secret(
        seeder, auth_settings, slug="clinica-mfa", email="owner@example.test", secret=secret
    )

    challenge = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")

    assert challenge.status_code == 403
    assert challenge.json()["code"] == "mfa_required"
    cookie = _cookie_header(challenge, MFA_COOKIE)
    assert cookie is not None
    assert "HttpOnly" in cookie
    assert "Path=/api/v1/auth/mfa" in cookie
    assert "Max-Age=300" in cookie
    assert _cookie_header(challenge, ACCESS_COOKIE) is None
    assert _cookie_header(challenge, REFRESH_COOKIE) is None

    sessions = _session_ids(db_engine, tenant_id)
    assert len(sessions) == 1
    pending = _session_row(db_engine, sessions[0])
    assert pending["mfa_satisfied"] is False
    assert pending["revoked_at"] is None
    assert _refresh_count(db_engine, sessions[0]) == 0

    code = _code(secret)
    verified = _verify(client, code)

    assert verified.status_code == 200
    assert verified.json()["user"]["email"] == "owner@example.test"
    assert verified.json()["roles"] == ["owner"]
    assert _cookie_header(verified, ACCESS_COOKIE) is not None
    assert _cookie_header(verified, REFRESH_COOKIE) is not None
    assert "Max-Age=0" in (_cookie_header(verified, MFA_COOKIE) or "")

    session = _session_row(db_engine, sessions[0])
    user = _user_row(db_engine, user_id)
    assert session["mfa_satisfied"] is True
    assert session["last_used_step"] is not None
    assert session["last_used_step"] == user["last_totp_step"]
    assert _refresh_count(db_engine, sessions[0]) == 1

    me = client.get(ME_URL)

    assert me.status_code == 200
    assert me.json()["mfa_enrolled"] is True
    for forbidden in ("mfa_secret", "password_hash", "otpauth://"):
        assert forbidden not in me.text


def test_codigo_invalido_no_emite_sesion_y_cuenta_para_el_lockout(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    started_at = datetime.now(UTC)
    secret = generate_secret()
    tenant_id, user_id = _owner_with_secret(
        seeder, auth_settings, slug="clinica-mfa", email="owner@example.test", secret=secret
    )
    _login(client, tenant_slug="clinica-mfa", email="owner@example.test")

    wrong = _verify(client, "000000")

    assert wrong.status_code == 401
    assert wrong.json()["code"] == "invalid_mfa_code"
    assert _cookie_header(wrong, ACCESS_COOKIE) is None
    assert _cookie_header(wrong, REFRESH_COOKIE) is None
    user = _user_row(db_engine, user_id)
    assert user["failed_login_count"] == 1
    assert user["last_totp_step"] is None
    assert _mfa_failures(db_engine, started_at, user_id) == [{"reason": "invalid_code"}]

    sessions = _session_ids(db_engine, tenant_id)
    assert len(sessions) == 1
    assert _refresh_count(db_engine, sessions[0]) == 0
    assert _session_row(db_engine, sessions[0])["mfa_satisfied"] is False

    # El desafío se consumió: el mismo challenge ya no sirve ni con código válido.
    assert _cookie_value(wrong, MFA_COOKIE) is None
    reused = _verify(client, _code(secret))
    assert reused.status_code == 401
    assert reused.json()["code"] == "mfa_step_up_expired"

    # Cuatro fallos más: el quinto bloquea la cuenta como cualquier lockout.
    client.cookies.clear()
    for attempt in range(2, 6):
        login = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")
        assert login.status_code == 403
        response = _verify(client, "000000")
        if attempt < 5:
            assert response.status_code == 401
            assert response.json()["code"] == "invalid_mfa_code"
        else:
            assert response.status_code == 423
            assert response.json()["code"] == "locked"
            assert int(response.headers["Retry-After"]) == 15 * 60

    user = _user_row(db_engine, user_id)
    assert user["failed_login_count"] == 5
    assert user["lockout_strikes"] == 1
    assert user["locked_until"] is not None
    assert len(_mfa_failures(db_engine, started_at, user_id)) == 5
    lockout_events = [
        detail
        for tipo, event_user, detail in _events(db_engine, started_at)
        if tipo == "lockout" and event_user == user_id
    ]
    assert len(lockout_events) == 1

    # Con la cuenta bloqueada, ni el password correcto genera desafío.
    client.cookies.clear()
    blocked = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")

    assert blocked.status_code == 423
    assert _cookie_header(blocked, MFA_COOKIE) is None


def test_codigo_reusado_se_rechaza_y_el_paso_no_retrocede(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    started_at = datetime.now(UTC)
    secret = generate_secret()
    _, user_id = _owner_with_secret(
        seeder, auth_settings, slug="clinica-mfa", email="owner@example.test", secret=secret
    )
    _login(client, tenant_slug="clinica-mfa", email="owner@example.test")
    code = _code(secret)
    assert _verify(client, code).status_code == 200
    accepted_step = _user_row(db_engine, user_id)["last_totp_step"]
    assert accepted_step is not None

    # Nuevo login (nuevo desafío) con el mismo código ya usado: replay rechazado.
    client.cookies.clear()
    assert _login(client, tenant_slug="clinica-mfa", email="owner@example.test").status_code == 403
    replay = _verify(client, code)

    assert replay.status_code == 401
    assert replay.json()["code"] == "invalid_mfa_code"
    user = _user_row(db_engine, user_id)
    assert user["last_totp_step"] == accepted_step
    assert _mfa_failures(db_engine, started_at, user_id) == [{"reason": "invalid_code"}]


def test_dos_verificaciones_concurrentes_del_mismo_codigo(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    secret = generate_secret()
    tenant_id, _ = _owner_with_secret(
        seeder, auth_settings, slug="clinica-mfa", email="owner@example.test", secret=secret
    )
    challenge = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")
    challenge_id = _challenge_id(challenge)
    code = _code(secret)
    barrier = threading.Barrier(2)
    app = client.app

    def _call(_: int) -> Any:
        worker = TestClient(app)
        barrier.wait(timeout=10)
        return worker.post(
            VERIFY_URL,
            json={"code": code},
            headers={"Cookie": f"{MFA_COOKIE}={challenge_id}"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_call, index) for index in range(2)]
        responses = [future.result(timeout=30) for future in futures]

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 401]
    rejected = next(response for response in responses if response.status_code == 401)
    assert rejected.json()["code"] == "mfa_step_up_expired"

    sessions = _session_ids(db_engine, tenant_id)
    assert len(sessions) == 1
    assert _session_row(db_engine, sessions[0])["mfa_satisfied"] is True
    assert _refresh_count(db_engine, sessions[0]) == 1


def test_owner_sin_secreto_enrola_y_confirma(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant(slug="clinica-mfa")
    user_id = seeder.user(email="owner@example.test")
    seeder.membership(tenant_id, user_id, "owner")

    login = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")

    assert login.status_code == 403
    assert login.json()["code"] == "mfa_enrollment_required"
    assert _challenge_id(login)
    assert _user_row(db_engine, user_id)["mfa_secret"] is None

    started = client.post(ENROLL_START_URL)

    assert started.status_code == 200
    body = started.json()
    secret = body["secret"]
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert secret in body["otpauth_uri"]
    assert _cookie_header(started, ACCESS_COOKIE) is None
    assert _cookie_header(started, REFRESH_COOKIE) is None
    assert _user_row(db_engine, user_id)["mfa_secret"] is None

    confirmed = client.post(ENROLL_CONFIRM_URL, json={"code": _code(secret)})

    assert confirmed.status_code == 200
    assert _cookie_header(confirmed, ACCESS_COOKIE) is not None
    assert _cookie_header(confirmed, REFRESH_COOKIE) is not None

    user = _user_row(db_engine, user_id)
    assert user["mfa_secret"] is not None
    assert secret not in user["mfa_secret"]
    assert user["mfa_secret_key_version"] == KEY_VERSION
    assert user["mfa_enrolled_at"] is not None
    assert (
        decrypt_secret(
            user["mfa_secret"],
            auth_settings.mfa_encryption_key,
            key_version=KEY_VERSION,
        )
        == secret
    )

    sessions = _session_ids(db_engine, tenant_id)
    assert len(sessions) == 1
    assert _session_row(db_engine, sessions[0])["mfa_satisfied"] is True
    assert _refresh_count(db_engine, sessions[0]) == 1


def test_front_desk_entra_directo_y_skip_mfa_no_sirve(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant(slug="clinica-mfa")
    desk = seeder.user(email="desk@example.test")
    seeder.membership(tenant_id, desk, "front_desk")

    direct = _login(client, tenant_slug="clinica-mfa", email="desk@example.test")

    assert direct.status_code == 200
    assert _cookie_header(direct, MFA_COOKIE) is None
    assert direct.json()["mfa_enrolled"] is False
    desk_session = _session_ids(db_engine, tenant_id)[0]
    assert _session_row(db_engine, desk_session)["mfa_satisfied"] is True

    client.cookies.clear()
    secret = generate_secret()
    _, owner_id = _owner_with_secret(
        seeder, auth_settings, slug="clinica-mfa-2", email="owner@example.test", secret=secret
    )
    skipped = _login(
        client,
        tenant_slug="clinica-mfa-2",
        email="owner@example.test",
        extra={"skip_mfa": True},
    )

    assert skipped.status_code == 403
    assert skipped.json()["code"] == "mfa_required"
    assert _cookie_header(skipped, ACCESS_COOKIE) is None
    assert _user_row(db_engine, owner_id)["failed_login_count"] == 0


def test_desafio_de_un_solo_uso_y_expirado(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
) -> None:
    secret = generate_secret()
    _owner_with_secret(
        seeder, auth_settings, slug="clinica-mfa", email="owner@example.test", secret=secret
    )
    login = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")
    challenge_id = _challenge_id(login)

    # Desafío vencido: se borra la clave como haría el TTL de Redis.
    client.app.state.redis.delete(f"auth:mfa:challenge:{challenge_id}")
    expired = _verify(client, _code(secret))

    assert expired.status_code == 401
    assert expired.json()["code"] == "mfa_step_up_expired"
    assert _cookie_header(expired, ACCESS_COOKIE) is None

    client.cookies.clear()
    second = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")
    second_challenge = _challenge_id(second)
    code = _code(secret)

    assert _verify(client, code).status_code == 200

    # Segundo uso del mismo desafío (aunque el código siga siendo válido).
    again = client.post(
        VERIFY_URL,
        json={"code": code},
        headers={"Cookie": f"{MFA_COOKIE}={second_challenge}"},
    )

    assert again.status_code == 401
    assert again.json()["code"] == "mfa_step_up_expired"
    assert _cookie_header(again, ACCESS_COOKIE) is None


def test_sin_redis_el_step_up_falla_cerrado(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    secret = generate_secret()
    tenant_id, _ = _owner_with_secret(
        seeder, auth_settings, slug="clinica-mfa", email="owner@example.test", secret=secret
    )
    original = client.app.state.redis
    client.app.state.redis = _BrokenRedis()

    login = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")

    assert login.status_code == 503
    assert login.json()["code"] == "mfa_unavailable"
    assert _cookie_header(login, MFA_COOKIE) is None
    assert _cookie_header(login, ACCESS_COOKIE) is None
    assert _cookie_header(login, REFRESH_COOKIE) is None
    assert _session_ids(db_engine, tenant_id) == []

    client.app.state.redis = original
    challenge = _login(client, tenant_slug="clinica-mfa", email="owner@example.test")
    assert challenge.status_code == 403

    client.app.state.redis = _BrokenRedis()
    verify = _verify(client, _code(secret))

    assert verify.status_code == 503
    assert verify.json()["code"] == "mfa_unavailable"
    assert _cookie_header(verify, ACCESS_COOKIE) is None
    pending_session = _challenge_session(db_engine, tenant_id)
    assert _refresh_count(db_engine, pending_session) == 0


def _challenge_session(engine: Engine, tenant_id: UUID) -> UUID:
    sessions = _session_ids(engine, tenant_id)
    assert len(sessions) == 1
    return sessions[0]


def test_el_secreto_cifrado_no_aparece_en_logs(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
    caplog: Any,
) -> None:
    caplog.set_level("DEBUG")
    tenant_id = seeder.tenant(slug="clinica-mfa")
    user_id = seeder.user(email="owner@example.test")
    seeder.membership(tenant_id, user_id, "owner")

    assert _login(client, tenant_slug="clinica-mfa", email="owner@example.test").status_code == 403
    started = client.post(ENROLL_START_URL)
    secret = started.json()["secret"]
    assert client.post(ENROLL_CONFIRM_URL, json={"code": _code(secret)}).status_code == 200

    assert secret not in caplog.text
    assert "otpauth://" not in caplog.text

    # El evento de auditoría tampoco lleva el secreto ni el otpauth.
    with db_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT detail FROM auth_event WHERE user_id = :id"),
            {"id": user_id},
        ).all()
    serialized = json.dumps([row[0] for row in rows])
    assert secret not in serialized
    assert "otpauth" not in serialized
