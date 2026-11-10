"""Desafío efímero, secreto cifrado y replay TOTP (design D5, RN-AU-04).

Este módulo no toca la base de datos ni la HTTP: solo Redis, criptografía y los
primitivos puros de TOTP. Las transiciones de sesión viven en ``service.py``.

Claves de Redis:

- ``auth:mfa:challenge:<id>`` → JSON mínimo ``{purpose, pending_session_id,
  source_session_id, user_id, tenant_id}``, TTL 300, se consume con ``GETDEL``
  (el desafío es de un solo uso, también cuando el código es incorrecto).
- ``auth:mfa:enroll:<id>`` → secreto base32 **sin confirmar**, TTL 300. Nunca se
  persiste en la base ni viaja en el payload del desafío.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from cryptography.fernet import InvalidToken
from redis import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.domain.auth.errors import AuthError, AuthErrorCode
from app.models.tenancy import Role, User

MFA_CHALLENGE_TTL_SECONDS = 300
MFA_SECRET_KEY_VERSION = 1
MFA_ISSUER = "Gestion Odontologica"
MFA_REQUIRED_ROLES = frozenset({Role.owner, Role.billing})

_CHALLENGE_PREFIX = "auth:mfa:challenge:"
_ENROLL_PREFIX = "auth:mfa:enroll:"


class MfaPurpose(StrEnum):
    login_verify = "login_verify"
    login_enroll = "login_enroll"
    switch_verify = "switch_verify"
    switch_enroll = "switch_enroll"


@dataclass(frozen=True)
class Challenge:
    """Estado mínimo del desafío; ni secretos ni PII."""

    purpose: MfaPurpose
    user_id: UUID
    tenant_id: UUID
    pending_session_id: UUID
    source_session_id: UUID | None = None


def _challenge_key(challenge_id: str) -> str:
    return f"{_CHALLENGE_PREFIX}{challenge_id}"


def _enroll_key(challenge_id: str) -> str:
    return f"{_ENROLL_PREFIX}{challenge_id}"


def challenge_ttl() -> int:
    return MFA_CHALLENGE_TTL_SECONDS


def store_challenge(redis: Redis, challenge: Challenge) -> str:
    """Persiste un desafío nuevo y devuelve su id opaco (cookie ``odontologia_mfa``)."""
    challenge_id = uuid4().hex
    payload = {
        "purpose": challenge.purpose.value,
        "user_id": str(challenge.user_id),
        "tenant_id": str(challenge.tenant_id),
        "pending_session_id": str(challenge.pending_session_id),
        "source_session_id": (
            str(challenge.source_session_id)
            if challenge.source_session_id is not None
            else None
        ),
    }
    try:
        redis.set(
            _challenge_key(challenge_id),
            json.dumps(payload),
            ex=MFA_CHALLENGE_TTL_SECONDS,
        )
    except RedisError as exc:
        raise AuthError(AuthErrorCode.mfa_unavailable) from exc
    return challenge_id


def consume_challenge(redis: Redis, challenge_id: str | None) -> Challenge:
    """``GETDEL`` atómico: un desafío se lee una sola vez, exista o no el código."""
    if not challenge_id:
        raise AuthError(AuthErrorCode.mfa_step_up_expired)
    try:
        raw = redis.getdel(_challenge_key(challenge_id))
    except RedisError as exc:
        raise AuthError(AuthErrorCode.mfa_unavailable) from exc
    if raw is None:
        raise AuthError(AuthErrorCode.mfa_step_up_expired)
    try:
        data = json.loads(raw)
        return Challenge(
            purpose=MfaPurpose(data["purpose"]),
            user_id=UUID(str(data["user_id"])),
            tenant_id=UUID(str(data["tenant_id"])),
            pending_session_id=UUID(str(data["pending_session_id"])),
            source_session_id=(
                UUID(str(data["source_session_id"]))
                if data.get("source_session_id")
                else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError(AuthErrorCode.mfa_step_up_expired) from exc


def store_enrollment_secret(redis: Redis, challenge_id: str, secret: str) -> None:
    """Secreto sin confirmar, fuera de la base y fuera del payload del desafío."""
    try:
        redis.set(_enroll_key(challenge_id), secret, ex=MFA_CHALLENGE_TTL_SECONDS)
    except RedisError as exc:
        raise AuthError(AuthErrorCode.mfa_unavailable) from exc


def consume_enrollment_secret(redis: Redis, challenge_id: str) -> str:
    try:
        raw = redis.getdel(_enroll_key(challenge_id))
    except RedisError as exc:
        raise AuthError(AuthErrorCode.mfa_unavailable) from exc
    if raw is None:
        raise AuthError(AuthErrorCode.mfa_step_up_expired)
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


def encrypt_user_secret(settings: Settings, secret: str) -> str:
    return encrypt_secret(
        secret, settings.mfa_encryption_key, key_version=MFA_SECRET_KEY_VERSION
    )


def decrypt_user_secret(settings: Settings, user: User) -> str:
    if user.mfa_secret is None or user.mfa_secret_key_version is None:
        raise AuthError(AuthErrorCode.mfa_enrollment_required)
    try:
        return decrypt_secret(
            user.mfa_secret,
            settings.mfa_encryption_key,
            key_version=user.mfa_secret_key_version,
        )
    except InvalidToken as exc:
        raise AuthError(AuthErrorCode.mfa_unavailable) from exc


def mfa_event_detail(purpose: MfaPurpose) -> dict[str, str]:
    return {"purpose": purpose.value}


__all__ = [
    "MFA_CHALLENGE_TTL_SECONDS",
    "MFA_ISSUER",
    "MFA_REQUIRED_ROLES",
    "MFA_SECRET_KEY_VERSION",
    "Challenge",
    "MfaPurpose",
    "challenge_ttl",
    "consume_challenge",
    "consume_enrollment_secret",
    "decrypt_user_secret",
    "encrypt_user_secret",
    "mfa_event_detail",
    "store_challenge",
    "store_enrollment_secret",
]
