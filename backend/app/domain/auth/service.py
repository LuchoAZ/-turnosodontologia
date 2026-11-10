"""Casos de uso de autenticación (design D3/D9).

El login resuelve el tenant por ``slug`` **antes** de fijar el contexto: el
``tenant_slug`` es el ámbito al que se pide entrar y la autorización real la da
la ``membership``. Desde el primer request autenticado, el ``tenant_id`` sale del
``sid`` de la sesión y cualquier ``tenant_id`` del body/query se ignora.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.config import Environment, Settings
from app.core.security import create_access_token, decode_access_token, mfa_cookie_header
from app.db.tenant_context import set_tenant_context
from app.domain.auth import mfa
from app.domain.auth.errors import AuthError, AuthErrorCode
from app.domain.auth.lockout import (
    LockoutState,
    is_locked,
    register_failure,
    register_success,
    retry_after_seconds,
)
from app.domain.auth.mfa import (
    MFA_REQUIRED_ROLES,
    Challenge,
    MfaPurpose,
)
from app.domain.auth.passwords import hash_password, verify_password
from app.domain.auth.tokens import hash_token, new_opaque_token
from app.domain.auth.totp import generate_secret, provisioning_uri, verify_code
from app.models.auth import PasswordResetToken, RefreshEstado, RefreshToken
from app.models.auth import Session as SessionModel
from app.models.tenancy import Membership, Role, Tenant, TenantEstado, User
from app.schemas.auth import LoginRequest, SessionOut, TenantOut, UserOut


@dataclass(frozen=True)
class IssuedSession:
    """Sesión emitida: el DTO para el body y los dos secretos para las cookies."""

    session: SessionOut
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class ResolvedSession:
    """Lo único que devuelve el resolver pre-contexto (nunca PII ni secretos)."""

    session_id: UUID
    tenant_id: UUID
    user_id: UUID
    expires_at: datetime
    revoked_at: datetime | None
    credentials_version: int


@dataclass(frozen=True)
class MfaEnrollment:
    """Alta del segundo factor: el secreto se muestra una sola vez."""

    secret: str
    otpauth_uri: str
    challenge_id: str


def register_event(
    db: Session,
    tipo: str,
    *,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Inserta un ``auth_event`` sin ``RETURNING`` (el rol de app no tiene ``SELECT``)."""
    db.execute(
        text(
            """
            INSERT INTO auth_event (tipo, user_id, tenant_id, detail)
            VALUES (:tipo, :user_id, :tenant_id, CAST(:detail AS jsonb))
            """
        ),
        {
            "tipo": tipo,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "detail": json.dumps(detail or {}),
        },
    )


def session_out(user: User, tenant: Tenant, roles: list[Role]) -> SessionOut:
    return SessionOut(
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
        roles=[role.value for role in roles],
        mfa_enrolled=user.mfa_enrolled_at is not None,
    )


def _lockout_state(user: User) -> LockoutState:
    return LockoutState(
        failed_login_count=user.failed_login_count,
        lockout_strikes=user.lockout_strikes,
        locked_until=user.locked_until,
    )


def _persist_lockout(user: User, state: LockoutState, moment: datetime) -> None:
    user.failed_login_count = state.failed_login_count
    user.lockout_strikes = state.lockout_strikes
    user.locked_until = state.locked_until
    if state.locked_until is not None and state.locked_until > moment:
        user.last_lockout_at = moment


# --- Piezas compartidas por login y step-up MFA -------------------------------


def _roles_of(db: Session, user_id: UUID) -> list[Role]:
    """Memberships activas del usuario en el tenant ya fijado en el GUC."""
    return list(
        db.execute(
            select(Membership.rol).where(
                Membership.user_id == user_id,
                Membership.activo.is_(True),
            )
        ).scalars()
    )


def _new_refresh_token(
    db: Session,
    *,
    session_id: UUID,
    tenant_id: UUID,
    expires_at: datetime,
    moment: datetime,
) -> str:
    plain = new_opaque_token()
    db.add(
        RefreshToken(
            id=uuid4(),
            session_id=session_id,
            tenant_id=tenant_id,
            family_id=uuid4(),
            token_hash=hash_token(plain),
            estado=RefreshEstado.activo,
            expires_at=expires_at,
            created_at=moment,
        )
    )
    return plain


