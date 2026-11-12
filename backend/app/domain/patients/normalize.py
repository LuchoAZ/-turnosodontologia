"""Normalización canónica de texto y teléfono (C-06, D5).

Es la única fuente de verdad de la forma que se guarda en ``apellido_norm``,
``nombre_norm`` y ``telefono_norm`` y de la que se usa para buscar y detectar
duplicados. Se calcula en la aplicación (no con ``unaccent``) porque es
determinística, testeable sin extensiones y el índice GIN trigram acelera el
``LIKE`` sobre estas columnas ya normalizadas.

No importa el ORM ni los modelos: es dominio puro.
"""

from __future__ import annotations

import unicodedata

_DIGITOS = frozenset("0123456789")


def normalizar_texto(valor: str) -> str:
    """NFKD → sin diacríticos → ``casefold`` → espacios colapsados.

    ``"  ANA   MARÍA "`` → ``"ana maria"``. La ``ñ`` se descompone en ``n`` +
    tilde combinante, así que ``"Núñez"`` → ``"nunez"``: la búsqueda por teclado
    sin acentos encuentra el apellido y el dedupe no se rompe por tipeo.
    """
    descompuesto = unicodedata.normalize("NFKD", valor)
    sin_diacriticos = "".join(
        caracter for caracter in descompuesto if not unicodedata.combining(caracter)
    )
    return " ".join(sin_diacriticos.casefold().split())


def normalizar_telefono(valor: str) -> str:
    """Deja solo los dígitos de un teléfono: ``"+54 11 5555-1234"`` → ``"541155551234"``."""
    return "".join(caracter for caracter in valor if caracter in _DIGITOS)
