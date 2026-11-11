"""Cuentas ficticias e idempotentes para el e2e (tasks 8.7 y 11.1).

La usa ``backend/scripts/e2e_server.py`` antes de levantar uvicorn. Corre como el
superusuario del contenedor (Alembic y seed), nunca como ``odontologia_app``.

Siembra el flujo completo de equipo en ``clinica-demo``:

===================  ==================  ======================================
email                rol                 uso en el e2e
===================  ==================  ======================================
demo@example.test    professional        auth (login, logout, refresh)
owner@example.test   owner               equipo: MFA pre-enrolado + TOTP fijo
admin@example.test   clinical_admin      equipo: ve la lista, no gestiona
desk@example.test    front_desk          equipo: 403 y sin enlace
profe@example.test   professional        equipo: destino del cambio de rol
===================  ==================  ======================================

Y en ``clinica-demo-b`` un único miembro (``ajeno@example.test``) para que el
aislamiento cross-tenant tenga datos que **no** deben aparecer nunca.

Todo es ficticio: contraseñas iguales y conocidas, y el secreto TOTP es el
vector público de RFC 4648 (``JBSWY3DPEHPK3PXP``). No hay secretos reales.
Idempotente: reejecutarlo deja los mismos ids y la misma matriz de memberships,
porque el seed **reemplaza** las memberships de esos tenants (los tests de
Playwright cambian roles y sin el reset el segundo run arrancaría distinto).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.config import Environment
from app.core.crypto import encrypt_secret
from app.domain.auth.passwords import hash_password
from sqlalchemy import text
from sqlalchemy.engine import Engine

TENANT_SLUG = "clinica-demo"
TENANT_NAME = "Clínica Demo"
TENANT_CUIT = "20123456789"

OTHER_TENANT_SLUG = "clinica-demo-b"
OTHER_TENANT_NAME = "Clínica Demo B"
OTHER_TENANT_CUIT = "20987654321"

USER_EMAIL = "demo@example.test"
USER_PASSWORD = "demo-password-123"

OWNER_EMAIL = "owner@example.test"
CLINICAL_ADMIN_EMAIL = "admin@example.test"
FRONT_DESK_EMAIL = "desk@example.test"
PROFESSIONAL_EMAIL = "profe@example.test"
OTHER_TENANT_EMAIL = "ajeno@example.test"

#: Vector público de RFC 4648: sirve para TOTP pero no protege nada real.
OWNER_TOTP_SECRET = "JBSWY3DPEHPK3PXP"

#: La misma clave ficticia que exporta ``e2e_server._export_settings``.
DEFAULT_MFA_ENCRYPTION_KEY = "m" * 32


@dataclass(frozen=True)
class SeedUser:
    email: str
    nombre: str
    apellido: str
    rol: str
    mfa: bool = False


FLOW_USERS: tuple[SeedUser, ...] = (
    SeedUser(USER_EMAIL, "Demo", "Pérez", "professional"),
    SeedUser(OWNER_EMAIL, "Olivia", "Owner", "owner", mfa=True),
    SeedUser(CLINICAL_ADMIN_EMAIL, "Clara", "Admin", "clinical_admin"),
    SeedUser(FRONT_DESK_EMAIL, "Fran", "Recepción", "front_desk"),
    SeedUser(PROFESSIONAL_EMAIL, "Paula", "Profesional", "professional"),
)

OTHER_TENANT_USER = SeedUser(OTHER_TENANT_EMAIL, "Bruno", "Ajeno", "professional")


@dataclass(frozen=True)
class SeededAccount:
    """Credenciales del e2e; el slug y los emails son estables entre corridas."""

    tenant_id: UUID
    user_id: UUID
    tenant_slug: str = TENANT_SLUG
    tenant_name: str = TENANT_NAME
    email: str = USER_EMAIL
    password: str = USER_PASSWORD
    users: dict[str, UUID] = field(default_factory=dict)
    other_tenant_id: UUID | None = None


def _upsert_tenant(connection, *, slug: str, nombre: str, cuit: str) -> UUID:
    return connection.execute(
        text(
            """
            INSERT INTO tenant (slug, nombre_comercial, cuit, estado)
            VALUES (:slug, :nombre, :cuit, 'active')
            ON CONFLICT (slug) DO UPDATE
               SET nombre_comercial = EXCLUDED.nombre_comercial
            RETURNING id
            """
        ),
        {"slug": slug, "nombre": nombre, "cuit": cuit},
    ).scalar_one()


def _upsert_user(
    connection,
    *,
    user: SeedUser,
    password_hash: str,
    mfa_secret: str | None,
) -> UUID:
    """Crea el usuario o lo deja con la contraseña y el MFA canónicos del seed.

    La versión de clave y la fecha de enrolamiento se calculan en Python y no con
    un ``CASE`` en SQL: psycopg no puede inferir el tipo de un bind que sólo se
    usa en un ``CASE WHEN :x IS NULL`` y Postgres rechaza el ``INSERT`` por
    ``could not determine data type of parameter``.
    """
    key_version = 1 if mfa_secret is not None else None
    enrolled_at = datetime.now(UTC) if mfa_secret is not None else None

    user_id = connection.execute(
        text('SELECT id FROM "user" WHERE email = :email'), {"email": user.email}
    ).scalar_one_or_none()

    if user_id is None:
        return connection.execute(
            text(
                """
                INSERT INTO "user"
                    (email, password_hash, nombre, apellido, activo, mfa_secret,
                     mfa_secret_key_version, mfa_enrolled_at)
                VALUES (:email, :password_hash, :nombre, :apellido, true, :mfa_secret,
                        :key_version, :enrolled_at)
                RETURNING id
                """
            ),
            {
                "email": user.email,
                "password_hash": password_hash,
                "nombre": user.nombre,
                "apellido": user.apellido,
                "mfa_secret": mfa_secret,
                "key_version": key_version,
                "enrolled_at": enrolled_at,
            },
        ).scalar_one()

    connection.execute(
        text(
            """
            UPDATE "user"
               SET password_hash = :password_hash,
                   nombre = :nombre,
                   apellido = :apellido,
                   activo = true,
                   mfa_secret = :mfa_secret,
                   mfa_secret_key_version = :key_version,
                   mfa_enrolled_at = :enrolled_at,
                   last_totp_step = NULL,
                   failed_login_count = 0,
                   lockout_strikes = 0,
                   locked_until = NULL
             WHERE id = :id
            """
        ),
        {
            "id": user_id,
            "password_hash": password_hash,
            "nombre": user.nombre,
            "apellido": user.apellido,
            "mfa_secret": mfa_secret,
            "key_version": key_version,
            "enrolled_at": enrolled_at,
        },
    )
    return user_id


def seed(
    engine: Engine,
    *,
    password: str = USER_PASSWORD,
    mfa_encryption_key: str = DEFAULT_MFA_ENCRYPTION_KEY,
) -> SeededAccount:
    """Crea o actualiza tenants, usuarios y la matriz de memberships canónica."""
    password_hash = hash_password(password, Environment.test)
    owner_secret = encrypt_secret(OWNER_TOTP_SECRET, mfa_encryption_key, key_version=1)

    with engine.begin() as connection:
        tenant_id = _upsert_tenant(
            connection, slug=TENANT_SLUG, nombre=TENANT_NAME, cuit=TENANT_CUIT
        )
        other_tenant_id = _upsert_tenant(
            connection,
            slug=OTHER_TENANT_SLUG,
            nombre=OTHER_TENANT_NAME,
            cuit=OTHER_TENANT_CUIT,
        )

        # Reset explícito: los tests cambian roles y el seed debe devolver la
        # matriz canónica en cada arranque (idempotente, sin memberships extra).
        connection.execute(
            text("DELETE FROM membership WHERE tenant_id IN (:a, :b)"),
            {"a": tenant_id, "b": other_tenant_id},
        )

        users: dict[str, UUID] = {}
        for user in FLOW_USERS:
            user_id = _upsert_user(
                connection,
                user=user,
                password_hash=password_hash,
                mfa_secret=owner_secret if user.mfa else None,
            )
            users[user.email] = user_id
            connection.execute(
                text(
                    """
                    INSERT INTO membership (tenant_id, user_id, rol, activo)
                    VALUES (:tenant_id, :user_id, :rol, true)
                    """
                ),
                {"tenant_id": tenant_id, "user_id": user_id, "rol": user.rol},
            )

        other_user_id = _upsert_user(
            connection,
            user=OTHER_TENANT_USER,
            password_hash=password_hash,
            mfa_secret=None,
        )
        users[OTHER_TENANT_USER.email] = other_user_id
        connection.execute(
            text(
                """
                INSERT INTO membership (tenant_id, user_id, rol, activo)
                VALUES (:tenant_id, :user_id, :rol, true)
                """
            ),
            {
                "tenant_id": other_tenant_id,
                "user_id": other_user_id,
                "rol": OTHER_TENANT_USER.rol,
            },
        )

    return SeededAccount(
        tenant_id=tenant_id,
        user_id=users[USER_EMAIL],
        password=password,
        users=users,
        other_tenant_id=other_tenant_id,
    )