def _access_token(
    settings: Settings,
    *,
    user_id: UUID,
    session_id: UUID,
    tenant_id: UUID,
    moment: datetime,
) -> str:
    return create_access_token(
        settings,
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        mfa=True,
        now=moment,
    )


def _load_pending_session(
    db: Session, challenge: Challenge, *, moment: datetime
) -> tuple[User, Tenant, SessionModel]:
    """Carga la sesión pendiente bajo el tenant del desafío, con la fila del user bloqueada."""
    set_tenant_context(db.connection(), challenge.tenant_id)
    session_row = db.get(SessionModel, challenge.pending_session_id)
    tenant = db.get(Tenant, challenge.tenant_id)
    user = db.execute(
        select(User).where(User.id == challenge.user_id).with_for_update()
    ).scalar_one_or_none()
    if user is None or not user.activo or tenant is None:
        raise AuthError(AuthErrorCode.not_authenticated)
    if (
        session_row is None
        or session_row.revoked_at is not None
        or session_row.expires_at <= moment
    ):
        raise AuthError(AuthErrorCode.mfa_step_up_expired)
    if session_row.user_id != user.id or session_row.tenant_id != tenant.id:
        raise AuthError(AuthErrorCode.mfa_step_up_expired)
    return user, tenant, session_row


def _claim_totp_step(db: Session, user: User, step: int) -> bool:
    """Barrera global de replay: solo avanza si el paso es estrictamente mayor."""
    result = cast(
        CursorResult[Any],
        db.execute(
            text(
                """
                UPDATE "user" SET last_totp_step = :step
                WHERE id = :id
                  AND (last_totp_step IS NULL OR last_totp_step < :step)
                """
            ),
            {"id": user.id, "step": step},
        ),
    )
    if result.rowcount != 1:
        return False
    user.last_totp_step = step
    return True


def _fail_mfa(
    db: Session,
    *,
    user: User,
    tenant_id: UUID,
    moment: datetime,
    reason: str,
) -> AuthError:
    """Fallo de segundo factor: cuenta para el lockout (S4.2) y consume el desafío."""
    state = register_failure(_lockout_state(user), moment)
    _persist_lockout(user, state, moment)
    register_event(
        db, "mfa_fail", user_id=user.id, tenant_id=tenant_id, detail={"reason": reason}
    )
    locked = is_locked(state, moment)
    if locked:
        register_event(
            db, "lockout", user_id=user.id, tenant_id=tenant_id, detail={"reason": "lockout"}
        )
    db.commit()
    if locked:
        return AuthError(
            AuthErrorCode.locked,
            retry_after_seconds=retry_after_seconds(state, moment),
        )
    return AuthError(AuthErrorCode.invalid_mfa_code)


def _complete_mfa_login(
    db: Session,
    settings: Settings,
    *,
    user: User,
    tenant: Tenant,
    session_row: SessionModel,
    roles: list[Role],
    step: int,
    moment: datetime,
) -> IssuedSession:
    """Cierra el step-up: sesión satisfecha y refresh nuevo (el caller commitea)."""
    session_row.mfa_satisfied = True
    session_row.last_used_step = step
    _persist_lockout(user, register_success(_lockout_state(user), moment), moment)
    user.last_login_at = moment
    refresh_plain = _new_refresh_token(
        db,
        session_id=session_row.id,
        tenant_id=tenant.id,
        expires_at=session_row.expires_at,
        moment=moment,
    )
    return IssuedSession(
        session=session_out(user, tenant, roles),
        access_token=_access_token(
            settings,
            user_id=user.id,
            session_id=session_row.id,
            tenant_id=tenant.id,
            moment=moment,
        ),
        refresh_token=refresh_plain,
    )


