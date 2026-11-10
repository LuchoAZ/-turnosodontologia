"""Aislamiento cross-tenant por HTTP con el rol de app (task 3.10, S8.6).

El HTTP corre como ``odontologia_app`` (no superusuario): si una consulta se
escapara de la RLS, el propio test lo vería. Las credenciales mezcladas (access
de una sesión con refresh de otra) se rechazan sin revocar nada, y cada sesión
legítima sigue funcionando.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.config import Settings
from app.core.security import ACCESS_COOKIE, REFRESH_COOKIE, create_access_token
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

ME_URL = "/api/v1/auth/me"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"


@dataclass(frozen=True)
class TenantSession:
    tenant_id: UUID
    user_id: UUID
    session_id: UUID
    family_id: UUID
    refresh_token: str
    access_token: str


def _tenant_session(
    client: TestClient,
    settings: Settings,
    seeder: Any,
    *,
    slug: str,
    email: str,
    rol: str = "professional",
) -> TenantSession:
    tenant_id = seeder.tenant(slug=slug)
    user_id = seeder.user(email=email)
    seeder.membership(tenant_id, user_id, rol)
    seeded = seeder.session(tenant_id, user_id)
    access = create_access_token(
        settings,
        user_id=user_id,
        session_id=seeded.session_id,
        tenant_id=tenant_id,
        mfa=True,
        now=datetime.now(UTC),
    )
    return TenantSession(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=seeded.session_id,
        family_id=seeded.family_id,
        refresh_token=seeded.refresh_token,
        access_token=access,
    )


def _raw(client: TestClient, method: str, url: str, cookie: str, **kwargs: Any) -> Any:
    return client.request(method, url, headers={"Cookie": cookie}, **kwargs)


def _session_state(engine: Engine, session_id: UUID) -> tuple[Any, int]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT revoked_at, credentials_version FROM session WHERE id = :id"),
            {"id": session_id},
        ).one()
    return row[0], row[1]


def _family_state(engine: Engine, family_id: UUID) -> dict[str, int]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT estado::text, count(*) FROM refresh_token
                WHERE family_id = :f GROUP BY 1
                """
            ),
            {"f": family_id},
        ).all()
    return dict(rows)


def _session_count(engine: Engine, tenant_id: UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT count(*) FROM session WHERE tenant_id = :t"), {"t": tenant_id}
            ).scalar_one()
        )


def test_la_sesion_de_a_no_lee_ni_cierra_la_de_b(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    a = _tenant_session(
        client, auth_settings, seeder, slug="clinica-a", email="ana@example.test"
    )
    b = _tenant_session(
        client, auth_settings, seeder, slug="clinica-b", email="beto@example.test"
    )

    injected = _raw(
        client,
        "GET",
        f"{ME_URL}?tenant_id={b.tenant_id}",
        f"{ACCESS_COOKIE}={a.access_token}",
        json={"tenant_id": str(b.tenant_id)},
    )

    assert injected.status_code == 200
    assert injected.json()["tenant"]["id"] == str(a.tenant_id)
    assert injected.json()["user"]["id"] == str(a.user_id)
    assert _session_state(db_engine, b.session_id)[0] is None
    assert _session_count(db_engine, b.tenant_id) == 1

    closed = _raw(
        client,
        "POST",
        LOGOUT_URL,
        f"{ACCESS_COOKIE}={a.access_token}; {REFRESH_COOKIE}={a.refresh_token}",
    )

    assert closed.status_code == 204
    assert _session_state(db_engine, a.session_id)[0] is not None
    assert _session_state(db_engine, b.session_id)[0] is None

    still_valid = _raw(client, "POST", REFRESH_URL, f"{REFRESH_COOKIE}={b.refresh_token}")

    assert still_valid.status_code == 200
    assert _session_state(db_engine, b.session_id)[0] is None


def test_credenciales_mezcladas_se_rechazan_sin_revocar_ni_rotar(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
) -> None:
    a = _tenant_session(
        client, auth_settings, seeder, slug="clinica-a", email="ana@example.test"
    )
    b = _tenant_session(
        client, auth_settings, seeder, slug="clinica-b", email="beto@example.test"
    )
    before = {
        "a": _session_state(db_engine, a.session_id),
        "b": _session_state(db_engine, b.session_id),
        "families": {
            "a": _family_state(db_engine, a.family_id),
            "b": _family_state(db_engine, b.family_id),
        },
    }

    # El refresh opaco usado como access no autentica.
    as_access = _raw(client, "GET", ME_URL, f"{ACCESS_COOKIE}={b.refresh_token}")

    # El JWT usado como refresh no rota nada.
    as_refresh = _raw(client, "POST", REFRESH_URL, f"{REFRESH_COOKIE}={a.access_token}")

    assert as_access.status_code == 401
    assert as_access.json()["code"] == "not_authenticated"
    assert as_refresh.status_code == 401
    assert as_refresh.json()["code"] == "not_authenticated"
    for response in (as_access, as_refresh):
        assert "set-cookie" not in response.headers

    assert _session_state(db_engine, a.session_id) == before["a"]
    assert _session_state(db_engine, b.session_id) == before["b"]
    assert _family_state(db_engine, a.family_id) == before["families"]["a"]
    assert _family_state(db_engine, b.family_id) == before["families"]["b"]

    # Access de A con refresh de B (y el simétrico): par inconsistente → 401.
    mixed_pairs = [
        (a.access_token, b.refresh_token),
        (b.access_token, a.refresh_token),
    ]
    for access, refresh in mixed_pairs:
        cookie = f"{ACCESS_COOKIE}={access}; {REFRESH_COOKIE}={refresh}"
        for method, url in (("POST", REFRESH_URL), ("POST", LOGOUT_URL)):
            response = _raw(client, method, url, cookie)
            assert response.status_code == 401
            assert response.json()["code"] == "not_authenticated"
            assert "set-cookie" not in response.headers

    assert _session_state(db_engine, a.session_id) == before["a"]
    assert _session_state(db_engine, b.session_id) == before["b"]
    assert _family_state(db_engine, a.family_id) == before["families"]["a"]
    assert _family_state(db_engine, b.family_id) == before["families"]["b"]

    # Las dos sesiones legítimas siguen vivas: /me y refresh responden 200.
    for session in (a, b):
        me = _raw(client, "GET", ME_URL, f"{ACCESS_COOKIE}={session.access_token}")
        assert me.status_code == 200
        assert me.json()["tenant"]["id"] == str(session.tenant_id)

        refreshed = _raw(
            client, "POST", REFRESH_URL, f"{REFRESH_COOKIE}={session.refresh_token}"
        )
        assert refreshed.status_code == 200
