"""Validación del CUIT de un tenant (RN-TEN-01).

Algoritmo módulo 11 sobre los primeros 10 dígitos con los pesos oficiales
``(5, 4, 3, 2, 7, 6, 5, 4, 3, 2)``; el dígito verificador es
``11 - (suma % 11)`` con ``11 -> 0`` y ``10 -> 9``.

La función es pura y no toca la base: el punto de escritura (schema/dominio de
C-03) decide qué hacer con el error.
"""

from __future__ import annotations

from typing import Literal

CuitErrorMotivo = Literal["formato", "digito_verificador"]

_PESOS: tuple[int, ...] = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_SEPARADORES = ("-", " ", ".")


class CuitError(ValueError):
    """CUIT inválido; ``motivo`` distingue formato de dígito verificador."""

    def __init__(self, motivo: CuitErrorMotivo) -> None:
        self.motivo = motivo
        super().__init__(f"CUIT inválido ({motivo})")


def _normalizar(value: str) -> str:
    limpio = value.strip()
    for separador in _SEPARADORES:
        limpio = limpio.replace(separador, "")
    return limpio


def validate_cuit(value: str) -> str:
    """Devuelve el CUIT normalizado a 11 dígitos o lanza ``CuitError``."""
    if not isinstance(value, str):
        raise CuitError("formato")

    normalizado = _normalizar(value)
    if len(normalizado) != 11 or not normalizado.isdigit():
        raise CuitError("formato")

    suma = sum(int(digito) * peso for digito, peso in zip(normalizado[:10], _PESOS, strict=True))
    check = 11 - (suma % 11)
    if check == 11:
        check = 0
    elif check == 10:
        check = 9

    if check != int(normalizado[10]):
        raise CuitError("digito_verificador")

    return normalizado