def login(
    db: Session,
    settings: Settings,
    redis: Redis,
    payload: LoginRequest,
    *,
    now: datetime | None = None,
) -> IssuedSession:
    """Autentica ``tenant_slug`` + ``email`` + ``password`` y emite la sesión."""
    moment = now or datetime.now(UTC)

    tenant = db.execute(
        select(Tenant).where(Tenant.slug == payload.tenant_slug)
    ).scalar_one_or_none()
    # La fila del usuario se bloquea (``FOR UPDATE``) para que dos intentos
    # concurrentes no puedan pisarse los contadores de lockout: la máquina de
    # estados pura corre dentro de la misma transacción que el commit.
    user = db.execute(
        select(User).where(User.email == payload.email).with_for_update()
    ).scalar_one_or_none()

    # ``LOCKED`` se evalúa ANTES de comparar el password: una cuenta bloqueada no
    # filtra si la credencial era correcta (ni por respuesta ni por timing).
    if user is not None:
        state = _lockout_state(user)
        if is_locked(state, moment):
            register_event(
                db,
                "login_fail",
                user_id=user.id,
                tenant_id=tenant.id if tenant is not None else None,
                detail={"reason": "locked"},
            )
            db.commit()
            raise AuthError(
                AuthErrorCode.locked,
                retry_after_seconds=retry_after_seconds(state, moment),
            )

    credentials_ok = (
        user is not None
        and user.activo
        and user.password_hash is not None
        and verify_password(payload.password, user.password_hash)
    )

    # Los cinco fallos de credencial comparten respuesta: no se filtra si el
    # email existe, si el usuario está activo o si el tenant existe.
    if tenant is None or user is None or not credentials_ok:
        event = "login_fail"
        detail: dict[str, Any] = {"reason": "invalid_credentials"}
        locked_state: LockoutState | None = None
        if user is not None and user.activo and user.password_hash is not None:
            new_state = register_failure(_lockout_state(user), moment)
            _persist_lockout(user, new_state, moment)
            if is_locked(new_state, moment):
                event = "lockout"
                detail = {"reason": "lockout"}
                locked_state = new_state
        register_event(
            db,
            event,
            user_id=user.id if user is not None else None,
            tenant_id=tenant.id if tenant is not None else None,
            detail=detail,
        )
        db.commit()
        if locked_state is not None:
            raise AuthError(
                AuthErrorCode.locked,
                retry_after_seconds=retry_after_seconds(locked_state, moment),
            )
        raise AuthError(AuthErrorCode.invalid_credentials)

    if tenant.estado in (TenantEstado.suspended, TenantEstado.closed):
        register_event(
            db,
            "login_fail",
            user_id=user.id,
            tenant_id=tenant.id,
            detail={"reason": "tenant_suspended"},
        )
        db.commit()
        raise AuthError(AuthErrorCode.tenant_not_available)

    # Recién ahora el contexto del tenant: `membership` está bajo RLS FORCE.
    set_tenant_context(db.connection(), tenant.id)
    roles = _roles_of(db, user.id)
    if not roles:
        register_event(
            db,
            "login_fail",
            user_id=user.id,
            tenant_id=tenant.id,
            detail={"reason": "no_active_membership"},
        )
        db.commit()
        raise AuthError(AuthErrorCode.invalid_credentials)

    if MFA_REQUIRED_ROLES.intersection(roles):
        # `owner`/`billing` no obtienen sesión sin segundo factor: se crea una
        # `session` pendiente (sin refresh ni cookies) y un desafío de un solo uso
        # en Redis. Si Redis no responde, rollback y 503 sin sesión (S4.6).
        session_id = uuid4()
        expires_at = moment + timedelta(hours=settings.session_ttl_hours)
        db.add(
            SessionModel(
                id=session_id,
                user_id=user.id,
                tenant_id=tenant.id,
                credentials_version=user.credentials_version,
                mfa_satisfied=False,
                expires_at=expires_at,
                created_at=moment,
            )
        )
        db.flush()
        purpose = (
            MfaPurpose.login_enroll
            if user.mfa_secret is None
            else MfaPurpose.login_verify
        )
        try:
            challenge_id = mfa.store_challenge(
                redis,
                Challenge(
                    purpose=purpose,
                    user_id=user.id,
                    tenant_id=tenant.id,
                    pending_session_id=session_id,
                ),
            )
        except AuthError:
            db.rollback()
            raise
        register_event(
            db,
            "mfa_step_up_issued",
            user_id=user.id,
            tenant_id=tenant.id,
            detail=mfa.mfa_event_detail(purpose),
        )
        db.commit()
        code = (
            AuthErrorCode.mfa_enrollment_required
            if purpose is MfaPurpose.login_enroll
            else AuthErrorCode.mfa_required
        )
        raise AuthError(
            code,
            extra_headers={
                "Set-Cookie": mfa_cookie_header(settings, challenge_id=challenge_id)
            },
        )

    expires_at = moment + timedelta(hours=settings.session_ttl_hours)
    session_id = uuid4()

    # Login exitoso = RESET: contadores y rachas a cero.
    _persist_lockout(user, register_success(_lockout_state(user), moment), moment)

    db.add(
        SessionModel(
            id=session_id,
            user_id=user.id,
            tenant_id=tenant.id,
            credentials_version=user.credentials_version,
            mfa_satisfied=True,
            expires_at=expires_at,
            created_at=moment,
        )
    )
    # Flush explícito: el UoW no debe decidir el orden entre `session` y
    # `refresh_token` (la FK lo exige) cuando hay autoflush por el evento.
    db.flush()
    refresh_plain = _new_refresh_token(
        db,
        session_id=session_id,
        tenant_id=tenant.id,
        expires_at=expires_at,
        moment=moment,
    )
    user.last_login_at = moment
    register_event(db, "login_success", user_id=user.id, tenant_id=tenant.id)
    db.commit()

    access_token = _access_token(
        settings,
        user_id=user.id,
        session_id=session_id,
        tenant_id=tenant.id,
        moment=moment,
    )
    return IssuedSession(
        session=session_out(user, tenant, roles),
        access_token=access_token,
        refresh_token=refresh_plain,
    )


