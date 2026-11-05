"""Tests unitarios del contexto de tenant por transacción (D3)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from app.db.tenant_context import TENANT_SETTING_SQL, set_tenant_context

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, parameters: dict[str, Any]) -> None:
        self.calls.append((str(statement), parameters))


def test_fija_el_tenant_con_parametro_bindeado() -> None:
    connection = RecordingConnection()

    set_tenant_context(connection, TENANT_A)  # type: ignore[arg-type]

    assert len(connection.calls) == 1
    sql, params = connection.calls[0]
    assert "set_config" in sql
    assert ":tenant_id" in sql
    assert ", true)" in sql
    assert str(TENANT_A) not in sql  # nunca se interpola el valor en el SQL
    assert params == {"tenant_id": str(TENANT_A)}


def test_acepta_un_string_uuid_valido() -> None:
    connection = RecordingConnection()

    set_tenant_context(connection, str(TENANT_A))  # type: ignore[arg-type]

    assert connection.calls[0][1] == {"tenant_id": str(TENANT_A)}


def test_identificador_invalido_se_rechaza_antes_de_tocar_la_base() -> None:
    connection = RecordingConnection()

    with pytest.raises(ValueError, match="tenant_id inválido"):
        set_tenant_context(connection, "no-es-un-uuid")  # type: ignore[arg-type]

    assert connection.calls == []


def test_la_sentencia_es_transaction_local() -> None:
    # El tercer argumento de set_config en true es lo que evita el leak entre
    # transacciones del pool; si cambia a false, este test lo detecta.
    assert str(TENANT_SETTING_SQL) == "SELECT set_config('app.current_tenant', :tenant_id, true)"
