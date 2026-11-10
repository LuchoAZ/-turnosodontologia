"""DTOs de entrada/salida de auth (Pydantic v2).

Los DTOs son la lista blanca de lo que sale por HTTP: nunca incluyen
``password_hash``, ``mfa_secret`` ni tokens. El contrato front↔back es el
OpenAPI de FastAPI, así que estas clases son la fuente de verdad del shape.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None
    nombre: str
    apellido: str


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    nombre_comercial: str


class SessionOut(BaseModel):
    """Respuesta de ``/auth/me`` y del login: perfil, tenant y roles."""

    user: UserOut
    tenant: TenantOut
    roles: list[str]
    mfa_enrolled: bool


class MfaCodeRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class MfaEnrollStartResponse(BaseModel):
    secret: str
    otpauth_uri: str


class SwitchTenantRequest(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=120)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ForgotPasswordResponse(BaseModel):
    token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=1, max_length=1024)


class ResetPasswordResponse(BaseModel):
    status: Literal["ok"] = "ok"
