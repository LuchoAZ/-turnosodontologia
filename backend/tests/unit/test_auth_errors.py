"""Contrato de errores y DTOs de auth (task 1.10/1.11, design D9)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.domain.auth.errors import AUTH_ERROR_STATUS, AuthError, AuthErrorCode
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MfaCodeRequest,
    MfaEnrollStartResponse,
    SessionOut,
    SwitchTenantRequest,
    TenantOut,
    UserOut,
)
from pydantic import ValidationError

EXPECTED = {
    "invalid_credentials": 401,
    "not_authenticated": 401,
    "session_expired": 401,
    "credentials_changed": 401,
    "invalid_mfa_code": 401,
    "mfa_step_up_expired": 401,
    "mfa_required": 403,
    "mfa_enrollment_required": 403,
    "mfa_unavailable": 503,
    "tenant_not_available": 403,
    "locked": 423,
    "refresh_reuse": 401,
    "invalid_or_expired_token": 400,
}


def test_every_code_maps_to_the_design_status() -> None:
    assert {code.value: status for code, status in AUTH_ERROR_STATUS.items()} == EXPECTED


def test_mfa_challenge_is_not_a_code() -> None:
    assert "mfa_challenge" not in {code.value for code in AuthErrorCode}


@pytest.mark.parametrize("code_value", sorted(EXPECTED))
def test_auth_error_exposes_code_status_and_payload(code_value: str) -> None:
    error = AuthError(AuthErrorCode(code_value))

    assert error.code.value == code_value
    assert error.status_code == EXPECTED[code_value]
    assert set(error.to_payload()) == {"code", "message"}
    assert error.to_payload()["code"] == code_value


def test_locked_error_carries_retry_after_header() -> None:
    error = AuthError(AuthErrorCode.locked, retry_after_seconds=900)

    assert error.headers() == {"Retry-After": "900"}


def test_errors_do_not_leak_identifiers() -> None:
    email = "demo@example.test"
    error = AuthError(AuthErrorCode.invalid_credentials)

    assert email not in str(error.to_payload())
    assert email not in error.to_payload()["message"]


def test_user_out_never_serializes_secrets() -> None:
    payload = UserOut(id=uuid4(), email="demo@example.test", nombre="Demo", apellido="User")

    keys = set(payload.model_dump())
    assert keys == {"id", "email", "nombre", "apellido"}
    assert not keys & {"password_hash", "mfa_secret", "mfa_secret_key_version"}


def test_session_out_never_serializes_tokens() -> None:
    response = SessionOut(
        user=UserOut(id=uuid4(), email="demo@example.test", nombre="Demo", apellido="User"),
        tenant=TenantOut(id=uuid4(), slug="clinica-demo", nombre_comercial="Clínica Demo"),
        roles=["professional"],
        permissions=["chart.finalize", "clinical_record.read"],
        mfa_enrolled=False,
    )

    serialized = response.model_dump_json()
    for forbidden in ("password_hash", "mfa_secret", "refresh_token", "access_token", "token"):
        assert forbidden not in serialized
    assert response.permissions == ["chart.finalize", "clinical_record.read"]


def test_login_request_requires_tenant_email_and_password() -> None:
    request = LoginRequest(
        tenant_slug="clinica-demo", email="demo@example.test", password="secret"
    )

    assert request.tenant_slug == "clinica-demo"


def test_login_request_rejects_empty_tenant() -> None:
    with pytest.raises(ValidationError, match="tenant_slug"):
        LoginRequest(tenant_slug="", email="demo@example.test", password="secret")


def test_mfa_code_request_requires_six_digits() -> None:
    assert MfaCodeRequest(code="123456").code == "123456"
    with pytest.raises(ValidationError, match="code"):
        MfaCodeRequest(code="12345")


def test_switch_tenant_request_reads_destination_slug() -> None:
    assert SwitchTenantRequest(tenant_slug="clinica-b").tenant_slug == "clinica-b"


def test_enroll_start_response_exposes_secret_once() -> None:
    response = MfaEnrollStartResponse(
        secret="JBSWY3DPEHPK3PXP", otpauth_uri="otpauth://totp/x?secret=JBSWY3DPEHPK3PXP"
    )

    assert response.otpauth_uri.startswith("otpauth://")


def test_forgot_password_response_has_no_token_outside_development() -> None:
    assert ForgotPasswordResponse().model_dump() == {"token": None}
    assert ForgotPasswordResponse(token="abc").token == "abc"


def test_forgot_password_request_requires_email() -> None:
    assert ForgotPasswordRequest(email="demo@example.test").email == "demo@example.test"
