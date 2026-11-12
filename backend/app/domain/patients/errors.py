"""Catálogo estable de errores de pacientes (C-06, D6).

Mismo shape que ``AuthError``/``RbacError``/``ClinicError``: ``{"code", "message"}``
y, cuando hay coincidencias, ``candidatos``. El frontend conmuta por ``code``.
``forbidden`` **no** vive acá: lo emite la guarda de RBAC (C-04).

``candidatos`` se recibe ya serializado (``list[dict[str, object]]``) para que este
módulo no dependa de Pydantic ni de los schemas.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final


class PatientErrorCode(StrEnum):
    patient_not_found = "patient_not_found"
    patient_dni_duplicado = "patient_dni_duplicado"
    patient_posible_duplicado = "patient_posible_duplicado"
    invalid_request = "invalid_request"


PATIENT_ERROR_STATUS: Final[dict[PatientErrorCode, int]] = {
    PatientErrorCode.patient_not_found: 404,
    PatientErrorCode.patient_dni_duplicado: 409,
    PatientErrorCode.patient_posible_duplicado: 409,
    PatientErrorCode.invalid_request: 422,
}

_DEFAULT_MESSAGES: Final[dict[PatientErrorCode, str]] = {
    PatientErrorCode.patient_not_found: "El paciente no existe en esta clínica.",
    PatientErrorCode.patient_dni_duplicado: (
        "Ya hay un paciente con ese DNI en esta clínica."
    ),
    PatientErrorCode.patient_posible_duplicado: (
        "Hay pacientes con datos parecidos. Confirmá el alta si es una persona distinta."
    ),
    PatientErrorCode.invalid_request: "La petición tiene campos inválidos o no permitidos.",
}


class PatientError(Exception):
    """Error de dominio con ``code`` estable, status derivado y candidatos opcionales."""

    def __init__(
        self,
        code: PatientErrorCode,
        message: str | None = None,
        *,
        candidatos: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.status_code = PATIENT_ERROR_STATUS[code]
        self.message = message or _DEFAULT_MESSAGES[code]
        self.candidatos = candidatos
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code.value, "message": self.message}
        if self.candidatos:
            payload["candidatos"] = self.candidatos
        return payload
