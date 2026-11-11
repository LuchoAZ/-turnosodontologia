"""Catálogo estable de errores de RBAC y de gestión de equipo (design D3).

Mismo shape que ``AuthError``: ``{"code", "message"}``. El frontend conmuta por
``code``; ningún error incluye ids de membership, emails, roles ajenos ni
``tenant_id``. ``invalid_request`` es el único ``422`` del contrato: lo emite el
handler de ``RequestValidationError``, de modo que en la red nunca aparece el
``detail`` de FastAPI.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class RbacErrorCode(StrEnum):
    forbidden = "forbidden"
    membership_not_found = "membership_not_found"
    membership_exists = "membership_exists"
    role_conflict = "role_conflict"
    owner_must_be_transferred = "owner_must_be_transferred"
    last_owner = "last_owner"
    ownership_changed = "ownership_changed"
    member_inactive = "member_inactive"
    member_is_actor = "member_is_actor"
    member_already_owner = "member_already_owner"
    role_not_assignable = "role_not_assignable"
    invalid_request = "invalid_request"
    capability_pending = "capability_pending"


RBAC_ERROR_STATUS: Final[dict[RbacErrorCode, int]] = {
    RbacErrorCode.forbidden: 403,
    RbacErrorCode.membership_not_found: 404,
    RbacErrorCode.membership_exists: 409,
    RbacErrorCode.role_conflict: 409,
    RbacErrorCode.owner_must_be_transferred: 409,
    RbacErrorCode.last_owner: 409,
    RbacErrorCode.ownership_changed: 409,
    RbacErrorCode.member_inactive: 409,
    RbacErrorCode.member_is_actor: 409,
    RbacErrorCode.member_already_owner: 409,
    RbacErrorCode.role_not_assignable: 422,
    RbacErrorCode.invalid_request: 422,
    RbacErrorCode.capability_pending: 501,
}

_DEFAULT_MESSAGES: Final[dict[RbacErrorCode, str]] = {
    RbacErrorCode.forbidden: "No tenés permiso para realizar esta operación.",
    RbacErrorCode.membership_not_found: "El miembro no existe en esta clínica.",
    RbacErrorCode.membership_exists: "Ese usuario ya tiene ese rol en la clínica.",
    RbacErrorCode.role_conflict: "El rol elegido choca con otra membership del mismo usuario.",
    RbacErrorCode.owner_must_be_transferred: "El rol owner no se asigna: se transfiere.",
    RbacErrorCode.last_owner: "La clínica no puede quedar sin un owner activo.",
    RbacErrorCode.ownership_changed: "El ownership cambió; reintentá la operación.",
    RbacErrorCode.member_inactive: "Ese miembro está dado de baja.",
    RbacErrorCode.member_is_actor: "No podés hacer esta operación sobre tu propia membership.",
    RbacErrorCode.member_already_owner: "Ese miembro ya es owner de la clínica.",
    RbacErrorCode.role_not_assignable: "Ese rol no se puede asignar por esta vía.",
    RbacErrorCode.invalid_request: "La petición tiene campos inválidos o no permitidos.",
    RbacErrorCode.capability_pending: "La capacidad todavía no está implementada.",
}


class RbacError(Exception):
    """Error de dominio con ``code`` estable y status derivado del catálogo."""

    def __init__(self, code: RbacErrorCode, message: str | None = None) -> None:
        self.code = code
        self.status_code = RBAC_ERROR_STATUS[code]
        self.message = message or _DEFAULT_MESSAGES[code]
        super().__init__(self.message)

    def to_payload(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


def invalid_request() -> RbacError:
    """Error genérico para el handler de ``RequestValidationError``."""
    return RbacError(RbacErrorCode.invalid_request)
