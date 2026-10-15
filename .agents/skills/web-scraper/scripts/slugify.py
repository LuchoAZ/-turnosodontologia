#!/usr/bin/env python3
"""Genera un slug kebab-case consistente para el nombre de archivo de una nota
de competidor, a partir de una URL o de un nombre.

Uso:
    python slugify.py "https://www.competidor-a.com/pricing"   -> competidor-a
    python slugify.py "Competidor A"                            -> competidor-a

El mismo input siempre produce el mismo slug, para que scrapear el mismo
competidor en corridas distintas pise el mismo archivo en discovery/sources/
en vez de duplicarlo.
"""
import re
import sys
from urllib.parse import urlparse

_STRIP_TLDS = (
    ".com", ".io", ".ai", ".co", ".net", ".org", ".app", ".dev", ".xyz",
)


def slugify(value: str) -> str:
    value = value.strip()

    if "://" in value or value.startswith("www."):
        parsed = urlparse(value if "://" in value else f"https://{value}")
        host = parsed.netloc or parsed.path
        host = re.sub(r"^www\.", "", host)
        for tld in _STRIP_TLDS:
            if host.endswith(tld):
                host = host[: -len(tld)]
                break
        value = host

    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    value = re.sub(r"-{2,}", "-", value)

    return value or "sin-nombre"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python slugify.py '<url-o-nombre>'", file=sys.stderr)
        sys.exit(1)
    print(slugify(sys.argv[1]))