# --- Step-up MFA (D5) --------------------------------------------------------


def verify_mfa(
    db: Session,
    settings: Settings,
    redis: Redis,
    *,
    challenge_id: str | None,
    code: str,
    now: datetime | None = None,
) -> IssuedSession:
    """Consume el desafío, valida el TOTP y emite la sesión (S4.1/S4.2)."""
    moment = now or datetime.now(UTC)
    challenge = mfa.consume_challenge(redis, challenge_id)
    if challenge.purpose not in (MfaPurpose.login_verify, MfaPurpose.switch_verify):
        raise AuthError(AuthErrorCode.mfa_step_up_expired)

    user, tenant, session_row = _load_pending_session(db, challenge, moment=moment)
    roles = _roles_of(db, user.id)
    secret = mfa.decrypt_user_secret(settings, user)
    step = verify_code(
        secret, code, last_used_step=user.last_totp_step, at=moment
    )
    if step is None or not _claim_totp_step(db, user, step):
        raise _fail_mfa(
            db, user=user, tenant_id=tenant.id, moment=moment, reason="invalid_code"
        )

    # El switch no reutiliza el factor de A: recién con el TOTP validado se
    # revoca la sesión origen y se completa la sesión pendiente de B.
    if challenge.purpose is MfaPurpose.switch_verify:
        _revoke_source_session(db, challenge.source_session_id)
        set_tenant_context(db.connection(), tenant.id)

    issued = _complete_mfa_login(
        db,
        settings,
        user=user,
        tenant=tenant,
        session_row=session_row,
        roles=roles,
        step=step,
        moment=moment,
    )
    register_event(
        db,
        "mfa_success",
        user_id=user.id,
        tenant_id=tenant.id,
        detail={"purpose": challenge.purpose.value},
    )
    if challenge.purpose is MfaPurpose.switch_verify:
        register_event(db, "switch_tenant", user_id=user.id, tenant_id=tenant.id)
    db.commit()
    return issued


def start_mfa_enrollment(
    db: Session,
    redis: Redis,
    *,
    challenge_id: str | None,
) -> MfaEnrollment:
    """Genera el secreto una sola vez y lo deja en Redis hasta la confirmación."""
    challenge = mfa.consume_challenge(redis, challenge_id)
    if challenge.purpose not in (MfaPurpose.login_enroll, MfaPurpose.switch_enroll):
        raise AuthError(AuthErrorCode.mfa_step_up_expired)

    user = db.get(User, challenge.user_id)
    if user is None or not user.activo:
        raise AuthError(AuthErrorCode.not_authenticated)

    secret = generate_secret()
    renewed = mfa.store_challenge(
        redis,
        Challenge(
            purpose=MfaPurpose.login_enroll,
            user_id=challenge.user_id,
            tenant_id=challenge.tenant_id,
            pending_session_id=challenge.pending_session_id,
        ),
    )
    mfa.store_enrollment_secret(redis, renewed, secret)
    return MfaEnrollment(
        secret=secret,
        otpauth_uri=provisioning_uri(
            secret, user.email or "", issuer=mfa.MFA_ISSUER
        ),
        challenge_id=renewed,
    )


