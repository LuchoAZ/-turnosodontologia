"""Tokens de acceso, cookies y utilidades de sesión (design D1/D9).

El access token es un JWT ``HS256`` firmado con ``SESSION_SECRET``. Ni el access
ni el refresh viajan en el body: se emiten como cookies ``HttpOnly`` y el SPA no
puede leerlos (ni por accidente ni por XSS). El hash del refresh vive en la base;
el valor en claro solo existe en la cookie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import Response

from app.config import Settings
from app.domain.auth.errors import AuthError, AuthErrorCode

ACCESS_COOKIE = "odontologia_access"
REFRESH_COOKIE = "odontologia_refresh"
MFA_COOKIE = "odontologia_mfa"

REFRESH_COOKIE_PATH = "/api/v1/auth"
MFA_COOKIE_PATH = "/api/v1/auth/mfa"

_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["sub", "sid", "tenant_id", "mfa", "iat", "exp"]


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    tenant_id: UUID
    mfa: bool
    issued_at: datetime
    expires_at: datetime


def create_access_token(
    settings: Settings,
    *,
    user_id: UUID,
    session_id: UUID,
    tenant_id: UUID,
    mfa: bool,
    now: datetime,
) -> str:
    expires_at = now + timedelta(seconds=settings.access_token_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "tenant_id": str(tenant_id),
        "mfa": mfa,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm=_ALGORITHM)


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    """Firma válida y ``exp`` vencido → ``session_expired``; resto → ``not_authenticated``."""
    try:
        payload = jwt.decode(
            token,
            settings.session_secret,
            algorithms=[_ALGORITHM],
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError(AuthErrorCode.session_expired) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(AuthErrorCode.not_authenticated) from exc

    try:
        return AccessClaims(
            user_id=UUID(str(payload["sub"])),
            session_id=UUID(str(payload["sid"])),
            tenant_id=UUID(str(payload["tenant_id"])),
            mfa=bool(payload["mfa"]),
            issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError(AuthErrorCode.not_authenticated) from exc


def set_auth_cookies(
    response: Response,
    settings: Settings,
    *,
    access_token: str,
    refresh_token: str,
) -> None:
    secure = settings.cookie_secure
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_ttl_seconds,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.session_ttl_hours * 3600,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def clear_auth_cookies(response: Response) -> None:
    """``Max-Age=0`` en ambas cookies (mismos ``Path`` que al emitirlas)."""
    response.delete_cookie(ACCESS_COOKIE, path="/", httponly=True, samesite="lax")
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, samesite="lax"
    )


def set_mfa_cookie(response: Response, settings: Settings, *, challenge_id: str) -> None:
    response.set_cookie(
        MFA_COOKIE,
        challenge_id,
        max_age=300,
        path=MFA_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def clear_mfa_cookie(response: Response) -> None:
    response.delete_cookie(MFA_COOKIE, path=MFA_COOKIE_PATH, httponly=True, samesite="lax")


def mfa_cookie_header(settings: Settings, *, challenge_id: str) -> str:
    """``Set-Cookie`` crudo del desafío, para adjuntarlo a una respuesta de error.

    El 403 de ``mfa_required`` viaja por el ``AuthError``; armar el header acá
    mantiene un único lugar con los atributos de la cookie.
    """
    response = Response()
    set_mfa_cookie(response, settings, challenge_id=challenge_id)
    header: str = response.headers["set-cookie"]
    return header
