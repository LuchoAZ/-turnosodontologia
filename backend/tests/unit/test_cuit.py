"""Tests unitarios de la validación de CUIT (RN-TEN-01).

Los valores esperados se calcularon a mano con el algoritmo módulo 11:
pesos (5,4,3,2,7,6,5,4,3,2) sobre los primeros 10 dígitos y
check = 11 - (suma % 11), con 11 -> 0 y 10 -> 9.
"""

from __future__ import annotations

import pytest
from app.domain.tenancy.cuit import CuitError, validate_cuit


def test_cuit_valido_se_normaliza_sin_guiones() -> None:
    assert validate_cuit("20-12345678-6") == "20123456786"


def test_cuit_valido_sin_separadores() -> None:
    assert validate_cuit("30712345671") == "30712345671"


def test_cuit_con_digito_verificador_incorrecto_es_rechazado() -> None:
    with pytest.raises(CuitError) as exc:
        validate_cuit("20-12345678-0")

    assert exc.value.motivo == "digito_verificador"


@pytest.mark.parametrize(
    "value",
    ["2012345678", "201234567890", "20-1234567A-6", "", "  "],
)
def test_cuit_con_formato_invalido_es_rechazado(value: str) -> None:
    with pytest.raises(CuitError) as exc:
        validate_cuit(value)

    assert exc.value.motivo == "formato"


def test_cuit_con_espacios_alrededor_se_normaliza() -> None:
    assert validate_cuit("  20-12345678-6  ") == "20123456786"
