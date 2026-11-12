"""Catálogo de errores de la agenda (change ``agendar-turno-sin-solapamiento``, D6).

Mismo shape que ``AuthError``/``RbacError``/``ClinicError``/``PatientError``:
``{"code", "message"}`` más los campos del contrato de la agenda —
``recurso`` (``professional`` | ``chair`` | ``patient``), ``motivo`` y
``rangoEnConflicto`` —. El frontend conmuta por ``code``; los campos extra existen
para que el formulario pueda señalar el recurso y el horario en conflicto sin
parsear el mensaje. ``forbidden`` **no** vive acá: lo emite la guarda de RBAC.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Final


class AgendaErrorCode(StrEnum):
    # Recurso inexistente en el tenant o de otro tenant: 404 indistinguible
    # (RN-EX-06) — nunca 403, para no filtrar la existencia de recursos ajenos.
    recurso_no_encontrado = "recurso_no_encontrado"
    recurso_inactivo = "recurso_inactivo"
    turno_solapado = "turno_solapado"
    paciente_solapado = "paciente_solapado"
    duracion_invalida = "duracion_invalida"


AGENDA_ERROR_STATUS: Final[dict[AgendaErrorCode, int]] = {
    AgendaErrorCode.recurso_no_encontrado: 404,
    AgendaErrorCode.recurso_inactivo: 409,
    AgendaErrorCode.turno_solapado: 409,
    AgendaErrorCode.paciente_solapado: 409,
    AgendaErrorCode.duracion_invalida: 409,
}

_DEFAULT_MESSAGES: Final[dict[AgendaErrorCode, str]] = {
    AgendaErrorCode.recurso_no_encontrado: (
        "El recurso no existe en esta clínica o no tenés acceso a él."
    ),
    AgendaErrorCode.recurso_inactivo: (
        "El recurso está inactivo y no se le pueden asignar turnos."
    ),
    AgendaErrorCode.turno_solapado: (
        "El horario se solapa con otro turno del mismo recurso."
    ),
    AgendaErrorCode.paciente_solapado: (
        "El paciente ya tiene un turno con ese profesional en ese horario."
    ),
    AgendaErrorCode.duracion_invalida: (
        "La duración del turno no es válida: revisá la disponibilidad y la duración "
        "por defecto del profesional."
    ),
}


class AgendaError(Exception):
    """Error de dominio con ``code`` estable, status derivado y contexto del conflicto."""

    def __init__(
        self,
        code: AgendaErrorCode,
        message: str | None = None,
        *,
        recurso: str | None = None,
        motivo: str | None = None,
        rango_en_conflicto: tuple[datetime, datetime] | None = None,
    ) -> None:
        self.code = code
        self.status_code = AGENDA_ERROR_STATUS[code]
        self.message = message or _DEFAULT_MESSAGES[code]
        self.recurso = recurso
        self.motivo = motivo
        self.rango_en_conflicto = rango_en_conflicto
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code.value, "message": self.message}
        if self.recurso is not None:
            payload["recurso"] = self.recurso
        if self.motivo is not None:
            payload["motivo"] = self.motivo
        if self.rango_en_conflicto is not None:
            inicio, fin = self.rango_en_conflicto
            payload["rangoEnConflicto"] = {
                "inicio": inicio.isoformat(),
                "fin": fin.isoformat(),
            }
        return payload
