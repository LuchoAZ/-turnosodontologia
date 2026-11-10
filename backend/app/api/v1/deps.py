"""Dependencias compartidas de la API v1 (design D4.3).

``require_auth`` resuelve la sesión con el resolver acotado (pre-contexto), fija
el GUC del tenant y recién entonces lee ``session`` bajo RLS. ``require_tenant``
valida la ``membership`` activa con el mismo ``Session``/transacción del request
(el ``set_config(..., true)`` es transaction-local: no hay commit en el medio).
El ``tenant_id`` **nunca** sale del body ni del query del cliente: sale del
``sid`` de la sesión y se revalida contra la base.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.security import ACCESS_COOKIE, decode_access_token
from app.db.engine import get_db
from app.db.tenant_context import set_tenant_context
from app.domain.auth import service
from app.domain.auth.errors import AuthError, AuthErrorCode
from app.models.auth import Session as SessionModel
from app.models.tenancy import Membership, Role, User

_REVOKE_SESSION_SQL = text(
    "UPDATE session SET revoked_at = COALESCE(revoked_at, now()) WHERE id = :id"
)


@dataclass(frozen=True)
class AuthContext:
    """Identidad resuelta del request: nunca incluye secretos ni PII extra."""

    user: User
    session: SessionModel
    tenant_id: UUID
    roles: list[Role]
    mfa_satisfied: bool


def get_settings(request: Request) -> Settings:
    """Config validada en el lifespan (nunca se lee ``os.environ`` en el request)."""
    settings: Settings = request.app.state.settings
    return settings


def _revoke_and_reject(
    db: Session, session_id: UUID, code: AuthErrorCode
) -> AuthError:
    db.execute(_REVOKE_SESSION_SQL, {"id": session_id})
    db.commit()
    return AuthError(code)


def require_auth(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """Valida la cookie de access y deja el contexto del tenant fijado."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise AuthError(AuthErrorCode.not_authenticated)

    claims = decode_access_token(settings, token)
    resolved = service.resolve_by_sid(db, claims.session_id)
    if resolved is None or resolved.tenant_id != claims.tenant_id:
        raise AuthError(AuthErrorCode.not_authenticated)
    if resolved.revoked_at is not None or resolved.expires_at <= datetime.now(UTC):
        raise AuthError(AuthErrorCode.not_authenticated)

    set_tenant_context(db.connection(), resolved.tenant_id)

    session_row = db.get(SessionModel, resolved.session_id)
    user = db.get(User, resolved.user_id)
    if session_row is None or user is None or not user.activo:
        raise AuthError(AuthErrorCode.not_authenticated)
    # Una sesión pendiente de MFA no autentica ningún endpoint (defensa extra:
    # tampoco se emitió access token para ella).
    if not session_row.mfa_satisfied:
        raise AuthError(AuthErrorCode.not_authenticated)

    if session_row.credentials_version < user.credentials_version:
        raise _revoke_and_reject(db, resolved.session_id, AuthErrorCode.credentials_changed)

    return AuthContext(
        user=user,
        session=session_row,
        tenant_id=resolved.tenant_id,
        roles=[],
        mfa_satisfied=session_row.mfa_satisfied,
    )


def require_tenant(
    context: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
) -> AuthContext:
    """Exige ``membership`` activa en el tenant ya fijado por ``require_auth``."""
    roles = list(
        db.execute(
            select(Membership.rol).where(
                Membership.user_id == context.user.id,
                Membership.activo.is_(True),
            )
        ).scalars()
    )
    if not roles:
        raise _revoke_and_reject(db, context.session.id, AuthErrorCode.not_authenticated)

    return AuthContext(
        user=context.user,
        session=context.session,
        tenant_id=context.tenant_id,
        roles=roles,
        mfa_satisfied=context.mfa_satisfied,
    )
