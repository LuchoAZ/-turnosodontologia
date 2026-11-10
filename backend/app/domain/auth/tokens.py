"""Tokens opacos y su hash (design D1/D2/D7).

El token viaja en una cookie `HttpOnly`; en la base solo se guarda su SHA-256.
El hash es determinista para poder buscar por igualdad sin guardar el original.
"""

from __future__ import annotations

import hashlib
import secrets

TOKEN_BYTES = 32


def new_opaque_token() -> str:
    """Token opaco URL-safe de 32 bytes (256 bits)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hexadecimal del token: lo único que se persiste."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