def confirm_mfa_enrollment(
    db: Session,
    settings: Settings,
    redis: Redis,
    *,
    challenge_id: str | None,
    code: str,
    now: datetime | None = None,
) -> IssuedSession:
    """Persiste el secreto cifrado solo si el código confirma la ventana (S4.3)."""
    moment = now or datetime.now(UTC)
    challenge = mfa.consume_challenge(redis, challenge_id)
    if challenge.purpose not in (MfaPurpose.login_enroll, MfaPurpose.switch_enroll):
        raise AuthError(AuthErrorCode.mfa_step_up_expired)
    secret = mfa.consume_enrollment_secret(redis, challenge_id or "")

    user, tenant, session_row = _load_pending_session(db, challenge, moment=moment)
    roles = _roles_of(db, user.id)
    step = verify_code(
        secret, code, last_used_step=user.last_totp_step, at=moment
    )
    if step is None or not _claim_totp_step(db, user, step):
        raise _fail_mfa(
            db, user=user, tenant_id=tenant.id, moment=moment, reason="invalid_code"
        )

    user.mfa_secret = mfa.encrypt_user_secret(settings, secret)
    user.mfa_secret_key_version = mfa.MFA_SECRET_KEY_VERSION
    user.mfa_enrolled_at = moment
    if challenge.purpose is MfaPurpose.switch_enroll:
        _revoke_source_session(db, challenge.source_session_id)
        set_tenant_context(db.connection(), tenant.id)
    issued = _complete_mfa_login(
        db,
        settings,
        user=user,
        tenant=tenant,
        session_row=session_row,
        roles=roles,
        step=step,
        moment=moment,
    )
    register_event(
        db,
        "mfa_enroll",
        user_id=user.id,
        tenant_id=tenant.id,
        detail={"purpose": challenge.purpose.value},
    )
    if challenge.purpose is MfaPurpose.switch_enroll:
        register_event(db, "switch_tenant", user_id=user.id, tenant_id=tenant.id)
    db.commit()
    return issued


# --- Cambio de tenant con re-emisión de sesión (RN-AU-07) --------------------


def _revoke_source_session(db: Session, source_session_id: UUID | None) -> None:
    """Revoca la sesión de origen y su familia antes de emitir la del destino."""
    if source_session_id is None:
        raise AuthError(AuthErrorCode.not_authenticated)
    source = resolve_by_sid(db, source_session_id)
    if source is None:
        raise AuthError(AuthErrorCode.not_authenticated)
    set_tenant_context(db.connection(), source.tenant_id)
    db.execute(
        text(
            """
            UPDATE refresh_token SET estado = 'revocado'
            WHERE session_id = :id AND estado <> 'revocado'
            """
        ),
        {"id": source_session_id},
    )
    db.execute(
        text("UPDATE session SET revoked_at = COALESCE(revoked_at, now()) WHERE id = :id"),
        {"id": source_session_id},
    )


