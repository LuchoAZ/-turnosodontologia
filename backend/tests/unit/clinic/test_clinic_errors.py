"""Catálogo estable de errores de la configuración clínica (task 2.1).

Mismo contrato que ``RbacError``: ``{"code", "message"}`` y status derivado del
catálogo. El test congela los nueve ``code`` y su status para que un cambio de
HTTP no se filtre silencioso al frontend.
"""

from __future__ import annotations

import pytest
from app.domain.clinic.errors import (
    CLINIC_ERROR_STATUS,
    ClinicError,
    ClinicErrorCode,
)

EXPECTED = {
    "chair_not_found": 404,
    "chair_name_taken": 409,
    "professional_not_found": 404,
    "professional_matricula_taken": 409,
    "specialty_not_found": 404,
    "user_not_member": 422,
    "availability_not_found": 404,
    "availability_overlap": 409,
    "invalid_request": 422,
}


def test_el_catalogo_tiene_los_nueve_codigos_con_su_status() -> None:
    assert {code.value for code in ClinicErrorCode} == set(EXPECTED)
    for raw, status in EXPECTED.items():
        assert CLINIC_ERROR_STATUS[ClinicErrorCode(raw)] == status


@pytest.mark.parametrize("raw", sorted(EXPECTED))
def test_cada_error_serializa_code_y_message_sin_datos_del_recurso(raw: str) -> None:
    error = ClinicError(ClinicErrorCode(raw))
    payload = error.to_payload()
    assert set(payload) == {"code", "message"}
    assert payload["code"] == raw
    assert payload["message"].strip()
    assert error.status_code == EXPECTED[raw]


def test_el_mensaje_no_ecoa_el_valor_recibido() -> None:
    error = ClinicError(ClinicErrorCode.invalid_request)
    assert "resonador" not in error.message
    assert "tenant" not in error.message.lower()


def test_un_mensaje_explicito_reemplaza_el_default() -> None:
    error = ClinicError(
        ClinicErrorCode.availability_overlap,
        "La ventana se solapa con otra regla del mismo profesional.",
    )
    assert "solapa" in error.message
    assert error.to_payload()["code"] == "availability_overlap"
