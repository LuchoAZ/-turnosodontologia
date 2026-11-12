"""Normalización pura de texto y teléfono para búsqueda y dedupe (task 3.1, D5).

``normalizar_texto`` produce la forma canónica que se guarda en ``*_norm``:
NFKD, sin diacríticos, ``casefold`` y espacios colapsados. ``normalizar_telefono``
deja solo dígitos. Ninguna toca la base ni SQLAlchemy: son la unidad del ciclo y
la fuente única de verdad para el seeder de integración.
"""

from __future__ import annotations

import sys

import pytest
from app.domain.patients.normalize import normalizar_telefono, normalizar_texto


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Pérez", "perez"),
        ("  ANA   MARÍA ", "ana maria"),
        ("", ""),
        ("   ", ""),
        ("ÑANDÚ", "nandu"),
        ("Núñez", "nunez"),
        ("D'Elía", "d'elia"),
        ("Güemes", "guemes"),
    ],
)
def test_normalizar_texto_quita_diacriticos_y_colapsa_espacios(
    entrada: str, esperado: str
) -> None:
    assert normalizar_texto(entrada) == esperado


def test_normalizar_texto_es_idempotente() -> None:
    once = normalizar_texto("  Jose María  Peña  ")
    assert normalizar_texto(once) == once == "jose maria pena"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("+54 11 5555-1234", "541155551234"),
        ("", ""),
        ("(011) 4444-0000", "01144440000"),
        ("sin dígitos", ""),
        ("11 5555 1234", "1155551234"),
    ],
)
def test_normalizar_telefono_deja_solo_digitos(entrada: str, esperado: str) -> None:
    assert normalizar_telefono(entrada) == esperado


def test_normalizar_telefono_es_idempotente() -> None:
    once = normalizar_telefono("+54 (11) 5555-1234")
    assert normalizar_telefono(once) == once


def test_el_modulo_de_normalizacion_no_depende_de_la_base() -> None:
    from app.domain.patients import normalize

    source = sys.modules[normalize.__name__].__loader__.get_source(normalize.__name__)  # type: ignore[attr-defined]
    assert source is not None
    assert "sqlalchemy" not in source.lower()
    assert "app.models" not in source
