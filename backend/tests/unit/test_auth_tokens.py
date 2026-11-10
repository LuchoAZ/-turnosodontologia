"""Contrato de tokens opacos y cifrado del secreto TOTP (task 1.6/1.7)."""

from __future__ import annotations

import base64
import re

import pytest
from app.core.crypto import decrypt_secret, derive_key, encrypt_secret
from app.domain.auth.tokens import hash_token, new_opaque_token
from cryptography.fernet import InvalidToken

MFA_KEY = "k" * 32
OTHER_KEY = "z" * 32
URL_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def test_new_opaque_token_is_url_safe_and_long_enough() -> None:
    token = new_opaque_token()

    assert URL_SAFE.match(token)
    decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert len(decoded) >= 32


def test_new_opaque_token_is_random() -> None:
    assert new_opaque_token() != new_opaque_token()


def test_hash_token_is_deterministic_sha256_hex() -> None:
    token = new_opaque_token()

    digest = hash_token(token)

    assert digest == hash_token(token)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert token not in digest


def test_hash_token_differs_for_different_tokens() -> None:
    assert hash_token("a") != hash_token("b")


def test_encrypt_decrypt_round_trip() -> None:
    ciphertext = encrypt_secret("JBSWY3DPEHPK3PXP", MFA_KEY, key_version=1)

    assert decrypt_secret(ciphertext, MFA_KEY, key_version=1) == "JBSWY3DPEHPK3PXP"


def test_ciphertext_does_not_contain_the_secret() -> None:
    ciphertext = encrypt_secret("JBSWY3DPEHPK3PXP", MFA_KEY, key_version=1)

    assert "JBSWY3DPEHPK3PXP" not in ciphertext


def test_ciphertext_is_randomized() -> None:
    first = encrypt_secret("JBSWY3DPEHPK3PXP", MFA_KEY, key_version=1)
    second = encrypt_secret("JBSWY3DPEHPK3PXP", MFA_KEY, key_version=1)

    assert first != second


def test_decrypt_with_another_key_fails() -> None:
    ciphertext = encrypt_secret("JBSWY3DPEHPK3PXP", MFA_KEY, key_version=1)

    with pytest.raises(InvalidToken):
        decrypt_secret(ciphertext, OTHER_KEY, key_version=1)


def test_derived_key_depends_on_the_key_version() -> None:
    assert derive_key(MFA_KEY, 1) != derive_key(MFA_KEY, 2)


def test_decrypt_with_another_key_version_fails() -> None:
    ciphertext = encrypt_secret("JBSWY3DPEHPK3PXP", MFA_KEY, key_version=1)

    with pytest.raises(InvalidToken):
        decrypt_secret(ciphertext, MFA_KEY, key_version=2)
