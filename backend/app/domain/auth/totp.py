"""TOTP de segundo factor (design D5, RN-AU-04).

La ventana es explícita — paso actual y el anterior, 30 s por paso — y el replay
se controla por paso: ``verify_code`` devuelve el paso aceptado (para que el
llamador lo persista y lo compare) o ``None`` si el código no corresponde o su
paso ya fue usado. ``user.last_totp_step`` es la barrera de credencial; el
``UPDATE ... WHERE last_totp_step < :step`` atómico vive en la capa de servicio.
"""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime

import pyotp

SECRET_BYTES = 32
STEP_SECONDS = 30
DIGITS = 6
_BACKWARD_STEPS = 1


def generate_secret() -> str:
    """Secreto base32 de 32 bytes (compatible con apps TOTP)."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def provisioning_uri(secret: str, email: str, issuer: str) -> str:
    """URI ``otpauth://`` para el alta (se devuelve una sola vez y no se loguea)."""
    return pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS).provisioning_uri(
        name=email, issuer_name=issuer
    )


def current_step(at: datetime | None = None) -> int:
    """Paso TOTP (Unix / 30 s) para ``at``."""
    moment = at if at is not None else datetime.now(UTC)
    return int(moment.timestamp()) // STEP_SECONDS


def verify_code(
    secret: str,
    code: str,
    *,
    last_used_step: int | None = None,
    at: datetime | None = None,
) -> int | None:
    """Valida ``code`` contra el paso actual y el anterior.

    Devuelve el paso aceptado —útil para el ``UPDATE`` atómico de replay— o
    ``None`` cuando el código no corresponde, ya fue usado o su paso no avanza
    con respecto a ``last_used_step``.
    """
    candidate = code.strip()
    if len(candidate) != DIGITS or not candidate.isdigit():
        return None

    totp = pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS)
    step = current_step(at)
    for offset in range(_BACKWARD_STEPS + 1):
        candidate_step = step - offset
        moment = datetime.fromtimestamp(candidate_step * STEP_SECONDS, tz=UTC)
        if totp.at(moment) != candidate:
            continue
        if last_used_step is not None and candidate_step <= last_used_step:
            return None
        return candidate_step
    return None
