"""Contrato del hash de contraseñas (task 1.2/1.3): Argon2id y rehash."""

from __future__ import annotations

from app.config import Environment
from app.domain.auth.passwords import hash_password, needs_rehash, verify_password


def test_hash_password_uses_argon2id() -> None:
    password_hash = hash_password("correct-horse-battery-staple", Environment.test)

    assert password_hash.startswith("$argon2id$")


def test_verify_password_accepts_the_correct_password() -> None:
    password_hash = hash_password("correct-horse-battery-staple", Environment.test)

    assert verify_password("correct-horse-battery-staple", password_hash) is True


def test_verify_password_rejects_a_wrong_password() -> None:
    password_hash = hash_password("correct-horse-battery-staple", Environment.test)

    assert verify_password("wrong-password", password_hash) is False


def test_verify_password_rejects_a_malformed_hash() -> None:
    assert verify_password("whatever", "not-a-hash") is False


def test_hash_is_salted() -> None:
    first = hash_password("same-password", Environment.test)
    second = hash_password("same-password", Environment.test)

    assert first != second


def test_needs_rehash_true_for_old_parameters() -> None:
    from argon2 import PasswordHasher

    weak_hash = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1).hash("pw")

    assert needs_rehash(weak_hash, Environment.production) is True


def test_needs_rehash_false_for_current_parameters() -> None:
    password_hash = hash_password("pw", Environment.production)

    assert needs_rehash(password_hash, Environment.production) is False
