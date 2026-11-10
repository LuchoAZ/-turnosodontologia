"""Modelos de sesión, refresh rotativo, MFA y recuperación (C-03)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class RefreshEstado(StrEnum):
    activo = "activo"
    rotado = "rotado"
    revocado = "revocado"


class AuthEventTipo(StrEnum):
    login_success = "login_success"
    login_fail = "login_fail"
    lockout = "lockout"
    logout = "logout"
    refresh_rotated = "refresh_rotated"
    refresh_reuse = "refresh_reuse"
    mfa_success = "mfa_success"
    mfa_fail = "mfa_fail"
    mfa_enroll = "mfa_enroll"
    mfa_step_up_issued = "mfa_step_up_issued"
    password_reset_request = "password_reset_request"
    password_reset = "password_reset"
    switch_tenant = "switch_tenant"


class Session(UUIDPrimaryKeyMixin, Base):
    """Sesión de un usuario en un tenant. ``estado`` es derivado (design D2)."""

    __tablename__ = "session"
    __table_args__ = (
        Index("session_tenant_user_idx", "tenant_id", "user_id"),
        Index("session_expires_at_idx", "expires_at"),
        CheckConstraint("expires_at > created_at", name="ck_session_expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    credentials_version: Mapped[int] = mapped_column(Integer, nullable=False)
    mfa_satisfied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    last_used_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """Refresh opaco hasheado; la familia agrupa la cadena de rotaciones."""

    __tablename__ = "refresh_token"
    __table_args__ = (
        Index("refresh_token_family_idx", "family_id"),
        Index("refresh_token_tenant_session_idx", "tenant_id", "session_id"),
        Index("refresh_token_expires_at_idx", "expires_at"),
        CheckConstraint(
            "replaced_by IS NULL OR replaced_by <> id",
            name="ck_refresh_token_not_self_replaced",
        ),
        CheckConstraint(
            "estado <> 'rotado' OR (used_at IS NOT NULL AND replaced_by IS NOT NULL)",
            name="ck_refresh_token_rotated_fields",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("session.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    estado: Mapped[RefreshEstado] = mapped_column(
        Enum(RefreshEstado, name="refresh_estado"),
        nullable=False,
        server_default=text("'activo'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("refresh_token.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class AuthEvent(Base):
    """Bitácora append-only; ``odontologia_app`` solo puede insertar."""

    __tablename__ = "auth_event"
    __table_args__ = (
        Index("auth_event_tenant_created_idx", "tenant_id", "created_at"),
        Index("auth_event_user_created_idx", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    tipo: Mapped[AuthEventTipo] = mapped_column(
        Enum(AuthEventTipo, name="auth_event_tipo"), nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenant.id", ondelete="SET NULL"), nullable=True
    )
    detail: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    """Token de recuperación de un solo uso; el rol de app no ve ``created_at``."""

    __tablename__ = "password_reset_token"
    __table_args__ = (
        Index("password_reset_token_user_idx", "user_id"),
        Index("password_reset_token_expires_at_idx", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
