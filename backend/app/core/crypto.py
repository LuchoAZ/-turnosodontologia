"""Cifrado del secreto TOTP en reposo (design D5).

Fernet con una clave derivada por HKDF-SHA256 de ``MFA_ENCRYPTION_KEY`` y del
``key_version`` de la fila: rotar la clave maestra no obliga a adivinar con qué
versión se cifró cada secreto. El valor cifrado nunca contiene el secreto en
claro y jamás se registra en logs.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_SALT = b"odontologia-saas/mfa"


def derive_key(material: str, key_version: int) -> bytes:
    """Clave Fernet (base64url de 32 bytes) para ``key_version``."""
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        info=f"mfa:{key_version}".encode(),
    ).derive(material.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def encrypt_secret(plaintext: str, material: str, *, key_version: int) -> str:
    return (
        Fernet(derive_key(material, key_version))
        .encrypt(plaintext.encode("utf-8"))
        .decode("ascii")
    )


def decrypt_secret(ciphertext: str, material: str, *, key_version: int) -> str:
    """Descifra; ``InvalidToken`` si la clave o la versión no corresponden."""
    return (
        Fernet(derive_key(material, key_version))
        .decrypt(ciphertext.encode("ascii"))
        .decode("utf-8")
    )
