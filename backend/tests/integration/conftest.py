from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.config import Environment, Settings, load_config
from app.core.crypto import encrypt_secret
from app.domain.auth.passwords import hash_password
from app.domain.auth.tokens import hash_token, new_opaque_token
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    """True when a Docker daemon is reachable; nothing else is skipped."""
    try:
        from testcontainers.core.docker_client import DockerClient

        DockerClient().client.ping()
    except Exception:
        return False
    return True


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


@pytest.fixture(scope="session")
def docker_services() -> Iterator[dict[str, str]]:
    """Start real Postgres 16 + Redis 7 containers for the session.

    Skips only when Docker itself is unreachable; any other failure (bad image,
    misconfigured helper) propagates and fails the test instead of hiding.
    """
    if not _docker_available():
        pytest.skip("Docker is not available")
    with (
        PostgresContainer("postgres:16-alpine") as pg,
        RedisContainer("redis:7-alpine") as redis,
    ):
        redis_host = redis.get_container_host_ip()
        redis_port = redis.get_exposed_port(6379)
        yield {
            "postgres_url": _normalize_postgres_url(pg.get_connection_url(driver=None)),
            "redis_url": f"redis://{redis_host}:{redis_port}/0",
        }


@pytest.fixture
def pg_engine(docker_services: dict[str, str]) -> Iterator[Engine]:
    eng = create_engine(docker_services["postgres_url"], future=True)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="session")
def migrated_database(docker_services: dict[str, str]) -> str:
    """Run the real Alembic chain (baseline + 002) once against the container."""
    url = docker_services["postgres_url"]
    config = Config()
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return url


@pytest.fixture
def db_engine(migrated_database: str) -> Iterator[Engine]:
    eng = create_engine(migrated_database, future=True)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def auth_settings(migrated_database: str, docker_services: dict[str, str]) -> Settings:
    """Config de la app para HTTP: ``odontologia_app``, Redis del contenedor."""
    return load_config(
        {
            "ENVIRONMENT": "test",
            "DATABASE_URL": migrated_database,
            "REDIS_URL": docker_services["redis_url"],
            "SESSION_SECRET": "s" * 64,
            "JWT_REFRESH_SECRET": "j" * 64,
            "MFA_ENCRYPTION_KEY": "m" * 32,
            "COOKIE_SECURE": "false",
        }
    )


@pytest.fixture
def client(auth_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(auth_settings)) as test_client:
        yield test_client


@pytest.fixture
def production_settings(
    migrated_database: str, docker_services: dict[str, str]
) -> Settings:
    """Misma base y Redis, pero ``ENVIRONMENT=production`` con cookies ``Secure``."""
    return load_config(
        {
            "ENVIRONMENT": "production",
            "DATABASE_URL": migrated_database,
            "REDIS_URL": docker_services["redis_url"],
            "SESSION_SECRET": "s" * 64,
            "JWT_REFRESH_SECRET": "j" * 64,
            "MFA_ENCRYPTION_KEY": "m" * 32,
            "COOKIE_SECURE": "true",
        }
    )


@pytest.fixture
def secure_client(production_settings: Settings) -> Iterator[TestClient]:
    """Cliente https para que httpx acepte cookies ``Secure``."""
    with TestClient(
        create_app(production_settings), base_url="https://testserver"
    ) as test_client:
        yield test_client


@dataclass(frozen=True)
class SeededSession:
    """Sesión sembrada con el refresh en claro (solo el hash va a la base)."""

    session_id: UUID
    refresh_id: UUID
    family_id: UUID
    refresh_token: str


