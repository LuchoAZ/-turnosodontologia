"""Constructor de patrones de búsqueda: escape de comodines de ``LIKE`` (task 3.5, D5).

``%``, ``_`` y ``\\`` se tratan como texto literal. Sin esto, ``q=%`` devolvería
todos los pacientes y ``q=\\`` rompería el ``LIKE ... ESCAPE '\\'``.
"""

from __future__ import annotations

import pytest
from app.domain.patients.search import build_like_pattern, escape_like


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("perez", "perez"),
        ("%", "\\%"),
        ("_", "\\_"),
        ("\\", "\\\\"),
        ("50%", "50\\%"),
        ("a_b", "a\\_b"),
        ("100\\%_x", "100\\\\\\%\\_x"),
        ("", ""),
        ("' OR 1=1 --", "' OR 1=1 --"),
    ],
)
def test_escape_like_neutraliza_los_comodines(entrada: str, esperado: str) -> None:
    assert escape_like(entrada) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("perez", "%perez%"),
        ("%", "%\\%%"),
        ("_", "%\\_%"),
        ("\\", "%\\\\%"),
    ],
)
def test_el_patron_encierra_el_texto_escapado(texto: str, esperado: str) -> None:
    assert build_like_pattern(texto) == esperado


def test_ningun_patron_conserva_un_comodin_sin_escapar() -> None:
    """Un ``%`` o ``_`` del usuario nunca queda como comodín (S2.3)."""
    for texto in ("%", "_", "%%", "__", "a%_b"):
        patron = build_like_pattern(texto)
        cuerpo = patron[1:-1]
        for indice, caracter in enumerate(cuerpo):
            if caracter in "%_":
                assert cuerpo[indice - 1] == "\\", (texto, patron)
