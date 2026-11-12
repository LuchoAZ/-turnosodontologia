from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.config import Environment, Settings, load_config
from app.core.crypto import encrypt_secret
from app.domain.auth.passwords import hash_password
from app.domain.auth.tokens import hash_token, new_opaque_token
from app.domain.patients.hce import formatear_numero
from app.domain.patients.normalize import normalizar_telefono, normalizar_texto
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

    def specialty(self, nombre: str = "Odontología general") -> UUID:
        """Id de una especialidad global sembrada por 002."""
        with self.engine.connect() as connection:
            return connection.execute(
                text(
                    """
                    SELECT id FROM specialty
                    WHERE nombre = :nombre AND tenant_id IS NULL
                    """
                ),
                {"nombre": nombre},
            ).scalar_one()

    def chair(
        self,
        tenant_id: UUID,
        nombre: str = "Sillón 1",
        tipo: str = "consultorio",
        *,
        activo: bool = True,
        ubicacion: str | None = None,
        equipamiento: dict[str, object] | None = None,
    ) -> UUID:
        chair_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO chair
                        (id, tenant_id, nombre, tipo, activo, ubicacion, equipamiento)
                    VALUES (:id, :tenant_id, :nombre, CAST(:tipo AS chair_tipo), :activo,
                            :ubicacion, CAST(:equipamiento AS jsonb))
                    """
                ),
                {
                    "id": chair_id,
                    "tenant_id": tenant_id,
                    "nombre": nombre,
                    "tipo": tipo,
                    "activo": activo,
                    "ubicacion": ubicacion,
                    "equipamiento": json.dumps(equipamiento or {}),
                },
            )
        return chair_id

    def professional(
        self,
        tenant_id: UUID,
        *,
        nombre: str = "Paula",
        apellido: str = "Pérez",
        matricula: str | None = None,
        especialidad_id: UUID | None = None,
        user_id: UUID | None = None,
        duracion_default_min: int = 30,
        porcentaje_liquidacion: float = 40,
        color_agenda: str = "#2563EB",
        activo: bool = True,
    ) -> UUID:
        professional_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO professional
                        (id, tenant_id, user_id, nombre, apellido, matricula, especialidad_id,
                         porcentaje_liquidacion, duracion_default_min, color_agenda, activo)
                    VALUES (:id, :tenant_id, :user_id, :nombre, :apellido, :matricula,
                            :especialidad_id, :porcentaje, :duracion, :color, :activo)
                    """
                ),
                {
                    "id": professional_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "nombre": nombre,
                    "apellido": apellido,
                    "matricula": matricula or f"MP-{uuid4().hex[:6]}",
                    "especialidad_id": especialidad_id or self.specialty(),
                    "porcentaje": porcentaje_liquidacion,
                    "duracion": duracion_default_min,
                    "color": color_agenda,
                    "activo": activo,
                },
            )
        return professional_id

    def availability_rule(
        self,
        tenant_id: UUID,
        *,
        professional_id: UUID | None = None,
        chair_id: UUID | None = None,
        dia_semana: int = 1,
        hora_inicio: time = time(9, 0),
        hora_fin: time = time(12, 0),
        slot_min: int = 30,
        buffer_previo_min: int = 0,
        buffer_posterior_min: int = 0,
        fecha_desde: date = date(2026, 11, 16),
        fecha_hasta: date | None = None,
        tipo_practica: str | None = None,
    ) -> UUID:
        rule_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO availability_rule
                        (id, tenant_id, professional_id, chair_id, dia_semana, hora_inicio,
                         hora_fin, slot_min, buffer_previo_min, buffer_posterior_min,
                         fecha_desde, fecha_hasta, tipo_practica)
                    VALUES (:id, :tenant_id, :professional_id, :chair_id, :dia_semana,
                            :hora_inicio, :hora_fin, :slot_min, :buffer_previo,
                            :buffer_posterior, :fecha_desde, :fecha_hasta, :tipo_practica)
                    """
                ),
                {
                    "id": rule_id,
                    "tenant_id": tenant_id,
                    "professional_id": professional_id,
                    "chair_id": chair_id,
                    "dia_semana": dia_semana,
                    "hora_inicio": hora_inicio,
                    "hora_fin": hora_fin,
                    "slot_min": slot_min,
                    "buffer_previo": buffer_previo_min,
                    "buffer_posterior": buffer_posterior_min,
                    "fecha_desde": fecha_desde,
                    "fecha_hasta": fecha_hasta,
                    "tipo_practica": tipo_practica,
                },
            )
        return rule_id

    def patient(
        self,
        tenant_id: UUID,
        *,
        nombre: str = "Ana",
        apellido: str = "Pérez",
        telefono: str = "11 5555-1234",
        dni: str | None = None,
        numero_historia_clinica: str | None = None,
        email: str | None = None,
        sexo: str | None = None,
        fecha_nacimiento: date | None = None,
        domicilio: dict[str, object] | None = None,
        obra_social_id: UUID | None = None,
        user_id: UUID | None = None,
        activo: bool = True,
        deleted_at: datetime | None = None,
        alergias: str | None = None,
        alerta_clinica: bool = False,
    ) -> UUID:
        """Siembra un paciente como superusuario.

        La HCE sale de ``patient_counter`` con el mismo upsert atómico que usa el
        servicio (D4), así los fixtures respetan el contador real y los tests de
        secuencia son deterministas. ``*_norm`` se calculan con el normalizador
        de dominio: no se duplica la regla en el test.
        """
        patient_id = uuid4()
        with self.engine.begin() as connection:
            if numero_historia_clinica is None:
                secuencia = connection.execute(
                    text(
                        """
                        INSERT INTO patient_counter (tenant_id, ultimo_numero)
                        VALUES (:tenant_id, 1)
                        ON CONFLICT (tenant_id) DO UPDATE
                          SET ultimo_numero = patient_counter.ultimo_numero + 1,
                              updated_at = now()
                        RETURNING ultimo_numero
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).scalar_one()
                numero_historia_clinica = formatear_numero(secuencia)
            connection.execute(
                text(
                    """
                    INSERT INTO patient
                        (id, tenant_id, user_id, dni, nombre, apellido, apellido_norm,
                         nombre_norm, fecha_nacimiento, sexo, telefono, telefono_norm,
                         email, domicilio, obra_social_id, numero_historia_clinica,
                         alergias, alerta_clinica, activo, deleted_at)
                    VALUES (:id, :tenant_id, :user_id, :dni, :nombre, :apellido, :apellido_norm,
                            :nombre_norm, :fecha_nacimiento, CAST(:sexo AS sexo_paciente),
                            :telefono, :telefono_norm, :email, CAST(:domicilio AS jsonb),
                            :obra_social_id, :numero_historia_clinica, :alergias,
                            :alerta_clinica, :activo, :deleted_at)
                    """
                ),
                {
                    "id": patient_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "dni": dni,
                    "nombre": nombre,
                    "apellido": apellido,
                    "apellido_norm": normalizar_texto(apellido),
                    "nombre_norm": normalizar_texto(nombre),
                    "fecha_nacimiento": fecha_nacimiento,
                    "sexo": sexo,
                    "telefono": telefono,
                    "telefono_norm": normalizar_telefono(telefono),
                    "email": email,
                    "domicilio": json.dumps(domicilio) if domicilio is not None else None,
                    "obra_social_id": obra_social_id,
                    "numero_historia_clinica": numero_historia_clinica,
                    "alergias": alergias,
                    "alerta_clinica": alerta_clinica,
                    "activo": activo,
                    "deleted_at": deleted_at,
                },
            )
        return patient_id

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

    def appointment(
        self,
        tenant_id: UUID,
        *,
        professional_id: UUID,
        chair_id: UUID,
        inicio: datetime,
        duracion_min: int = 30,
        buffer_previo_min: int = 0,
        buffer_posterior_min: int = 0,
        estado: str = "pendiente",
        origen: str = "recepcion",
        patient_id: UUID | None = None,
        creado_por: UUID | None = None,
        tipo_practica: str | None = None,
    ) -> UUID:
        """Turno ya existente para probar el solape y RN-AG-10.

        ``fin`` se deriva de ``duracion_min`` (nunca se pasa a mano): es lo que hace
        el servicio y así el setup no crea filas que la API no podría crear. El
        default ``patient_id = None`` es un turno sin paciente identificado: los
        tests de solape de recursos no deben disparar RN-AG-10 de rebote.
        """
        appointment_id = uuid4()
        fin = inicio + timedelta(minutes=duracion_min)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO appointment
                        (id, tenant_id, patient_id, professional_id, chair_id, inicio, fin,
                         duracion_min, buffer_previo_min, buffer_posterior_min, estado,
                         origen, creado_por, tipo_practica)
                    VALUES
                        (:id, :tenant_id, :patient_id, :professional_id, :chair_id, :inicio,
                         :fin, :duracion_min, :buffer_previo_min, :buffer_posterior_min,
                         CAST(:estado AS appointment_estado),
                         CAST(:origen AS appointment_origen), :creado_por, :tipo_practica)
                    """
                ),
                {
                    "id": appointment_id,
                    "tenant_id": tenant_id,
                    "patient_id": patient_id,
                    "professional_id": professional_id,
                    "chair_id": chair_id,
                    "inicio": inicio,
                    "fin": fin,
                    "duracion_min": duracion_min,
                    "buffer_previo_min": buffer_previo_min,
                    "buffer_posterior_min": buffer_posterior_min,
                    "estado": estado,
                    "origen": origen,
                    "creado_por": creado_por,
                    "tipo_practica": tipo_practica,
                },
            )
        return appointment_id

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

