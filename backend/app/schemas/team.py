"""DTOs de gestión de equipo (design D6, Pydantic v2).

``MemberOut`` es la lista blanca de lo que sale por HTTP: nunca
``password_hash``, ``mfa_secret``, ``tenant_id`` ni ``permissions``. El
``professional_id`` existe en el modelo desde 002 pero queda ``null`` hasta
C-05, igual que en el contrato del change.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MemberOut(BaseModel):
    """Una membership del tenant con los datos visibles de su usuario."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email: str | None
    nombre: str
    apellido: str
    rol: str
    activo: bool
    professional_id: UUID | None


class MemberListOut(BaseModel):
    """Un objeto y no un array pelado: permite agregar metadatos sin romper."""

    members: list[MemberOut]


class AssignMemberRequest(BaseModel):
    """Alta de miembro: usuario existente o creación con contraseña temporal."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    rol: str = Field(min_length=1, max_length=32)
    password_temporal: str | None = Field(default=None, min_length=12, max_length=1024)


class ChangeRoleRequest(BaseModel):
    """Cambio de rol de una membership existente."""

    model_config = ConfigDict(extra="forbid")

    rol: str = Field(min_length=1, max_length=32)


class OwnershipTransferRequest(BaseModel):
    """Transferencia de ownership: el rol que recibe el owner saliente.

    La validación de pertenencia a ``ASSIGNABLE_ROLES`` vive en el servicio para
    que falte, venga ``owner`` o un rol de portal responda ``422
    role_not_assignable`` con ``code`` estable y no el ``detail`` de Pydantic.
    """

    model_config = ConfigDict(extra="forbid")

    target_membership_id: UUID
    previous_owner_role: str | None = Field(default=None, max_length=32)
