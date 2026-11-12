"""DTOs de configuración clínica (C-05, Pydantic v2).

``extra="forbid"`` en todo lo que entra: un ``tenant_id`` en el body es
``422 invalid_request`` (el handler global traduce ``RequestValidationError``)
y nunca llega al servicio. Lo que sale es una lista blanca sin ``tenant_id``.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.clinic import ChairTipo

ColorHex = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class ChairIn(BaseModel):
    """Alta de sillón; ``activo`` nace en ``true`` y no se acepta del cliente."""

    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=60)
    tipo: ChairTipo
    ubicacion: str | None = Field(default=None, max_length=120)
    equipamiento: dict[str, Any] = Field(default_factory=dict)


class ChairPatch(BaseModel):
    """Actualización parcial; los campos ausentes no se tocan."""

    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    tipo: ChairTipo | None = None
    ubicacion: str | None = Field(default=None, max_length=120)
    equipamiento: dict[str, Any] | None = None
    activo: bool | None = None


class ChairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    tipo: str
    ubicacion: str | None
    equipamiento: dict[str, Any]
    activo: bool


class ChairListOut(BaseModel):
    chairs: list[ChairOut]


class SpecialtyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str


class SpecialtyListOut(BaseModel):
    specialties: list[SpecialtyOut]


class ProfessionalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=80)
    apellido: str = Field(min_length=1, max_length=80)
    matricula: str = Field(min_length=1, max_length=32)
    especialidad_id: UUID
    user_id: UUID | None = None
    duracion_default_min: int = Field(default=30, ge=5, le=480)
    porcentaje_liquidacion: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    color_agenda: ColorHex = "#2563EB"


class ProfessionalPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    apellido: str | None = Field(default=None, min_length=1, max_length=80)
    matricula: str | None = Field(default=None, min_length=1, max_length=32)
    especialidad_id: UUID | None = None
    user_id: UUID | None = None
    duracion_default_min: int | None = Field(default=None, ge=5, le=480)
    porcentaje_liquidacion: Decimal | None = Field(default=None, ge=0, le=100)
    color_agenda: ColorHex | None = None
    activo: bool | None = None


class ProfessionalOut(BaseModel):
    id: UUID
    user_id: UUID | None
    nombre: str
    apellido: str
    matricula: str
    especialidad: SpecialtyOut
    duracion_default_min: int
    porcentaje_liquidacion: Decimal
    color_agenda: str
    activo: bool


class ProfessionalListOut(BaseModel):
    professionals: list[ProfessionalOut]


class AvailabilityIn(BaseModel):
    """Ventana de disponibilidad; ``professional_id`` nulo = toda la clínica."""

    model_config = ConfigDict(extra="forbid")

    professional_id: UUID | None = None
    chair_id: UUID | None = None
    dia_semana: int = Field(ge=0, le=6)
    hora_inicio: time
    hora_fin: time
    slot_min: int = Field(default=30, gt=0, le=1440)
    buffer_previo_min: int = Field(default=0, ge=0, le=1440)
    buffer_posterior_min: int = Field(default=0, ge=0, le=1440)
    fecha_desde: date
    fecha_hasta: date | None = None
    tipo_practica: str | None = Field(default=None, max_length=40)


class AvailabilityPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    professional_id: UUID | None = None
    chair_id: UUID | None = None
    dia_semana: int | None = Field(default=None, ge=0, le=6)
    hora_inicio: time | None = None
    hora_fin: time | None = None
    slot_min: int | None = Field(default=None, gt=0, le=1440)
    buffer_previo_min: int | None = Field(default=None, ge=0, le=1440)
    buffer_posterior_min: int | None = Field(default=None, ge=0, le=1440)
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    tipo_practica: str | None = Field(default=None, max_length=40)


class AvailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    professional_id: UUID | None
    chair_id: UUID | None
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    slot_min: int
    buffer_previo_min: int
    buffer_posterior_min: int
    fecha_desde: date
    fecha_hasta: date | None
    tipo_practica: str | None


class AvailabilityListOut(BaseModel):
    availability: list[AvailabilityOut]
