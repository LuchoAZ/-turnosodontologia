"""Router de autenticación de plataforma (C-03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from redis import Redis
from sqlalchemy.orm import Session

from app.api.v1.deps import AuthContext, get_settings, require_tenant
from app.config import Settings
from app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    clear_mfa_cookie,
    set_auth_cookies,
    set_mfa_cookie,
)
from app.db.engine import get_db
from app.db.redis import get_redis
from app.domain.auth import service
from app.domain.auth.errors import AuthError, AuthErrorCode
from app.models.tenancy import Tenant
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MfaCodeRequest,
    MfaEnrollStartResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SessionOut,
    SwitchTenantRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me", response_model=SessionOut)
def me(
    context: AuthContext = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> SessionOut:
    tenant = db.get(Tenant, context.tenant_id)
    if tenant is None:
        raise AuthError(AuthErrorCode.not_authenticated)
    return service.session_out(context.user, tenant, context.roles)


@router.post("/login", response_model=SessionOut)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> SessionOut:
    issued = service.login(db, settings, redis, payload)
    set_auth_cookies(
        response,
        settings,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
    )
    return issued.session


@router.post("/mfa/verify", response_model=SessionOut)
def mfa_verify(
    payload: MfaCodeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> SessionOut:
    issued = service.verify_mfa(
        db,
        settings,
        redis,
        challenge_id=request.cookies.get("odontologia_mfa"),
        code=payload.code,
    )
    set_auth_cookies(
        response,
        settings,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
    )
    clear_mfa_cookie(response)
    return issued.session


@router.post("/mfa/enroll/start", response_model=MfaEnrollStartResponse)
def mfa_enroll_start(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> MfaEnrollStartResponse:
    enrollment = service.start_mfa_enrollment(
        db, redis, challenge_id=request.cookies.get("odontologia_mfa")
    )
    set_mfa_cookie(response, settings, challenge_id=enrollment.challenge_id)
    return MfaEnrollStartResponse(
        secret=enrollment.secret, otpauth_uri=enrollment.otpauth_uri
    )


@router.post("/mfa/enroll/confirm", response_model=SessionOut)
def mfa_enroll_confirm(
    payload: MfaCodeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> SessionOut:
    issued = service.confirm_mfa_enrollment(
        db,
        settings,
        redis,
        challenge_id=request.cookies.get("odontologia_mfa"),
        code=payload.code,
    )
    set_auth_cookies(
        response,
        settings,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
    )
    clear_mfa_cookie(response)
    return issued.session


@router.post("/refresh", response_model=SessionOut)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SessionOut:
    issued = service.refresh(
        db,
        settings,
        request.cookies.get(REFRESH_COOKIE),
        access_token=request.cookies.get(ACCESS_COOKIE),
    )
    set_auth_cookies(
        response,
        settings,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
    )
    return issued.session


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    service.logout(
        db,
        settings,
        access_token=request.cookies.get(ACCESS_COOKIE),
        refresh_token=request.cookies.get(REFRESH_COOKIE),
    )
    clear_auth_cookies(response)


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    response_model_exclude_none=True,
    status_code=202,
)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ForgotPasswordResponse:
    """Responde 202 siempre; el token solo se devuelve en desarrollo/test."""
    token = service.forgot_password(db, settings, email=payload.email)
    return ForgotPasswordResponse(token=token)


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResetPasswordResponse:
    service.reset_password(
        db, settings, token=payload.token, new_password=payload.new_password
    )
    return ResetPasswordResponse()


@router.post("/switch-tenant", response_model=SessionOut)
def switch_tenant(
    payload: SwitchTenantRequest,
    response: Response,
    context: AuthContext = Depends(require_tenant),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> SessionOut:
    """Única excepción a RN-TEN-03: el destino sale del body y se revalida."""
    issued = service.switch_tenant(
        db,
        settings,
        redis,
        user_id=context.user.id,
        source_session_id=context.session.id,
        source_tenant_id=context.tenant_id,
        tenant_slug=payload.tenant_slug,
    )
    set_auth_cookies(
        response,
        settings,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
    )
    return issued.session
