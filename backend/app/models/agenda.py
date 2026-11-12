"""Modelo del turno de la agenda (change ``agendar-turno-sin-solapamiento``, D1/D2).

``appointment`` reserva **dos recursos a la vez** —``professional_id`` y
``chair_id``— dentro de una transacción (RN-AG-01). La garantía dura contra el
doble booking es un ``EXCLUDE USING gist`` por recurso sobre el **rango bloqueado**
``[inicio - buffer_previo_min, fin + buffer_posterior_min)`` (RN-AG-02/03): los
buffers son tiempo real de higiene y también reservan. Ese constraint vive en la
migración ``007_agenda`` porque SQLAlchemy no lo expresa en ``__table_args__``;
el modelo solo declara columnas, índices y el ``CHECK`` de ``fin > inicio``.

``inicio`` y ``fin`` son ``timestamptz`` (UTC, RN-AG-09). ``duracion_min`` y los
buffers son un **snapshot** del cálculo hecho al crear el turno: si mañana cambia
la ``availability_rule``, el turno pasado no se reinterpreta (RN-AG-03).

``patient_id`` es nullable a propósito: el turno sin paciente identificado es
válido (placeholder de recepción) y RN-AG-10 solo aplica cuando hay paciente.
Las deudas de esta tabla (version/optimistic locking, recordatorios) se activan en
C-07; las columnas existen desde ahora para no migrar dos veces.
"""

from __future__ import annotations

import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Estados que liberan los recursos: un turno cancelado o ausente no bloquea el
# horario (lo replica el ``WHERE`` del EXCLUDE y el pre-chequeo de la aplicación).
ESTADOS_NO_BLOQUEANTES = ("cancelado", "no_asistio")
# Estados en los que RN-AG-10 considera que el paciente "tiene" el turno.
ESTADOS_RN_AG_10 = ("pendiente", "confirmado", "en_curso")


class AppointmentEstado(StrEnum):
    """Ciclo de vida del turno (enum nativo ``appointment_estado``)."""

    pendiente = "pendiente"
    confirmado = "confirmado"
    en_curso = "en_curso"
    atendido = "atendido"
    cancelado = "cancelado"
    no_asistio = "no_asistio"
    reprogramado = "reprogramado"


class AppointmentOrigen(StrEnum):
    """Canal de origen del turno (enum nativo ``appointment_origen``)."""

    recepcion = "recepcion"
    portal = "portal"
    whatsapp = "whatsapp"
    api = "api"
    importacion = "importacion"


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Turno del tenant: profesional + sillón + rango de tiempo (RN-AG-01)."""

    __tablename__ = "appointment"
    __table_args__ = (
        CheckConstraint("fin > inicio", name="ck_appointment_fin_posterior_a_inicio"),
        Index("ix_appointment_tenant_inicio", "tenant_id", "inicio"),
        Index("ix_appointment_patient_inicio", "patient_id", "inicio"),
        # Soporte del pre-chequeo de solape: solo los estados que bloquean.
        Index(
            "ix_appointment_estado_activos",
            "tenant_id",
            "estado",
            postgresql_where=text("estado NOT IN ('cancelado', 'no_asistio')"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Turno sin paciente identificado: placeholder válido de recepción.
    patient_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Los recursos no se borran: se desactivan (``activo = false``). El CASCADE
    # solo se dispara al borrar el tenant completo, que arrastra la agenda.
    professional_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professional.id", ondelete="CASCADE"),
        nullable=False,
    )
    chair_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chair.id", ondelete="CASCADE"),
        nullable=False,
    )
    inicio: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Snapshot de RN-AG-03: no se recalcula si luego cambia la regla.
    duracion_min: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_previo_min: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    buffer_posterior_min: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    estado: Mapped[AppointmentEstado] = mapped_column(
        Enum(AppointmentEstado, name="appointment_estado"),
        nullable=False,
        server_default=text("'pendiente'"),
    )
    # Etiqueta libre (varchar 40, igual que ``availability_rule.tipo_practica`` en
    # C-05): el catálogo de prácticas llega con facturación (deuda D3).
    tipo_practica: Mapped[str | None] = mapped_column(String(40), nullable=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    origen: Mapped[AppointmentOrigen] = mapped_column(
        Enum(AppointmentOrigen, name="appointment_origen"),
        nullable=False,
        server_default=text("'recepcion'"),
    )
    creado_por: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    recordatorio_24h_enviado_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recordatorio_2h_enviado_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelado_motivo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Defensa secundaria de C-07; el EXCLUDE es la garantía real (D2).
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
