"""Modelos de identidad y tenancy (KB ``04_modelo_de_datos`` § Tenancy)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Role(StrEnum):
    """Los 9 roles base de ``03_actores_y_roles`` (enum nativo ``role``)."""

    owner = "owner"
    clinical_admin = "clinical_admin"
    professional = "professional"
    assistant = "assistant"
    front_desk = "front_desk"
    billing = "billing"
    patient = "patient"
    external_lab = "external_lab"
    accountant = "accountant"


class TenantEstado(StrEnum):
    trial = "trial"
    active = "active"
    suspended = "suspended"
    closed = "closed"


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Clínica (PyME). Sin RLS: el login la resuelve por ``slug`` antes del contexto."""

    __tablename__ = "tenant"
    __table_args__ = (Index("ix_tenant_estado", "estado"),)

    slug: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    nombre_comercial: Mapped[str] = mapped_column(String(160), nullable=False)
    cuit: Mapped[str] = mapped_column(String(11), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'America/Argentina/Buenos_Aires'"),
    )
    config: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    estado: Mapped[TenantEstado] = mapped_column(
        Enum(TenantEstado, name="tenant_estado"),
        nullable=False,
        server_default=text("'trial'"),
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persona global; el vínculo con una clínica vive en ``membership``."""

    __tablename__ = "user"
    __table_args__ = (
        Index("uq_user_email", "email", unique=True, postgresql_where=text("email IS NOT NULL")),
        Index("ix_user_telefono", "telefono"),
        Index("ix_user_dni", "dni"),
    )

    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dni: Mapped[str | None] = mapped_column(String(11), nullable=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    apellido: Mapped[str] = mapped_column(String(80), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_secret: Mapped[str | None] = mapped_column(Text, nullable=True)


class Membership(UUIDPrimaryKeyMixin, Base):
    """Vínculo usuario ↔ tenant ↔ rol. Tabla tenant-scoped con RLS forzada."""

    __tablename__ = "membership"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "rol",
            name="uq_membership_tenant_user_rol",
        ),
        Index(
            "uq_membership_owner_activo",
            "tenant_id",
            unique=True,
            postgresql_where=text("rol = 'owner' AND activo"),
        ),
        Index("ix_membership_tenant_id", "tenant_id"),
        Index("ix_membership_user_id", "user_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    rol: Mapped[Role] = mapped_column(Enum(Role, name="role"), nullable=False)
    # FK a ``professional`` se agrega en C-05; deuda explícita del design.
    professional_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
