"""Modelos de configuración operativa de la clínica (C-05, design D3).

``chair`` es la unidad de capacidad que un turno reserva junto al profesional
(RN-AG-01); ``professional`` lleva la matrícula única por tenant y la duración
por defecto; ``availability_rule`` fija la ventana, el slot y los buffers
(RN-AG-03). Las tres tablas son tenant-scoped con RLS ``FORCE`` (RN-TEN-02).
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ChairTipo(StrEnum):
    """Tipos de sillón de ``04_modelo_de_datos`` (enum nativo ``chair_tipo``)."""

    consultorio = "consultorio"
    rx = "rx"
    cirugia = "cirugia"
    higiene = "higiene"
    otro = "otro"


class Chair(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Sillón: el recurso escaso que un turno reserva (RN-AG-01)."""

    __tablename__ = "chair"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nombre", name="uq_chair_tenant_nombre"),
        Index("ix_chair_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo: Mapped[ChairTipo] = mapped_column(Enum(ChairTipo, name="chair_tipo"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    ubicacion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    equipamiento: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


class Professional(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Profesional de la clínica; ``user_id`` nulo = externo sin login."""

    __tablename__ = "professional"
    __table_args__ = (
        UniqueConstraint("tenant_id", "matricula", name="uq_professional_tenant_matricula"),
        Index("ix_professional_tenant_id", "tenant_id"),
        Index("ix_professional_especialidad_id", "especialidad_id"),
        CheckConstraint(
            "duracion_default_min BETWEEN 5 AND 480",
            name="ck_professional_duracion_default_min",
        ),
        CheckConstraint(
            "porcentaje_liquidacion BETWEEN 0 AND 100",
            name="ck_professional_porcentaje_liquidacion",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    apellido: Mapped[str] = mapped_column(String(80), nullable=False)
    matricula: Mapped[str] = mapped_column(String(32), nullable=False)
    especialidad_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("specialty.id"),
        nullable=False,
    )
    porcentaje_liquidacion: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("0"),
    )
    duracion_default_min: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("30")
    )
    color_agenda: Mapped[str] = mapped_column(
        String(7), nullable=False, server_default=text("'#2563EB'")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class AvailabilityRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ventana semanal con slot y buffers; ``professional_id`` nulo = toda la clínica."""

    __tablename__ = "availability_rule"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "professional_id",
            "chair_id",
            "dia_semana",
            "fecha_desde",
            name="uq_availability_rule_scope",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_availability_rule_tenant_id", "tenant_id"),
        Index("ix_availability_rule_professional_id", "professional_id"),
        CheckConstraint("dia_semana BETWEEN 0 AND 6", name="ck_availability_rule_dia_semana"),
        CheckConstraint("hora_fin > hora_inicio", name="ck_availability_rule_ventana"),
        CheckConstraint("slot_min > 0", name="ck_availability_rule_slot_min"),
        CheckConstraint("buffer_previo_min >= 0", name="ck_availability_rule_buffer_previo"),
        CheckConstraint(
            "buffer_posterior_min >= 0", name="ck_availability_rule_buffer_posterior"
        ),
        CheckConstraint(
            "fecha_hasta IS NULL OR fecha_hasta >= fecha_desde",
            name="ck_availability_rule_fechas",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    professional_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professional.id", ondelete="CASCADE"),
        nullable=True,
    )
    chair_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chair.id", ondelete="CASCADE"),
        nullable=True,
    )
    dia_semana: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)
    slot_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    buffer_previo_min: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    buffer_posterior_min: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_practica: Mapped[str | None] = mapped_column(String(40), nullable=True)
