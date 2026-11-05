"""Catálogos base: especialidades, conceptos de precio y monedas."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class Specialty(UUIDPrimaryKeyMixin, Base):
    """``tenant_id IS NULL`` = catálogo global; el tenant puede agregar las suyas."""

    __tablename__ = "specialty"
    __table_args__ = (
        Index(
            "uq_specialty_global_nombre",
            "nombre",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=True,
    )
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    duracion_default_min: Mapped[int] = mapped_column(Integer, nullable=False)


class PriceConcept(UUIDPrimaryKeyMixin, Base):
    """Nomenclador; global cuando ``tenant_id IS NULL``, override cuando no."""

    __tablename__ = "price_concept"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "codigo",
            name="uq_price_concept_tenant_codigo",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_price_concept_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=True,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    precio_default: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    alicuota_impuesto: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Currency(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "currency"

    codigo: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(40), nullable=False)
    simbolo: Mapped[str] = mapped_column(String(5), nullable=False)
    decimales: Mapped[int] = mapped_column(Integer, nullable=False)