def switch_tenant(
    db: Session,
    settings: Settings,
    redis: Redis,
    *,
    user_id: UUID,
    source_session_id: UUID,
    source_tenant_id: UUID,
    tenant_slug: str,
    now: datetime | None = None,
) -> IssuedSession:
    """Excepción explícita de RN-TEN-03: el destino sale del body y se valida.

    Sin membership activa responde ``403 tenant_not_available`` sin tocar A. Con
    ``owner``/``billing`` en el destino responde el 403 de step-up y A sigue
    vigente hasta que ``mfa/verify`` (o ``enroll/confirm``) complete (S6.5).
    """
    moment = now or datetime.now(UTC)
    target = db.execute(
        select(Tenant).where(Tenant.slug == tenant_slug)
    ).scalar_one_or_none()
    if target is None or target.estado in (TenantEstado.suspended, TenantEstado.closed):
        raise AuthError(AuthErrorCode.tenant_not_available)

    # GUC del destino: `membership` está bajo RLS FORCE y el de A no la ve.
    set_tenant_context(db.connection(), target.id)
    roles = _roles_of(db, user_id)
    if not roles:
        db.rollback()
        set_tenant_context(db.connection(), source_tenant_id)
        raise AuthError(AuthErrorCode.tenant_not_available)

    user = db.get(User, user_id)
    if user is None or not user.activo:
        raise AuthError(AuthErrorCode.not_authenticated)

    expires_at = moment + timedelta(hours=settings.session_ttl_hours)
    if MFA_REQUIRED_ROLES.intersection(roles):
        pending_id = uuid4()
        db.add(
            SessionModel(
                id=pending_id,
                user_id=user_id,
                tenant_id=target.id,
                credentials_version=user.credentials_version,
                mfa_satisfied=False,
                expires_at=expires_at,
                created_at=moment,
            )
        )
        db.flush()
        purpose = (
            MfaPurpose.switch_enroll
            if user.mfa_secret is None
            else MfaPurpose.switch_verify
        )
        try:
            challenge_id = mfa.store_challenge(
                redis,
                Challenge(
                    purpose=purpose,
                    user_id=user_id,
                    tenant_id=target.id,
                    pending_session_id=pending_id,
                    source_session_id=source_session_id,
                ),
            )
        except AuthError:
            db.rollback()
            set_tenant_context(db.connection(), source_tenant_id)
            raise
        register_event(
            db,
            "mfa_step_up_issued",
            user_id=user_id,
            tenant_id=target.id,
            detail=mfa.mfa_event_detail(purpose),
        )
        db.commit()
        code = (
            AuthErrorCode.mfa_enrollment_required
            if purpose is MfaPurpose.switch_enroll
            else AuthErrorCode.mfa_required
        )
        raise AuthError(
            code,
            extra_headers={
                "Set-Cookie": mfa_cookie_header(settings, challenge_id=challenge_id)
            },
        )

    _revoke_source_session(db, source_session_id)
    set_tenant_context(db.connection(), target.id)

    session_id = uuid4()
    db.add(
        SessionModel(
            id=session_id,
            user_id=user_id,
            tenant_id=target.id,
            credentials_version=user.credentials_version,
            mfa_satisfied=True,
            expires_at=expires_at,
            created_at=moment,
        )
    )
    db.flush()
    refresh_plain = _new_refresh_token(
        db,
        session_id=session_id,
        tenant_id=target.id,
        expires_at=expires_at,
        moment=moment,
    )
    register_event(db, "switch_tenant", user_id=user_id, tenant_id=target.id)
    db.commit()
    return IssuedSession(
        session=session_out(user, target, roles),
        access_token=_access_token(
            settings,
            user_id=user_id,
            session_id=session_id,
            tenant_id=target.id,
            moment=moment,
        ),
        refresh_token=refresh_plain,
    )


# --- Refresh rotativo (D2) ---------------------------------------------------


