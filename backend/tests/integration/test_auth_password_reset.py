"""Recuperación de contraseña con token opaco (tasks 6.1/6.2, design D7).

El reset no enumera tenants ni barre ``session``: invalida por credencial
(``user.credentials_version``) y deja que cada sesión falle en su próximo uso con
``401 credentials_changed``. El HTTP corre como ``odontologia_app``; las
aserciones directas usan el superusuario del contenedor.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.config import load_config
from app.domain.auth import service as auth_service
from app.domain.auth.passwords import verify_password
from app.domain.auth.tokens import hash_token
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "nueva-clave-larga-y-segura"
FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
APP_ROLE = "odontologia_app"


def _forgot(client: TestClient, email: str) -> str:
    response = client.post(FORGOT_URL, json={"email": email})
    assert response.status_code == 202, response.text
    token = response.json()["token"]
    assert isinstance(token, str)
    assert token
    return token


def _reset_rows(engine: Engine, user_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT user_id, token_hash, expires_at, used_at, created_at
                FROM password_reset_token WHERE user_id = :user_id
                ORDER BY created_at
                """
            ),
            {"user_id": user_id},
        ).mappings()
        return [dict(row) for row in rows]


def _reset_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(text("SELECT count(*) FROM password_reset_token")).scalar_one()
        )


