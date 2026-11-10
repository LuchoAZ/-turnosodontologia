"""Contrato TOTP (task 1.4/1.5): secreto, URI de alta, ventana y replay."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pyotp
from app.domain.auth.totp import generate_secret, provisioning_uri, verify_code

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
STEP_SECONDS = 30


def _code_at(secret: str, at: datetime) -> str:
    return pyotp.TOTP(secret).at(at)


def test_generate_secret_is_32_bytes_base32() -> None:
    secret = generate_secret()

    decoded = base64.b32decode(secret + "=" * (-len(secret) % 8))

    assert len(decoded) == 32
    assert secret == secret.upper()


def test_generate_secret_is_random() -> None:
    assert generate_secret() != generate_secret()


def test_provisioning_uri_is_otpauth_totp() -> None:
    secret = generate_secret()

    uri = provisioning_uri(secret, email="demo@example.test", issuer="Odontologia")

    assert uri.startswith("otpauth://totp/")
    assert "secret=" + secret in uri
    assert "issuer=Odontologia" in uri


def test_verify_code_accepts_current_step() -> None:
    secret = generate_secret()

    assert verify_code(secret, _code_at(secret, NOW), at=NOW) is not None


def test_verify_code_accepts_previous_step() -> None:
    secret = generate_secret()
    previous = NOW - timedelta(seconds=STEP_SECONDS)

    assert verify_code(secret, _code_at(secret, previous), at=NOW) is not None


def test_verify_code_rejects_a_code_five_minutes_old() -> None:
    secret = generate_secret()
    old = NOW - timedelta(minutes=5)

    assert verify_code(secret, _code_at(secret, old), at=NOW) is None


def test_verify_code_rejects_a_wrong_code() -> None:
    secret = generate_secret()

    assert verify_code(secret, "000000", at=NOW) is None


def test_verify_code_rejects_replay_of_last_used_step() -> None:
    secret = generate_secret()
    step = verify_code(secret, _code_at(secret, NOW), at=NOW)
    assert step is not None

    assert verify_code(secret, _code_at(secret, NOW), at=NOW, last_used_step=step) is None


def test_verify_code_rejects_an_older_step_than_last_used() -> None:
    secret = generate_secret()
    step = verify_code(secret, _code_at(secret, NOW), at=NOW)
    assert step is not None
    previous = NOW - timedelta(seconds=STEP_SECONDS)

    assert (
        verify_code(secret, _code_at(secret, previous), at=NOW, last_used_step=step) is None
    )