def _resolved_from_row(row: Any) -> ResolvedSession:
    return ResolvedSession(
        session_id=row["session_id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        credentials_version=row["credentials_version"],
    )


def resolve_by_refresh(db: Session, token_hash: str) -> ResolvedSession | None:
    row = db.execute(
        text("SELECT * FROM auth_resolve_session_by_refresh(:token_hash)"),
        {"token_hash": token_hash},
    ).mappings().first()
    return None if row is None else _resolved_from_row(row)


def resolve_by_sid(db: Session, session_id: UUID) -> ResolvedSession | None:
    row = db.execute(
        text("SELECT * FROM auth_resolve_session_by_sid(:sid)"),
        {"sid": session_id},
    ).mappings().first()
    return None if row is None else _resolved_from_row(row)


def _roles_in_tenant(db: Session, user_id: UUID) -> list[Role]:
    return list(
        db.execute(
            select(Membership.rol).where(
                Membership.user_id == user_id,
                Membership.activo.is_(True),
            )
        ).scalars()
    )


def _revoke_family(
    db: Session,
    *,
    family_id: UUID,
    session_id: UUID,
    user_id: UUID,
    tenant_id: UUID,
    event: str,
) -> None:
    set_tenant_context(db.connection(), tenant_id)
    db.execute(
        text(
            """
            UPDATE refresh_token SET estado = 'revocado'
            WHERE family_id = :family AND estado <> 'revocado'
            """
        ),
        {"family": family_id},
    )
    db.execute(
        text("UPDATE session SET revoked_at = COALESCE(revoked_at, now()) WHERE id = :id"),
        {"id": session_id},
    )
    register_event(db, event, user_id=user_id, tenant_id=tenant_id)
    db.commit()


def _access_session_id(settings: Settings, access_token: str | None) -> UUID | None:
    """``sid`` de un access válido; ``None`` si falta, expiró o es inválido.

    Se usa solo para detectar pares de credenciales mezclados (access de una
    sesión con refresh de otra): en el refresh normal el access ya expiró.
    """
    if not access_token:
        return None
    try:
        return decode_access_token(settings, access_token).session_id
    except AuthError:
        return None


def refresh(
    db: Session,
    settings: Settings,
    refresh_token: str | None,
    *,
    access_token: str | None = None,
    now: datetime | None = None,
) -> IssuedSession:
    """Rota el refresh con arbitraje atómico; un reuso revoca toda la familia."""
    moment = now or datetime.now(UTC)
    if not refresh_token:
        raise AuthError(AuthErrorCode.not_authenticated)

    token_hash = hash_token(refresh_token)
    resolved = resolve_by_refresh(db, token_hash)
    if (
        resolved is None
        or resolved.revoked_at is not None
        or resolved.expires_at <= moment
    ):
        raise AuthError(AuthErrorCode.not_authenticated)

    access_sid = _access_session_id(settings, access_token)
    if access_sid is not None and access_sid != resolved.session_id:
        raise AuthError(AuthErrorCode.not_authenticated)

    user = db.get(User, resolved.user_id)
    if user is None or not user.activo:
        raise AuthError(AuthErrorCode.not_authenticated)

    set_tenant_context(db.connection(), resolved.tenant_id)

    if resolved.credentials_version < user.credentials_version:
        db.execute(
            text("UPDATE session SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL"),
            {"id": resolved.session_id},
        )
        db.commit()
        raise AuthError(AuthErrorCode.credentials_changed)

    current = db.execute(
        text(
            """
            SELECT id, family_id, estado::text, expires_at
            FROM refresh_token WHERE token_hash = :token_hash
            """
        ),
        {"token_hash": token_hash},
    ).mappings().first()
    if current is None or current["estado"] == "revocado":
        raise AuthError(AuthErrorCode.not_authenticated)

    new_refresh_id = uuid4()
    new_refresh_plain = new_opaque_token()
    savepoint = db.begin_nested()
    # La fila nueva se inserta primero: `replaced_by` es FK y el CHECK del
    # estado `rotado` exige las tres columnas juntas.
    db.execute(
        text(
            """
            INSERT INTO refresh_token
                (id, session_id, tenant_id, family_id, token_hash, estado,
                 expires_at, created_at)
            VALUES (:id, :session_id, :tenant_id, :family_id, :token_hash, 'activo',
                    :expires_at, :created_at)
            """
        ),
        {
            "id": new_refresh_id,
            "session_id": resolved.session_id,
            "tenant_id": resolved.tenant_id,
            "family_id": current["family_id"],
            "token_hash": hash_token(new_refresh_plain),
            "expires_at": resolved.expires_at,
            "created_at": moment,
        },
    )
    rotated = db.execute(
        text(
            """
            UPDATE refresh_token
               SET estado = 'rotado', used_at = :now, replaced_by = :new_id
             WHERE id = :id AND estado = 'activo' AND expires_at > :now
            RETURNING id
            """
        ),
        {"now": moment, "new_id": new_refresh_id, "id": current["id"]},
    ).first()
    if rotated is None:
        savepoint.rollback()
        estado_actual = db.execute(
            text("SELECT estado::text FROM refresh_token WHERE id = :id"),
            {"id": current["id"]},
        ).scalar_one_or_none()
        if estado_actual == "rotado":
            _revoke_family(
                db,
                family_id=current["family_id"],
                session_id=resolved.session_id,
                user_id=resolved.user_id,
                tenant_id=resolved.tenant_id,
                event="refresh_reuse",
            )
            raise AuthError(AuthErrorCode.refresh_reuse)
        raise AuthError(AuthErrorCode.not_authenticated)
    savepoint.commit()

    roles = _roles_in_tenant(db, resolved.user_id)
    session_state = db.execute(
        text("SELECT mfa_satisfied, expires_at FROM session WHERE id = :id"),
        {"id": resolved.session_id},
    ).mappings().one()
    tenant = db.get(Tenant, resolved.tenant_id)
    assert tenant is not None  # FK viva: la sesión existe
    register_event(
        db,
        "refresh_rotated",
        user_id=resolved.user_id,
        tenant_id=resolved.tenant_id,
    )
    db.commit()

    access_token = create_access_token(
        settings,
        user_id=resolved.user_id,
        session_id=resolved.session_id,
        tenant_id=resolved.tenant_id,
        mfa=bool(session_state["mfa_satisfied"]),
        now=moment,
    )
    return IssuedSession(
        session=session_out(user, tenant, roles),
        access_token=access_token,
        refresh_token=new_refresh_plain,
    )


# --- Logout idempotente (D2) -------------------------------------------------


def logout(
    db: Session,
    settings: Settings,
    *,
    access_token: str | None,
    refresh_token: str | None,
) -> None:
    """Revoca sesión y familia si se pueden resolver; si no, no falla (204).

    Si llegan access y refresh de sesiones distintas, el par es inconsistente:
    ``401 not_authenticated`` sin revocar ninguna de las dos (S8.6).
    """
    resolved: ResolvedSession | None = None

    if refresh_token:
        resolved = resolve_by_refresh(db, hash_token(refresh_token))

    access_sid = _access_session_id(settings, access_token)
    if resolved is not None and access_sid is not None and resolved.session_id != access_sid:
        raise AuthError(AuthErrorCode.not_authenticated)

    if resolved is None and access_sid is not None:
        resolved = resolve_by_sid(db, access_sid)

    if resolved is None:
        return

    set_tenant_context(db.connection(), resolved.tenant_id)
    db.execute(
        text(
            """
            UPDATE refresh_token SET estado = 'revocado'
            WHERE session_id = :id AND estado <> 'revocado'
            """
        ),
        {"id": resolved.session_id},
    )
    db.execute(
        text("UPDATE session SET revoked_at = COALESCE(revoked_at, now()) WHERE id = :id"),
        {"id": resolved.session_id},
    )
    register_event(
        db, "logout", user_id=resolved.user_id, tenant_id=resolved.tenant_id
    )
    db.commit()


# --- Recuperación de contraseña (D7) -----------------------------------------

RESET_TOKEN_TTL = timedelta(minutes=30)

# Fuera de estos entornos el token no viaja en la respuesta ni en el evento.
_TOKEN_EXPOSED_ENVIRONMENTS = frozenset(
    {Environment.local, Environment.development, Environment.test}
)


def forgot_password(
    db: Session, settings: Settings, *, email: str, now: datetime | None = None
) -> str | None:
    """Emite un token de un solo uso; responde igual exista o no la cuenta.

    Devuelve el token solo cuando el entorno lo permite (S5.3/S5.4); en el resto
    el token existe únicamente como hash en ``password_reset_token``.
    """
    moment = now or datetime.now(UTC)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not user.activo or user.password_hash is None:
        return None

    token = new_opaque_token()
    exposed = settings.environment in _TOKEN_EXPOSED_ENVIRONMENTS
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=moment + RESET_TOKEN_TTL,
            created_at=moment,
        )
    )
    # El token en claro solo queda registrado donde ya se expone en el body.
    register_event(
        db,
        "password_reset_request",
        user_id=user.id,
        detail={"token": token} if exposed else {},
    )
    db.commit()
    return token if exposed else None


