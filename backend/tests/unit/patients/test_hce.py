"""Formato del número de historia clínica (task 3.2, D4).

El número es la secuencia del contador con al menos 6 dígitos: crece a 7 o más
sin romper la columna ``varchar(20)``. La secuencia en sí (integrar contra
``patient_counter``) se prueba en ``tests/integration/test_patients_service.py``.
"""

from __future__ import annotations

import pytest
from app.domain.patients.hce import formatear_numero


@pytest.mark.parametrize(
    ("secuencia", "esperado"),
    [
        (1, "000001"),
        (2, "000002"),
        (999_998, "999998"),
        (999_999, "999999"),
        (1_000_000, "1000000"),
        (12_345_678, "12345678"),
    ],
)
def test_formatear_numero_pad_a_seis_digitos_y_crece(secuencia: int, esperado: str) -> None:
    assert formatear_numero(secuencia) == esperado


def test_formatear_numero_rechaza_secuencias_no_positivas() -> None:
    for invalida in (0, -1):
        with pytest.raises(ValueError, match="arranca en 1"):
            formatear_numero(invalida)


def test_el_numero_cabe_en_la_columna() -> None:
    # ``numero_historia_clinica`` es varchar(20): 20 dígitos es el techo teórico.
    assert len(formatear_numero(10**19)) == 20