class Seeder:
    """Siembra tenants, usuarios y memberships como superusuario.

    El HTTP corre como ``odontologia_app`` (RLS activa); el superusuario del
    contenedor solo se usa para el setup y las aserciones directas. ``close``
    borra lo sembrado en orden de FK (``user`` primero: ``auth_event`` hace
    ``ON DELETE SET NULL`` y el trigger lo permite).
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._tenants: list[UUID] = []
        self._users: list[UUID] = []

    def tenant(
        self,
        *,
        slug: str | None = None,
        estado: str = "active",
        nombre: str = "Clínica Demo",
    ) -> UUID:
        tenant_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO tenant (id, slug, nombre_comercial, cuit, estado)
                    VALUES (:id, :slug, :nombre, :cuit, :estado)
                    """
                ),
                {
                    "id": tenant_id,
                    "slug": slug or f"clinica-{uuid4().hex[:8]}",
                    "nombre": nombre,
                    "cuit": f"{uuid4().int % 10**11:011d}",
                    "estado": estado,
                },
            )
        self._tenants.append(tenant_id)
        return tenant_id

    def user(
        self,
        *,
        email: str | None = None,
        password: str | None = "correct-horse-battery-staple",
        activo: bool = True,
        mfa_secret: str | None = None,
        credentials_version: int = 0,
        nombre: str = "Ana",
        apellido: str = "Pérez",
    ) -> UUID:
        user_id = uuid4()
        password_hash = hash_password(password, Environment.test) if password is not None else None
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO "user"
                        (id, email, password_hash, nombre, apellido, activo, mfa_secret,
                         credentials_version)
                    VALUES (:id, :email, :password_hash, :nombre, :apellido, :activo,
                            :mfa_secret, :credentials_version)
                    """
                ),
                {
                    "id": user_id,
                    "email": email or f"user-{uuid4().hex[:8]}@example.test",
                    "password_hash": password_hash,
                    "nombre": nombre,
                    "apellido": apellido,
                    "activo": activo,
                    "mfa_secret": mfa_secret,
                    "credentials_version": credentials_version,
                },
            )
        self._users.append(user_id)
        return user_id

    def membership(
        self,
        tenant_id: UUID,
        user_id: UUID,
        rol: str = "professional",
        *,
        activo: bool = True,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO membership (id, tenant_id, user_id, rol, activo)
                    VALUES (:id, :tenant_id, :user_id, :rol, :activo)
                    """
                ),
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "rol": rol,
                    "activo": activo,
                },
            )

    def session(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        credentials_version: int = 0,
        mfa_satisfied: bool = True,
        session_ttl: timedelta | None = None,
        refresh_ttl: timedelta | None = None,
        revoked: bool = False,
    ) -> SeededSession:
        """Sesión + refresh con token en claro conocido (para probar el endpoint)."""
        now = datetime.now(UTC)
        session_expires = now + (session_ttl or timedelta(hours=1))
        refresh_expires = now + (refresh_ttl or (session_expires - now))
        session_id = uuid4()
        refresh_id = uuid4()
        family_id = uuid4()
        plain_refresh = new_opaque_token()

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO session
                        (id, user_id, tenant_id, credentials_version, mfa_satisfied,
                         expires_at, revoked_at, created_at)
                    VALUES (:id, :user_id, :tenant_id, :credentials_version, :mfa_satisfied,
                            :expires_at, :revoked_at, :created_at)
                    """
                ),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "credentials_version": credentials_version,
                    "mfa_satisfied": mfa_satisfied,
                    "expires_at": session_expires,
                    "revoked_at": now if revoked else None,
                    "created_at": now,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO refresh_token
                        (id, session_id, tenant_id, family_id, token_hash, estado,
                         expires_at, created_at)
                    VALUES (:id, :session_id, :tenant_id, :family_id, :token_hash, 'activo',
                            :expires_at, :created_at)
                    """
                ),
                {
                    "id": refresh_id,
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "family_id": family_id,
                    "token_hash": hash_token(plain_refresh),
                    "expires_at": refresh_expires,
                    "created_at": now,
                },
            )

        return SeededSession(
            session_id=session_id,
            refresh_id=refresh_id,
            family_id=family_id,
            refresh_token=plain_refresh,
        )

    def enroll_mfa(
        self,
        user_id: UUID,
        *,
        secret: str,
        encryption_key: str,
        key_version: int = 1,
    ) -> None:
        """Deja al usuario con segundo factor enrolado (secreto cifrado en reposo)."""
        ciphertext = encrypt_secret(secret, encryption_key, key_version=key_version)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE "user"
                       SET mfa_secret = :ciphertext,
                           mfa_secret_key_version = :key_version,
                           mfa_enrolled_at = now()
                     WHERE id = :id
                    """
                ),
                {
                    "id": user_id,
                    "ciphertext": ciphertext,
                    "key_version": key_version,
                },
            )

    def set_membership_active(
        self, tenant_id: UUID, user_id: UUID, *, activo: bool
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE membership SET activo = :activo
                    WHERE tenant_id = :tenant_id AND user_id = :user_id
                    """
                ),
                {"activo": activo, "tenant_id": tenant_id, "user_id": user_id},
            )

    def close(self) -> None:
        with self.engine.begin() as connection:
            if self._users:
                connection.execute(
                    text('DELETE FROM "user" WHERE id IN :ids').bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": self._users},
                )
            if self._tenants:
                connection.execute(
                    text("DELETE FROM tenant WHERE id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": self._tenants},
                )
        self._users.clear()
        self._tenants.clear()


@pytest.fixture
def seeder(db_engine: Engine) -> Iterator[Seeder]:
    helper = Seeder(db_engine)
    try:
        yield helper
    finally:
        helper.close()