def reset_password(
    db: Session,
    settings: Settings,
    *,
    token: str,
    new_password: str,
    now: datetime | None = None,
) -> None:
    """Consume el token una sola vez e invalida las sesiones por credencial.

    El ``UPDATE ... WHERE used_at IS NULL`` arbitra entre resets concurrentes
    (S5.5). No se enumeran ni se tocan filas ``session``: el incremento de
    ``credentials_version`` en la misma transacción es la invalidación (D4.4).
    """
    moment = now or datetime.now(UTC)
    consumed = db.execute(
        text(
            """
            UPDATE password_reset_token
               SET used_at = :now
             WHERE token_hash = :token_hash
               AND used_at IS NULL
               AND expires_at > :now
            RETURNING user_id
            """
        ),
        {"now": moment, "token_hash": hash_token(token)},
    ).mappings().first()
    if consumed is None:
        raise AuthError(AuthErrorCode.invalid_or_expired_token)

    updated = db.execute(
        text(
            """
            UPDATE "user"
               SET password_hash = :password_hash,
                   credentials_version = credentials_version + 1
             WHERE id = :id AND activo
            RETURNING id
            """
        ),
        {
            "id": consumed["user_id"],
            "password_hash": hash_password(new_password, settings.environment),
        },
    ).first()
    if updated is None:
        # El token se consumió en esta transacción: el rollback lo devuelve.
        db.rollback()
        raise AuthError(AuthErrorCode.invalid_or_expired_token)

    register_event(db, "password_reset", user_id=consumed["user_id"])
    db.commit()
