"""Modelos de la ficha demográfica del paciente y del contador de HCE (C-06, D3).

``patient`` es la entidad administrativa que la agenda referencia y que recepción
administra sin ver la historia clínica (RN-CMP-04). ``patient_counter`` guarda el
último número de historia clínica emitido por tenant: solo avanza, así que un
número nunca se recicla aunque el paciente se dé de baja (RN-CLI-01).

Las columnas ``*_norm`` son una denormalización de búsqueda y dedupe calculada en
la aplicación (D5); no son campos de dominio y no se exponen en la API.
``alergias`` y ``alerta_clinica`` existen en la tabla pero **no** se exponen en
C-06: su captura es clínica y llega con C-09 (PQ-17).

Ambas tablas son tenant-scoped con RLS ``FORCE`` (RN-TEN-02).
"""

from __future__ import annotations

import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SexoPaciente(StrEnum):
    """Sexo declarado del paciente (enum nativo ``sexo_paciente``, D3)."""

    femenino = "femenino"
    masculino = "masculino"
    otro = "otro"
    no_declara = "no_declara"


class Patient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ficha demográfica del paciente, única por tenant (RN-TEN-02, RN-CLI-01)."""

    __tablename__ = "patient"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "numero_historia_clinica",
            name="uq_patient_tenant_numero_historia_clinica",
        ),
        Index("ix_patient_tenant_id", "tenant_id"),
        Index(
            "uq_patient_dni",
            "tenant_id",
            "dni",
            unique=True,
            postgresql_where=text("dni IS NOT NULL"),
        ),
        Index("ix_patient_nombre", "tenant_id", "apellido_norm", "nombre_norm"),
        Index("ix_patient_telefono", "tenant_id", "telefono_norm"),
        Index(
            "ix_patient_nombre_trgm",
            "apellido_norm",
            "nombre_norm",
            postgresql_using="gin",
            postgresql_ops={
                "apellido_norm": "gin_trgm_ops",
                "nombre_norm": "gin_trgm_ops",
            },
        ),
        Index(
            "ix_patient_activos",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Portal del paciente: nullable y sin escritores en C-06 (deuda D3).
    # FK simple porque ``user`` es global (``uq_user_email``), no tenant-scoped.
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    dni: Mapped[str | None] = mapped_column(String(11), nullable=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    apellido: Mapped[str] = mapped_column(String(80), nullable=False)
    apellido_norm: Mapped[str] = mapped_column(String(80), nullable=False)
    nombre_norm: Mapped[str] = mapped_column(String(80), nullable=False)
    fecha_nacimiento: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    sexo: Mapped[SexoPaciente | None] = mapped_column(
        Enum(SexoPaciente, name="sexo_paciente"), nullable=True
    )
    telefono: Mapped[str] = mapped_column(String(32), nullable=False)
    telefono_norm: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    domicilio: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Catálogo de obras sociales fuera de v0.1: se persiste sin FK (deuda D3).
    obra_social_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    numero_historia_clinica: Mapped[str] = mapped_column(String(20), nullable=False)
    # Columnas clínicas: existen pero NO se exponen en C-06 (PQ-17, C-09).
    alergias: Mapped[str | None] = mapped_column(Text, nullable=True)
    alerta_clinica: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PatientCounter(Base):
    """Último número de HCE emitido por tenant; solo avanza (RN-CLI-01, D4)."""

    __tablename__ = "patient_counter"

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ultimo_numero: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
