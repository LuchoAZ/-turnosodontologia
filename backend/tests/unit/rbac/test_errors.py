"""Contrato del catálogo RBAC y de sus handlers HTTP (tasks 2.1/2.2, design D3).

El frontend conmuta por ``code``, nunca por el status ni por el texto, y un
rechazo **nunca** devuelve datos del recurso (ni ids, ni emails, ni conteos).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.domain.rbac.errors import RBAC_ERROR_STATUS, RbacError, RbacErrorCode
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

EXPECTED = {
    "forbidden": 403,
    "membership_not_found": 404,
    "membership_exists": 409,
    "role_conflict": 409,
    "owner_must_be_transferred": 409,
    "last_owner": 409,
    "ownership_changed": 409,
    "member_inactive": 409,
    "member_is_actor": 409,
    "member_already_owner": 409,
    "role_not_assignable": 422,
    "invalid_request": 422,
    "capability_pending": 501,
}


def test_catalogo_mapea_cada_code_a_su_status() -> None:
    assert {code.value: status for code, status in RBAC_ERROR_STATUS.items()} == EXPECTED
    assert len(RbacErrorCode) == len(EXPECTED)


@pytest.mark.parametrize("code_value", sorted(EXPECTED))
def test_rbac_error_expone_code_status_y_payload(code_value: str) -> None:
    error = RbacError(RbacErrorCode(code_value))

    assert error.code.value == code_value
    assert error.status_code == EXPECTED[code_value]
    assert set(error.to_payload()) == {"code", "message"}
    assert error.to_payload()["code"] == code_value
    assert error.to_payload()["message"].strip() != ""


def test_el_payload_no_filtra_datos_del_recurso() -> None:
    membership_id = uuid4()
    email = "miembro@example.test"
    error = RbacError(RbacErrorCode.membership_not_found)

    payload = error.to_payload()
    assert set(payload) == {"code", "message"}
    assert str(membership_id) not in str(payload)
    assert email not in str(payload)


def test_handler_de_rbac_serializa_por_http(app: FastAPI, client: TestClient) -> None:
    @app.get("/_test/rbac-forbidden")
    async def _forbidden() -> None:
        raise RbacError(RbacErrorCode.forbidden)

    @app.get("/_test/rbac-pending")
    async def _pending() -> None:
        raise RbacError(RbacErrorCode.capability_pending)

    forbidden = client.get("/_test/rbac-forbidden")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden"
    assert set(forbidden.json()) == {"code", "message"}

    pending = client.get("/_test/rbac-pending")
    assert pending.status_code == 501
    assert pending.json()["code"] == "capability_pending"


def test_body_invalido_responde_422_con_code_estable(app: FastAPI, client: TestClient) -> None:
    """`extra="forbid"`: un campo no declarado —incluido `tenant_id`— es `422`."""

    class _Body(BaseModel):
        model_config = ConfigDict(extra="forbid")

        rol: str

    @app.post("/_test/body")
    async def _body(payload: _Body) -> dict[str, str]:
        return {"rol": payload.rol}

    extra = client.post("/_test/body", json={"rol": "front_desk", "tenant_id": str(uuid4())})
    assert extra.status_code == 422
    assert extra.json()["code"] == "invalid_request"
    assert set(extra.json()) == {"code", "message"}
    # El shape de FastAPI (`detail`) nunca sale a la red.
    assert "detail" not in extra.json()
    assert str(uuid4())[:8] not in extra.text

    missing = client.post("/_test/body", json={})
    assert missing.status_code == 422
    assert missing.json()["code"] == "invalid_request"


def test_el_422_no_eco_el_valor_recibido(app: FastAPI, client: TestClient) -> None:
    class _Body(BaseModel):
        model_config = ConfigDict(extra="forbid")

        rol: str

    @app.post("/_test/body-echo")
    async def _body(payload: _Body) -> dict[str, str]:
        return {"rol": payload.rol}

    secret = "valor-que-no-debe-volver"
    response = client.post("/_test/body-echo", json={"rol": "front_desk", "password": secret})

    assert response.status_code == 422
    assert secret not in response.text
