"""Idempotencia del seed de e2e (task 11.1).

El seed corre una vez por arranque del servidor de Playwright, pero los tests
cambian roles y el segundo arranque debe dejar **exactamente** la misma matriz:
mismos ids, mismas memberships, sin duplicados. Si esto se rompe, el e2e falla
por estado heredado y no por la aplicación.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from app.core.crypto import decrypt_secret
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

TESTS_ROOT = Path(__file__).resolve().parents[1]
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from fixtures import seed_auth_e2e as seed_e2e  # noqa: E402  (path del seed)


def _snapshot(engine: Engine, tenant_ids: tuple[Any, Any]) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT m.tenant_id, u.email, m.rol::text AS rol, m.activo
                FROM membership m JOIN "user" u ON u.id = m.user_id
                WHERE m.tenant_id IN (:a, :b)
                ORDER BY u.email, m.rol
                """
            ),
            {"a": tenant_ids[0], "b": tenant_ids[1]},
        ).all()
        return [tuple(row) for row in rows]


def _mfa_secret(engine: Engine, user_id: Any) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            text('SELECT mfa_secret FROM "user" WHERE id = :id'), {"id": user_id}
        ).scalar_one()


def _cleanup(engine: Engine) -> None:
    """Borra lo sembrado para no dejar usuarios globales que choquen con otros tests.

    ``"user"`` es global (el email es único en toda la base) y el ``Seeder`` de
    integración inserta con ``email`` explícito: si este test dejara
    ``profe@example.test`` vivo, el test de cambio de rol fallaría con
    ``uq_user_email``. ``membership`` cae por ``ON DELETE CASCADE``.
    """
    with engine.begin() as connection:
        connection.execute(
            text('DELETE FROM "user" WHERE email = ANY(:emails)'),
            {
                "emails": [user.email for user in seed_e2e.FLOW_USERS]
                + [seed_e2e.OTHER_TENANT_USER.email]
            },
        )
        connection.execute(
            text("DELETE FROM tenant WHERE slug = ANY(:slugs)"),
            {"slugs": [seed_e2e.TENANT_SLUG, seed_e2e.OTHER_TENANT_SLUG]},
        )


def test_el_seed_e2e_es_idempotente(migrated_database: str) -> None:
    engine = create_engine(migrated_database, future=True)
    try:
        first = seed_e2e.seed(engine)
        after_first = _snapshot(engine, (first.tenant_id, first.other_tenant_id))
        second = seed_e2e.seed(engine)
        after_second = _snapshot(engine, (second.tenant_id, second.other_tenant_id))

        assert first.tenant_id == second.tenant_id
        assert first.other_tenant_id == second.other_tenant_id
        assert first.users == second.users
        assert after_first == after_second

        # 5 usuarios del flujo en clínica A y 1 ajeno en B, sin duplicados.
        assert len(after_first) == len(seed_e2e.FLOW_USERS) + 1
        roles_a = {
            (email, rol)
            for tenant_id, email, rol, activo in after_first
            if tenant_id == first.tenant_id and activo
        }
        assert roles_a == {
            (seed_e2e.USER_EMAIL, "professional"),
            (seed_e2e.OWNER_EMAIL, "owner"),
            (seed_e2e.CLINICAL_ADMIN_EMAIL, "clinical_admin"),
            (seed_e2e.FRONT_DESK_EMAIL, "front_desk"),
            (seed_e2e.PROFESSIONAL_EMAIL, "professional"),
        }
        roles_b = {
            (email, rol)
            for tenant_id, email, rol, activo in after_first
            if tenant_id == first.other_tenant_id
        }
        assert roles_b == {(seed_e2e.OTHER_TENANT_EMAIL, "professional")}

        # Solo el owner tiene el segundo factor pre-enrolado, con el secreto fijo
        # cifrado en reposo y descifrable con la clave ficticia del e2e.
        owner_secret = _mfa_secret(engine, second.users[seed_e2e.OWNER_EMAIL])
        assert owner_secret is not None
        assert (
            decrypt_secret(
                owner_secret,
                seed_e2e.DEFAULT_MFA_ENCRYPTION_KEY,
                key_version=1,
            )
            == seed_e2e.OWNER_TOTP_SECRET
        )
        for email in (
            seed_e2e.USER_EMAIL,
            seed_e2e.CLINICAL_ADMIN_EMAIL,
            seed_e2e.FRONT_DESK_EMAIL,
            seed_e2e.PROFESSIONAL_EMAIL,
            seed_e2e.OTHER_TENANT_EMAIL,
        ):
            assert _mfa_secret(engine, second.users[email]) is None
    finally:
        _cleanup(engine)
        engine.dispose()
