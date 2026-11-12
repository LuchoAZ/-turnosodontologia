"""Armado de búsqueda de pacientes sobre columnas normalizadas (C-06, D5).

``%``, ``_`` y ``\\`` del término del usuario se escapan y el ``LIKE`` se ejecuta
siempre con ``ESCAPE '\\'``: un ``%`` buscado es un porcentaje literal, nunca
"todos los pacientes" (S2.3). La búsqueda corre sobre ``apellido_norm``,
``nombre_norm`` y ``telefono_norm`` (ya normalizados) más el DNI exacto.
"""

from __future__ import annotations

LIKE_ESCAPE = "\\"

_ESPECIALES = frozenset({"\\", "%", "_"})


def escape_like(valor: str) -> str:
    """Neutraliza los comodines de ``LIKE`` escapándolos con ``\\``."""
    return "".join(
        f"{LIKE_ESCAPE}{caracter}" if caracter in _ESPECIALES else caracter
        for caracter in valor
    )


def build_like_pattern(valor: str) -> str:
    """Patrón ``%texto%`` con el texto escapado, listo para ``LIKE ... ESCAPE '\\'``."""
    return f"%{escape_like(valor)}%"
