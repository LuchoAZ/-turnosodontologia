"""Tests unitarios de la resolución del tenant desde los claims (RN-TEN-03)."""

from __future__ import annotations

from uuid import UUID

import pytest
from app.core.tenant_guard import TenantClaimError, tenant_id_from_claims

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")


def test_resuelve_el_tenant_de_los_claims() -> None:
    assert tenant_id_from_claims({"tenant_id": str(TENANT_A)}) == TENANT_A


def test_sin_claim_de_tenant_no_hay_acceso() -> None:
    with pytest.raises(TenantClaimError):
        tenant_id_from_claims({"sub": "user-1"})


def test_claim_con_formato_invalido_es_rechazado() -> None:
    with pytest.raises(TenantClaimError):
        tenant_id_from_claims({"tenant_id": "no-es-un-uuid"})


def test_el_tenant_id_del_body_es_ignorado() -> None:
    claims = {"tenant_id": str(TENANT_A)}
    request_payload = {"tenant_id": str(TENANT_B), "professional_id": "x"}

    resolved = tenant_id_from_claims({**claims, "body": request_payload})

    assert resolved == TENANT_A
    assert resolved != UUID(request_payload["tenant_id"])
