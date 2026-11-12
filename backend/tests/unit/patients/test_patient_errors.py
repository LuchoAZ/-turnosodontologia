"""Catálogo de errores de pacientes y payload de 409 con candidatos (task 3.3, D6).

El frontend conmuta por ``code``; ``candidatos`` solo aparece en
``patient_posible_duplicado`` y el 409 por DNI devuelve el existente. ``forbidden``
no vive acá: lo emite la guarda de RBAC.
"""

from __future__ import annotations

import pytest
from app.domain.patients.errors import (
    PATIENT_ERROR_STATUS,
    PatientError,
    PatientErrorCode,
)


def test_el_catalogo_esta_completo_con_sus_status() -> None:
    assert {code.value for code in PatientErrorCode} == {
        "patient_not_found",
        "patient_dni_duplicado",
        "patient_posible_duplicado",
        "invalid_request",
    }
    assert {
        PatientErrorCode.patient_not_found: 404,
        PatientErrorCode.patient_dni_duplicado: 409,
        PatientErrorCode.patient_posible_duplicado: 409,
        PatientErrorCode.invalid_request: 422,
    } == PATIENT_ERROR_STATUS


@pytest.mark.parametrize("code", list(PatientErrorCode))
def test_cada_error_tiene_mensaje_por_defecto_y_status(code: PatientErrorCode) -> None:
    error = PatientError(code)
    assert error.status_code == PATIENT_ERROR_STATUS[code]
    assert error.message
    assert error.to_payload() == {"code": code.value, "message": error.message}


def test_el_payload_sin_candidatos_no_incluye_la_clave() -> None:
    payload = PatientError(PatientErrorCode.patient_dni_duplicado).to_payload()
    assert "candidatos" not in payload


def test_el_posible_duplicado_incluye_los_candidatos() -> None:
    candidatos = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "numero_historia_clinica": "000001",
            "nombre": "Ana",
            "apellido": "Pérez",
            "dni": "30111222",
            "telefono": "11 5555-1234",
        }
    ]
    payload = PatientError(
        PatientErrorCode.patient_posible_duplicado, candidatos=candidatos
    ).to_payload()

    assert payload["code"] == "patient_posible_duplicado"
    assert payload["candidatos"] == candidatos


def test_el_dni_duplicado_puede_reportar_el_existente() -> None:
    existente = {
        "id": "22222222-2222-2222-2222-222222222222",
        "numero_historia_clinica": "000002",
    }
    payload = PatientError(
        PatientErrorCode.patient_dni_duplicado, candidatos=[existente]
    ).to_payload()
    assert payload["candidatos"] == [existente]
    assert payload["code"] == "patient_dni_duplicado"
