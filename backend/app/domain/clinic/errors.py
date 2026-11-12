"""Catálogo estable de errores de la configuración clínica (design D7).

Mismo shape que ``AuthError``/``RbacError``: ``{"code", "message"}``. El
frontend conmuta por ``code``. ``forbidden`` **no** vive acá: lo emite la guarda
de RBAC (C-04) y duplicarlo abriría dos fuentes para el mismo status.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class ClinicErrorCode(StrEnum):
    chair_not_found = "chair_not_found"
    chair_name_taken = "chair_name_taken"
    professional_not_found = "professional_not_found"
    professional_matricula_taken = "professional_matricula_taken"
    specialty_not_found = "specialty_not_found"
    user_not_member = "user_not_member"
    availability_not_found = "availability_not_found"
    availability_overlap = "availability_overlap"
    invalid_request = "invalid_request"


CLINIC_ERROR_STATUS: Final[dict[ClinicErrorCode, int]] = {
    ClinicErrorCode.chair_not_found: 404,
    ClinicErrorCode.chair_name_taken: 409,
    ClinicErrorCode.professional_not_found: 404,
    ClinicErrorCode.professional_matricula_taken: 409,
    ClinicErrorCode.specialty_not_found: 404,
    ClinicErrorCode.user_not_member: 422,
    ClinicErrorCode.availability_not_found: 404,
    ClinicErrorCode.availability_overlap: 409,
    ClinicErrorCode.invalid_request: 422,
}

_DEFAULT_MESSAGES: Final[dict[ClinicErrorCode, str]] = {
    ClinicErrorCode.chair_not_found: "El sillón no existe en esta clínica.",
    ClinicErrorCode.chair_name_taken: "Ya hay un sillón con ese nombre en la clínica.",
    ClinicErrorCode.professional_not_found: "El profesional no existe en esta clínica.",
    ClinicErrorCode.professional_matricula_taken: (
        "Ya hay un profesional con esa matrícula en la clínica."
    ),
    ClinicErrorCode.specialty_not_found: "La especialidad no existe en el catálogo.",
    ClinicErrorCode.user_not_member: (
        "Ese usuario no tiene una membership activa en esta clínica."
    ),
    ClinicErrorCode.availability_not_found: "La regla de disponibilidad no existe.",
    ClinicErrorCode.availability_overlap: (
        "La ventana se solapa con otra regla del mismo alcance y día."
    ),
    ClinicErrorCode.invalid_request: (
        "La petición tiene campos inválidos o no permitidos."
    ),
}


class ClinicError(Exception):
    """Error de dominio con ``code`` estable y status derivado del catálogo."""

    def __init__(self, code: ClinicErrorCode, message: str | None = None) -> None:
        self.code = code
        self.status_code = CLINIC_ERROR_STATUS[code]
        self.message = message or _DEFAULT_MESSAGES[code]
        super().__init__(self.message)

    def to_payload(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}
