"""Refresh rotativo, detección de reuso y credencial (tasks 3.3/3.5, design D2)."""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
REFRESH_COOKIE = "odontologia_refresh"
ACCESS_COOKIE = "odontologia_access"


def _cookie_value(response: Any, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        match = re.match(rf"^{re.escape(name)}=([^;]+)", header)
        if match:
            return match.group(1)
    return None


def _send_refresh(client: TestClient, token: str) -> Any:
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, token, path="/api/v1/auth")
    return client.post(REFRESH_URL)


def _refresh_rows(engine: Engine, family_id: UUID) -> dict[UUID, dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id, session_id, family_id, estado::text, used_at, replaced_by,
                       expires_at
                FROM refresh_token WHERE family_id = :family
                """
            ),
            {"family": family_id},
        ).mappings()
        return {row["id"]: dict(row) for row in rows}


def _session_row(engine: Engine, session_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT revoked_at, expires_at FROM session WHERE id = :id"),
            {"id": session_id},
        ).mappings().one()
    return dict(row)


def test_refresh_valido_rota_el_token_y_conserva_la_sesion(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    seeded = seeder.session(tenant_id, user_id)

    response = _send_refresh(client, seeded.refresh_token)

    assert response.status_code == 200
    new_token = _cookie_value(response, REFRESH_COOKIE)
    assert new_token is not None
    assert new_token != seeded.refresh_token
    assert _cookie_value(response, "odontologia_access") is not None

    rows = _refresh_rows(db_engine, seeded.family_id)
    old = rows[seeded.refresh_id]
    assert old["estado"] == "rotado"
    assert old["used_at"] is not None
    assert old["replaced_by"] is not None

    new = rows[old["replaced_by"]]
    assert new["estado"] == "activo"
    assert new["family_id"] == seeded.family_id
    assert new["session_id"] == seeded.session_id

    session_row = _session_row(db_engine, seeded.session_id)
    assert session_row["revoked_at"] is None
    assert new["expires_at"] == session_row["expires_at"]


def test_reuso_de_un_token_rotado_revoca_la_familia_entera(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    seeded = seeder.session(tenant_id, user_id)

    first = _send_refresh(client, seeded.refresh_token)
    assert first.status_code == 200
    rotated_token = _cookie_value(first, REFRESH_COOKIE)
    assert rotated_token is not None

    second = _send_refresh(client, seeded.refresh_token)

    assert second.status_code == 401
    assert second.json()["code"] == "refresh_reuse"
    assert "set-cookie" not in second.headers

    rows = _refresh_rows(db_engine, seeded.family_id)
    assert len(rows) == 2
    assert {row["estado"] for row in rows.values()} == {"revocado"}
    assert _session_row(db_engine, seeded.session_id)["revoked_at"] is not None

    third = _send_refresh(client, rotated_token)

    assert third.status_code == 401
    assert third.json()["code"] == "not_authenticated"


def test_refresh_expirado_o_de_sesion_revocada_no_toca_otras_familias(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    expired = seeder.session(tenant_id, user_id, refresh_ttl=timedelta(minutes=-1))
    closed = seeder.session(tenant_id, user_id, revoked=True)
    healthy = seeder.session(tenant_id, user_id)

    expired_response = _send_refresh(client, expired.refresh_token)
    closed_response = _send_refresh(client, closed.refresh_token)

    assert expired_response.status_code == 401
    assert expired_response.json()["code"] == "not_authenticated"
    assert closed_response.status_code == 401
    assert closed_response.json()["code"] == "not_authenticated"

    healthy_response = _send_refresh(client, healthy.refresh_token)

    assert healthy_response.status_code == 200
    assert _session_row(db_engine, healthy.session_id)["revoked_at"] is None


def test_credencial_vieja_rechaza_sin_rotar_y_solo_revoca_su_tenant(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_a = seeder.tenant()
    tenant_b = seeder.tenant()
    user_id = seeder.user(credentials_version=1)
    seeder.membership(tenant_a, user_id, "professional")
    seeder.membership(tenant_b, user_id, "professional")
    stale = seeder.session(tenant_a, user_id, credentials_version=0)
    current = seeder.session(tenant_b, user_id, credentials_version=1)

    response = _send_refresh(client, stale.refresh_token)

    assert response.status_code == 401
    assert response.json()["code"] == "credentials_changed"
    assert _refresh_rows(db_engine, stale.family_id)[stale.refresh_id]["estado"] == "activo"
    assert _session_row(db_engine, stale.session_id)["revoked_at"] is not None
    assert _session_row(db_engine, current.session_id)["revoked_at"] is None

    still_valid = _send_refresh(client, current.refresh_token)

    assert still_valid.status_code == 200


def _cookie_headers(response: Any) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        name = header.split("=", 1)[0]
        headers[name] = header
    return headers


def test_logout_idempotente_revoca_sesion_y_familia_sin_tocar_otras(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    target = seeder.session(tenant_id, user_id)
    untouched = seeder.session(tenant_id, user_id)

    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, target.refresh_token, path="/api/v1/auth")
    first = client.post(LOGOUT_URL)

    assert first.status_code == 204
    cookies = _cookie_headers(first)
    assert "Max-Age=0" in cookies[ACCESS_COOKIE]
    assert "Path=/" in cookies[ACCESS_COOKIE]
    assert "Max-Age=0" in cookies[REFRESH_COOKIE]
    assert "Path=/api/v1/auth" in cookies[REFRESH_COOKIE]

    revoked = _refresh_rows(db_engine, target.family_id)
    assert len(revoked) == 1
    assert {row["estado"] for row in revoked.values()} == {"revocado"}
    assert _session_row(db_engine, target.session_id)["revoked_at"] is not None

    # Segunda llamada: idempotente y sin efectos sobre otra sesión del usuario.
    second = client.post(LOGOUT_URL)

    assert second.status_code == 204
    assert _session_row(db_engine, target.session_id)["revoked_at"] is not None
    assert _session_row(db_engine, untouched.session_id)["revoked_at"] is None
    assert {row["estado"] for row in _refresh_rows(db_engine, untouched.family_id).values()} == {
        "activo"
    }

    # Sin cookies también es 204: el endpoint no filtra si había sesión.
    client.cookies.clear()
    assert client.post(LOGOUT_URL).status_code == 204


def test_dos_refresh_concurrentes_rotan_una_sola_vez(
    client: TestClient,
    seeder: Any,
    db_engine: Engine,
) -> None:
    """Con la fila bloqueada, ambos requests llegan al ``UPDATE`` a la vez.

    El que gana rota; el otro recibe 0 filas del ``UPDATE`` atómico y cae en la
    detección de reuso. Nunca hay dos filas ``activo`` ni dos sesiones.
    """
    tenant_id = seeder.tenant()
    user_id = seeder.user()
    seeder.membership(tenant_id, user_id, "professional")
    seeded = seeder.session(tenant_id, user_id)

    barrier = threading.Barrier(2)
    app = client.app

    def _call(_: int) -> Any:
        worker = TestClient(app)
        barrier.wait(timeout=10)
        return worker.post(
            REFRESH_URL,
            headers={"Cookie": f"{REFRESH_COOKIE}={seeded.refresh_token}"},
        )

    with db_engine.connect() as locker:
        locker.execute(
            text("SELECT id FROM refresh_token WHERE id = :id FOR UPDATE"),
            {"id": seeded.refresh_id},
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_call, index) for index in range(2)]
            time.sleep(1.5)
            locker.rollback()
            responses = [future.result(timeout=30) for future in futures]

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 401]
    rejected = next(response for response in responses if response.status_code == 401)
    assert rejected.json()["code"] == "refresh_reuse"
    assert "set-cookie" not in rejected.headers

    rows = _refresh_rows(db_engine, seeded.family_id)
    assert len(rows) == 2
    assert {row["estado"] for row in rows.values()} == {"revocado"}
    assert _session_row(db_engine, seeded.session_id)["revoked_at"] is not None
