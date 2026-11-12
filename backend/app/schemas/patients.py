"""DTOs de la ficha demográfica del paciente (C-06, D7).

``extra="forbid"`` en todo lo que entra: un ``tenant_id``, un
``numero_historia_clinica`` o un campo clínico en el body es ``422`` (el handler
global traduce ``RequestValidationError``) y nunca llega al servicio. Lo que sale
es una lista blanca: sin ``tenant_id``, ``deleted_at`` ni campos clínicos
(RN-CMP-04, S9.1).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Telefono = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
Dni = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{7,11}$")]


class Sexo(StrEnum):
    """Espeja el enum ``sexo_paciente`` de la base."""

    femenino = "femenino"
    masculino = "masculino"
    otro = "otro"
    no_declara = "no_declara"


class Domicilio(BaseModel):
    """Domicilio estructurado; se persiste tal cual en la columna JSONB."""

    model_config = ConfigDict(extra="forbid")

    calle: str | None = Field(default=None, max_length=120)
    numero: str | None = Field(default=None, max_length=20)
    localidad: str | None = Field(default=None, max_length=80)
    provincia: str | None = Field(default=None, max_length=80)
    codigo_postal: str | None = Field(default=None, max_length=12)


class PatientCreate(BaseModel):
    """Alta de paciente; ``confirmar_duplicado`` es control, no se persiste."""

    model_config = ConfigDict(extra="forbid")

    nombre: Nombre
    apellido: Nombre
    telefono: Telefono
    dni: Dni | None = None
    fecha_nacimiento: date | None = None
    sexo: Sexo | None = None
    email: EmailStr | None = None
    domicilio: Domicilio | None = None
    confirmar_duplicado: bool = False


class PatientUpdate(BaseModel):
    """Actualización parcial: ``exclude_unset`` distingue "no enviado" de ``null``."""

    model_config = ConfigDict(extra="forbid")

    nombre: Nombre | None = None
    apellido: Nombre | None = None
    telefono: Telefono | None = None
    dni: Dni | None = None
    fecha_nacimiento: date | None = None
    sexo: Sexo | None = None
    email: EmailStr | None = None
    domicilio: Domicilio | None = None


class PatientOut(BaseModel):
    """Ficha pública: sin ``tenant_id``, ``deleted_at`` ni campos clínicos."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero_historia_clinica: str
    nombre: str
    apellido: str
    dni: str | None
    fecha_nacimiento: date | None
    sexo: str | None
    telefono: str
    email: str | None
    domicilio: dict[str, Any] | None
    activo: bool
    created_at: datetime
    updated_at: datetime


class PatientListOut(BaseModel):
    patients: list[PatientOut]
    total: int


class PatientCandidate(BaseModel):
    """Coincidencia que viaja en el ``409`` sin crear la ficha."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero_historia_clinica: str
    nombre: str
    apellido: str
    dni: str | None
    telefono: str
