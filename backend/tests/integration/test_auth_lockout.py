"""Lockout progresivo y auditoría mínima (task 4.1, RN-AU-05, design D6).

El estado vive en ``user`` (``failed_login_count``, ``lockout_strikes``,
``locked_until``): no depende de Redis. La verificación de ``LOCKED`` ocurre
antes de comparar el password, así una cuenta bloqueada no filtra si la
credencial era correcta.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

PASSWORD = "correct-horse-battery-staple"
LOGIN_URL = "/api/v1/auth/login"


def _login(
    client: TestClient,
    *,
    tenant_slug: str,
    email: str,
    password: str = PASSWORD,
) -> Any:
    return client.post(
        LOGIN_URL,
        json={"tenant_slug": tenant_slug, "email": email, "password": password},
    )


def _user_state(engine: Engine, user_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT failed_login_count, lockout_strikes, locked_until,
                       last_lockout_at, last_login_at
                FROM "user" WHERE id = :id
                """
            ),
            {"id": user_id},
        ).mappings().one()
    return dict(row)


def _force_lockout_expiry(engine: Engine, user_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE "user" SET locked_until = now() - interval '1 second'
                WHERE id = :id
                """
            ),
            {"id": user_id},
        )


def _force_locked(engine: Engine, user_id: UUID, *, minutes: int = 15) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE "user"
                   SET failed_login_count = 5, lockout_strikes = 1,
                       locked_until = now() + make_interval(mins => :minutes),
                       last_lockout_at = now()
                 WHERE id = :id
                """
            ),
            {"id": user_id, "minutes": minutes},
        )


def _events(
    engine: Engine, since: datetime
) -> list[tuple[str, UUID | None, UUID | None, dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tipo::text, user_id, tenant_id, detail
                FROM auth_event WHERE created_at >= :since ORDER BY id
                """
            ),
            {"since": since},
        ).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows]


def _sessions_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM session")).scalar_one())


def _assert_locked_for(response: Any, *, minutes: int) -> None:
    assert response.status_code == 423
    assert response.json()["code"] == "locked"
    expected = minutes * 60
    assert int(response.headers["Retry-After"]) in {expected, expected - 1}


def test_cuatro_fallos_no_bloquean_y_el_quinto_bloquea(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    started_at = datetime.now(UTC)
    tenant_id = seeder.tenant(slug="clinica-a")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_id, user_id, "professional")

    for expected in range(1, 5):
        response = _login(
            client, tenant_slug="clinica-a", email="ana@example.test", password="mala"
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_credentials"
        assert "set-cookie" not in response.headers
        state = _user_state(db_engine, user_id)
        assert state["failed_login_count"] == expected
        assert state["locked_until"] is None

    fifth = _login(client, tenant_slug="clinica-a", email="ana@example.test", password="mala")

    _assert_locked_for(fifth, minutes=15)
    assert "set-cookie" not in fifth.headers

    state = _user_state(db_engine, user_id)
    assert state["failed_login_count"] == 5
    assert state["lockout_strikes"] == 1
    remaining = state["locked_until"] - datetime.now(UTC)
    assert timedelta(minutes=14) < remaining <= timedelta(minutes=15, seconds=5)
    assert state["last_lockout_at"] is not None
    assert _sessions_count(db_engine) == 0

    events = [event for event in _events(db_engine, started_at) if event[1] == user_id]
    kinds = [event[0] for event in events]
    assert kinds.count("login_fail") == 4
    assert kinds.count("lockout") == 1
    serialized = json.dumps([event[3] for event in events])
    assert PASSWORD not in serialized
    assert "mala" not in serialized


def test_credenciales_correctas_durante_el_bloqueo_no_emiten_sesion(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant(slug="clinica-a")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_id, user_id, "professional")
    _force_locked(db_engine, user_id)
    before = _user_state(db_engine, user_id)

    response = _login(client, tenant_slug="clinica-a", email="ana@example.test")

    _assert_locked_for(response, minutes=15)
    assert "set-cookie" not in response.headers
    assert _sessions_count(db_engine) == 0
    after = _user_state(db_engine, user_id)
    assert after["last_login_at"] == before["last_login_at"]
    assert after["failed_login_count"] == 5


def test_el_bloqueo_expira_y_el_login_correcto_resetea_contadores(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant(slug="clinica-a")
    user_id = seeder.user(email="ana@example.test")
    seeder.membership(tenant_id, user_id, "professional")
    _force_locked(db_engine, user_id)
    _force_lockout_expiry(db_engine, user_id)

    response = _login(client, tenant_slug="clinica-a", email="ana@example.test")

    assert response.status_code == 200
    state = _user_state(db_engine, user_id)
    assert state["failed_login_count"] == 0
    assert state["lockout_strikes"] == 0
    assert state["locked_until"] is None
    assert state["last_login_at"] is not None

    next_failure = _login(
        client, tenant_slug="clinica-a", email="ana@example.test", password="mala"
    )

    assert next_failure.status_code == 401
    assert _user_state(db_engine, user_id)["failed_login_count"] == 1


def test_la_segunda_racha_duplica_la_ventana_y_el_lockout_es_por_cuenta(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_a = seeder.tenant(slug="clinica-a")
    tenant_c = seeder.tenant(slug="clinica-c")
    ana = seeder.user(email="ana@example.test")
    seeder.membership(tenant_a, ana, "professional")
    seeder.membership(tenant_c, ana, "front_desk")
    beto = seeder.user(email="beto@example.test")
    seeder.membership(tenant_a, beto, "professional")

    for _ in range(5):
        _login(client, tenant_slug="clinica-a", email="ana@example.test", password="mala")
    assert _user_state(db_engine, ana)["lockout_strikes"] == 1

    _force_lockout_expiry(db_engine, ana)
    for _ in range(5):
        second = _login(
            client, tenant_slug="clinica-a", email="ana@example.test", password="mala"
        )

    _assert_locked_for(second, minutes=30)
    state = _user_state(db_engine, ana)
    assert state["lockout_strikes"] == 2
    remaining = state["locked_until"] - datetime.now(UTC)
    assert timedelta(minutes=29) < remaining <= timedelta(minutes=30, seconds=5)

    # Mientras A está bloqueado, B del mismo tenant entra.
    other_user = _login(client, tenant_slug="clinica-a", email="beto@example.test")

    assert other_user.status_code == 200

    # El bloqueo es de la cuenta: A tampoco entra en otro tenant donde tiene membership.
    other_tenant = _login(client, tenant_slug="clinica-c", email="ana@example.test")

    _assert_locked_for(other_tenant, minutes=30)

    # Un login exitoso posterior devuelve la racha a cero.
    _force_lockout_expiry(db_engine, ana)
    recovered = _login(client, tenant_slug="clinica-a", email="ana@example.test")

    assert recovered.status_code == 200
    assert _user_state(db_engine, ana)["lockout_strikes"] == 0
