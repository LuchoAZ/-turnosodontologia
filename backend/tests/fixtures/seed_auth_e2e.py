"""Cuenta ficticia e idempotente para el e2e de auth (task 8.7).

La usa ``backend/scripts/e2e_server.py`` antes de levantar uvicorn. Corre como el
superusuario del contenedor (Alembic y seed), nunca como ``odontologia_app``.
Los datos son ficticios y la contraseña se puede pisar por entorno: no hay
secretos reales en el repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.config import Environment
from app.domain.auth.passwords import hash_password
from sqlalchemy import text
from sqlalchemy.engine import Engine

TENANT_SLUG = "clinica-demo"
TENANT_NAME = "Clínica Demo"
TENANT_CUIT = "20123456789"
USER_EMAIL = "demo@example.test"
USER_PASSWORD = "demo-password-123"


@dataclass(frozen=True)
class SeededAccount:
    """Credenciales del e2e; el slug y el email son estables entre corridas."""

    tenant_id: UUID
    user_id: UUID
    tenant_slug: str = TENANT_SLUG
    tenant_name: str = TENANT_NAME
    email: str = USER_EMAIL
    password: str = USER_PASSWORD


def seed(engine: Engine, *, password: str = USER_PASSWORD) -> SeededAccount:
    """Crea o actualiza tenant, usuario y membership ``professional``.

    Idempotente: reejecutarlo deja la misma cuenta con la contraseña vigente, así
    el e2e puede correr contra un contenedor reciclado o contra una base externa.
    """
    password_hash = hash_password(password, Environment.test)

    with engine.begin() as connection:
        tenant_id = connection.execute(
            text(
                """
                INSERT INTO tenant (slug, nombre_comercial, cuit, estado)
                VALUES (:slug, :nombre, :cuit, 'active')
                ON CONFLICT (slug) DO UPDATE
                   SET nombre_comercial = EXCLUDED.nombre_comercial
                RETURNING id
                """
            ),
            {"slug": TENANT_SLUG, "nombre": TENANT_NAME, "cuit": TENANT_CUIT},
        ).scalar_one()

        user_id = connection.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": USER_EMAIL},
        ).scalar_one_or_none()

        if user_id is None:
            user_id = connection.execute(
                text(
                    """
                    INSERT INTO "user" (email, password_hash, nombre, apellido, activo)
                    VALUES (:email, :password_hash, 'Demo', 'Pérez', true)
                    RETURNING id
                    """
                ),
                {"email": USER_EMAIL, "password_hash": password_hash},
            ).scalar_one()
        else:
            connection.execute(
                text(
                    """
                    UPDATE "user"
                       SET password_hash = :password_hash,
                           activo = true,
                           failed_login_count = 0,
                           lockout_strikes = 0,
                           locked_until = NULL
                     WHERE id = :id
                    """
                ),
                {"id": user_id, "password_hash": password_hash},
            )

        connection.execute(
            text(
                """
                INSERT INTO membership (tenant_id, user_id, rol, activo)
                VALUES (:tenant_id, :user_id, 'professional', true)
                ON CONFLICT ON CONSTRAINT uq_membership_tenant_user_rol
                DO UPDATE SET activo = true
                """
            ),
            {"tenant_id": tenant_id, "user_id": user_id},
        )

    return SeededAccount(tenant_id=tenant_id, user_id=user_id, password=password)
