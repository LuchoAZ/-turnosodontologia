"""Contrato Pydantic del turno (change ``agendar-turno-sin-solapamiento``, D5).

Un único contrato: FastAPI valida con este schema y el frontend deriva sus tipos
del OpenAPI. Reglas del borde:

* ``inicio`` es ``AwareDatetime``: un RFC 3339 **sin offset** es ``422`` porque el
  servidor nunca asume su zona (RN-AG-09).
* ``fin`` y ``duracion_min`` **no** existen en el payload: los deriva el servidor
  (RN-AG-03). ``extra="forbid"`` convierte enviarlos en ``422``.
* ``estado`` y ``origen`` tampoco se aceptan: el turno nace ``pendiente`` y con
  ``origen = recepcion`` (este change no expone otros canales).
* ``tenant_id`` no se declara acá: el borde HTTP lo descarta antes de validar
  (RN-TEN-03) y la respuesta nunca lo expone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class TipoPractica(StrEnum):
    """Catálogo **code-owned** de prácticas de la agenda v0.1 (deuda de catálogo).

    La KB no define tabla de prácticas y C-05 dejó ``availability_rule.tipo_practica``
    como ``varchar(40)`` libre. Este enum es la fuente de verdad del wire y el
    matching contra la regla se hace normalizado (casefold, sin acentos), así una
    regla cargada como "Endodoncia" matchea ``endodoncia``. El catálogo
    administrable llega con facturación.
    """

    consulta = "consulta"
    control = "control"
    limpieza = "limpieza"
    endodoncia = "endodoncia"
    extraccion = "extraccion"
    cirugia = "cirugia"
    periodoncia = "periodoncia"
    ortodoncia = "ortodoncia"
    protesis = "protesis"
    implante = "implante"


class CreateAppointment(BaseModel):
    """Alta de turno: profesional + sillón + inicio; el resto lo deriva el servidor."""

    model_config = ConfigDict(extra="forbid")

    professional_id: UUID
    chair_id: UUID
    # Turno sin paciente identificado (placeholder de recepción): RN-AG-10 no aplica.
    patient_id: UUID | None = None
    inicio: AwareDatetime
    tipo_practica: TipoPractica | None = None

    @model_validator(mode="before")
    @classmethod
    def _descartar_tenant_id(cls, data: Any) -> Any:
        """``tenant_id`` en el body se **ignora**, no es ``422`` (RN-TEN-03).

        El contrato es tolerante a que un cliente viejo o un proxy agregue el
        campo: se descarta antes de validar y el tenant sale siempre de la sesión.
        Cualquier otro campo desconocido sigue siendo ``422`` por ``extra``.
        """
        if isinstance(data, dict) and "tenant_id" in data:
            limpio = dict(data)
            limpio.pop("tenant_id")
            return limpio
        return data

    @field_validator("inicio")
    @classmethod
    def _normalizar_a_utc(cls, valor: datetime) -> datetime:
        """Una sola representación en el dominio: UTC (RN-AG-09)."""
        return valor.astimezone(UTC)


class AppointmentOut(BaseModel):
    """Turno creado: sin ``tenant_id`` y con ``fin``/``duracion_min`` ya derivados."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    professional_id: UUID
    chair_id: UUID
    patient_id: UUID | None
    inicio: datetime
    fin: datetime
    duracion_min: int
    buffer_previo_min: int
    buffer_posterior_min: int
    estado: str
    origen: str
    tipo_practica: str | None = Field(default=None)
