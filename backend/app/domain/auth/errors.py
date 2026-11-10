"""Catálogo estable de errores de autenticación (design D9).

El frontend conmuta por ``code``, nunca por el status ni por el texto. Ningún
error incluye email, hash, token ni ``tenant_id`` ajeno. ``mfa_challenge`` no
existe como código: el estado de UI se llama ``mfaStepUp``.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final


class AuthErrorCode(StrEnum):
    invalid_credentials = "invalid_credentials"
    not_authenticated = "not_authenticated"
    session_expired = "session_expired"
    credentials_changed = "credentials_changed"
    invalid_mfa_code = "invalid_mfa_code"
    mfa_step_up_expired = "mfa_step_up_expired"
    mfa_required = "mfa_required"
    mfa_enrollment_required = "mfa_enrollment_required"
    mfa_unavailable = "mfa_unavailable"
    tenant_not_available = "tenant_not_available"
    locked = "locked"
    refresh_reuse = "refresh_reuse"
    invalid_or_expired_token = "invalid_or_expired_token"


AUTH_ERROR_STATUS: Final[dict[AuthErrorCode, int]] = {
    AuthErrorCode.invalid_credentials: 401,
    AuthErrorCode.not_authenticated: 401,
    AuthErrorCode.session_expired: 401,
    AuthErrorCode.credentials_changed: 401,
    AuthErrorCode.invalid_mfa_code: 401,
    AuthErrorCode.mfa_step_up_expired: 401,
    AuthErrorCode.mfa_required: 403,
    AuthErrorCode.mfa_enrollment_required: 403,
    AuthErrorCode.mfa_unavailable: 503,
    AuthErrorCode.tenant_not_available: 403,
    AuthErrorCode.locked: 423,
    AuthErrorCode.refresh_reuse: 401,
    AuthErrorCode.invalid_or_expired_token: 400,
}

_DEFAULT_MESSAGES: Final[dict[AuthErrorCode, str]] = {
    AuthErrorCode.invalid_credentials: "Email o contraseña incorrectos.",
    AuthErrorCode.not_authenticated: "No hay una sesión válida.",
    AuthErrorCode.session_expired: "La sesión expiró; reintentá con el refresh.",
    AuthErrorCode.credentials_changed: "La contraseña cambió; volvé a iniciar sesión.",
    AuthErrorCode.invalid_mfa_code: "El código de verificación es incorrecto.",
    AuthErrorCode.mfa_step_up_expired: "La verificación expiró; volvé a iniciar sesión.",
    AuthErrorCode.mfa_required: "Se requiere el segundo factor.",
    AuthErrorCode.mfa_enrollment_required: "Tenés que enrolar el segundo factor.",
    AuthErrorCode.mfa_unavailable: "La verificación no está disponible; reintentá en un momento.",
    AuthErrorCode.tenant_not_available: "La clínica no está disponible.",
    AuthErrorCode.locked: "La cuenta está bloqueada temporalmente.",
    AuthErrorCode.refresh_reuse: "La sesión fue revocada por seguridad.",
    AuthErrorCode.invalid_or_expired_token: "El token no es válido o expiró.",
}


class AuthError(Exception):
    """Error de dominio con ``code`` estable y status derivado del catálogo.

    ``extra_headers`` permite adjuntar el ``Set-Cookie`` del desafío MFA al 403
    (el handler de la app reenvía ``headers()`` sin cambios).
    """

    def __init__(
        self,
        code: AuthErrorCode,
        message: str | None = None,
        *,
        retry_after_seconds: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.code = code
        self.status_code = AUTH_ERROR_STATUS[code]
        self.message = message or _DEFAULT_MESSAGES[code]
        self.retry_after_seconds = retry_after_seconds
        self.extra_headers = dict(extra_headers or {})
        super().__init__(self.message)

    def to_payload(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}

    def headers(self) -> dict[str, str]:
        headers = dict(self.extra_headers)
        if self.retry_after_seconds is not None:
            headers["Retry-After"] = str(self.retry_after_seconds)
        return headers