def _user_row(engine: Engine, user_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT password_hash, credentials_version
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
                SELECT revoked_at, credentials_version, tenant_id
                FROM session WHERE id = :id
                """
            ),
            {"id": session_id},
        ).mappings().one()
        return dict(row)


def test_forgot_y_reset_invalidan_por_credencial_sin_barrer_sesiones(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    """S5.1: token hasheado a 30 min, consumo único y sesiones viejas sin credencial."""
    slug = f"reset-a-{uuid4().hex[:6]}"
    tenant_a = seeder.tenant(slug=slug)
    tenant_b = seeder.tenant(slug=f"reset-b-{uuid4().hex[:6]}")
    email = f"reset-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_b, user_id, "professional")

    login = client.post(
        LOGIN_URL, json={"tenant_slug": slug, "email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    session_a = _session_id_of(db_engine, user_id, tenant_a)
    other = seeder.session(tenant_b, user_id)

    before = datetime.now(UTC)
    token = _forgot(client, email)

    rows = _reset_rows(db_engine, user_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["token_hash"] == hash_token(token)
    assert token not in row["token_hash"]
    assert row["used_at"] is None
    assert timedelta(minutes=29) < row["expires_at"] - before < timedelta(minutes=31)

    reset = client.post(RESET_URL, json={"token": token, "new_password": NEW_PASSWORD})
    assert reset.status_code == 200, reset.text

    row = _reset_rows(db_engine, user_id)[0]
    assert row["used_at"] is not None
    user = _user_row(db_engine, user_id)
    assert user["credentials_version"] == 1
    assert user["password_hash"].startswith("$argon2id$")
    assert verify_password(NEW_PASSWORD, user["password_hash"])
    assert not verify_password(PASSWORD, user["password_hash"])

    # El reset no toca `session`: ni la de A ni la de B.
    assert _session_row(db_engine, session_a)["revoked_at"] is None
    assert _session_row(db_engine, other.session_id)["revoked_at"] is None
    assert _session_row(db_engine, other.session_id)["credentials_version"] == 0

    me = client.get(ME_URL)
    assert me.status_code == 401
    assert me.json()["code"] == "credentials_changed"
    assert _session_row(db_engine, session_a)["revoked_at"] is not None
    assert _session_row(db_engine, other.session_id)["revoked_at"] is None


def _session_id_of(engine: Engine, user_id: UUID, tenant_id: UUID) -> UUID:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT id FROM session WHERE user_id = :user_id AND tenant_id = :tenant_id"),
            {"user_id": user_id, "tenant_id": tenant_id},
        ).scalar_one()


def test_token_expirado_no_cambia_la_password(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S5.2: un token vencido no se consume ni cambia el hash."""
    email = f"vencido-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    original = _user_row(db_engine, user_id)["password_hash"]
    token = _forgot(client, email)

    with db_engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE password_reset_token
                   SET expires_at = now() - interval '1 second'
                 WHERE token_hash = :token_hash
                """
            ),
            {"token_hash": hash_token(token)},
        )

    response = client.post(RESET_URL, json={"token": token, "new_password": NEW_PASSWORD})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_or_expired_token"
    assert _user_row(db_engine, user_id)["password_hash"] == original
    assert _user_row(db_engine, user_id)["credentials_version"] == 0
    assert _reset_rows(db_engine, user_id)[0]["used_at"] is None


def test_token_reusado_no_cambia_la_password(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S5.2: el segundo reset con el mismo token es rechazado y no toca el hash."""
    email = f"reusado-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    token = _forgot(client, email)

    first = client.post(RESET_URL, json={"token": token, "new_password": NEW_PASSWORD})
    assert first.status_code == 200
    after_first = _user_row(db_engine, user_id)

    second = client.post(RESET_URL, json={"token": token, "new_password": "otra-clave-distinta-1"})

    assert second.status_code == 400
    assert second.json()["code"] == "invalid_or_expired_token"
    assert _user_row(db_engine, user_id) == after_first
    assert _user_row(db_engine, user_id)["credentials_version"] == 1


def test_token_inventado_no_cambia_la_password(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S5.2: un token que no corresponde a ningún hash responde 400."""
    email = f"inventado-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    original = _user_row(db_engine, user_id)

    response = client.post(
        RESET_URL, json={"token": "token-que-nunca-existio", "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_or_expired_token"
    assert _user_row(db_engine, user_id) == original


def test_email_inexistente_responde_igual_y_no_crea_token(
    secure_client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S5.3: en producción el body no distingue el email inexistente."""
    seeder.user(email=f"existe-{uuid4().hex[:8]}@example.test")
    before = _reset_count(db_engine)

    missing = secure_client.post(
        FORGOT_URL, json={"email": f"no-existe-{uuid4().hex[:8]}@example.test"}
    )

    assert missing.status_code == 202
    assert missing.json() == {}
    assert _reset_count(db_engine) == before


def test_production_no_expone_el_token_ni_lo_loguea(
    secure_client: TestClient,
    seeder: Any,
    db_engine: Engine,
    monkeypatch: Any,
    caplog: Any,
) -> None:
    """S5.4: fuera de desarrollo el token no viaja ni queda en logs."""
    email = f"produccion-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    sentinel = "sentinel-token-que-no-debe-filtrarse"
    monkeypatch.setattr(auth_service, "new_opaque_token", lambda: sentinel)
    caplog.set_level(logging.DEBUG)

    response = secure_client.post(FORGOT_URL, json={"email": email})

    assert response.status_code == 202
    assert "token" not in response.json()
    assert sentinel not in response.text
    assert sentinel not in caplog.text
    rows = _reset_rows(db_engine, user_id)
    assert len(rows) == 1
    assert rows[0]["token_hash"] == hash_token(sentinel)


def test_development_devuelve_el_token(
    client: TestClient,
    seeder: Any,
    auth_settings: Any,
    db_engine: Engine,
) -> None:
    """S5.4: en desarrollo el token sí se expone para probar el flujo."""
    email = f"desarrollo-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    dev_settings = load_config(
        {
            "ENVIRONMENT": "development",
            "DATABASE_URL": auth_settings.database_url,
            "REDIS_URL": auth_settings.redis_url,
            "SESSION_SECRET": "s" * 64,
            "JWT_REFRESH_SECRET": "j" * 64,
            "MFA_ENCRYPTION_KEY": "m" * 32,
            "COOKIE_SECURE": "false",
        }
    )

    with TestClient(create_app(dev_settings)) as dev_client:
        response = dev_client.post(FORGOT_URL, json={"email": email})

    assert response.status_code == 202
    assert isinstance(response.json()["token"], str)
    assert len(_reset_rows(db_engine, user_id)) == 1


def test_dos_resets_concurrentes_solo_uno_gana(
    client: TestClient, seeder: Any, db_engine: Engine
) -> None:
    """S5.5: el ``UPDATE ... WHERE used_at IS NULL`` arbitra una sola vez."""
    email = f"concurrente-{uuid4().hex[:8]}@example.test"
    user_id = seeder.user(email=email)
    token = _forgot(client, email)
    passwords = ["primera-clave-segura-123", "segunda-clave-segura-456"]

    barrier = threading.Barrier(2)
    app = client.app

    def _call(index: int) -> Any:
        worker = TestClient(app)
        barrier.wait(timeout=10)
        return worker.post(RESET_URL, json={"token": token, "new_password": passwords[index]})

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_call, index) for index in range(2)]
        responses = [future.result(timeout=30) for future in futures]

    assert sorted(response.status_code for response in responses) == [200, 400]
    winner = next(
        index for index, response in enumerate(responses) if response.status_code == 200
    )
    loser = responses[1 - winner]
    assert loser.json()["code"] == "invalid_or_expired_token"

    user = _user_row(db_engine, user_id)
    assert user["credentials_version"] == 1
    assert verify_password(passwords[winner], user["password_hash"])
    assert not verify_password(passwords[1 - winner], user["password_hash"])
    assert len(_reset_rows(db_engine, user_id)) == 1


def test_grants_de_reset_son_por_columna(db_engine: Engine) -> None:
    """El rol de app solo puede marcar ``used_at``; nunca reescribir el token."""
    with db_engine.connect() as connection:
        assert connection.exec_driver_sql(
            f"""
            SELECT has_column_privilege(
                '{APP_ROLE}', 'password_reset_token', 'used_at', 'UPDATE'
            )
            """
        ).scalar_one() is True
        assert connection.exec_driver_sql(
            f"""
            SELECT has_column_privilege(
                '{APP_ROLE}', 'password_reset_token', 'token_hash', 'UPDATE'
            )
            """
        ).scalar_one() is False
        assert connection.exec_driver_sql(
            f"SELECT has_table_privilege('{APP_ROLE}', 'password_reset_token', 'DELETE')"
        ).scalar_one() is False
