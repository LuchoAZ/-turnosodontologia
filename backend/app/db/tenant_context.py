"""Contexto de tenant por transacción (D3 del design de C-02).

``set_config('app.current_tenant', :tenant_id, true)`` es la forma
parameterizada y **transaction-local** de fijar el GUC que leen las políticas
RLS. ``SET LOCAL app.current_tenant = '...'`` no admite parámetros bindeados:
obligaría a interpolar el UUID en el SQL.

El tercer argumento ``true`` hace que, al commit o rollback, la conexión vuelva
al pool sin contexto (sin leak entre requests).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

TENANT_SETTING_SQL = text("SELECT set_config('app.current_tenant', :tenant_id, true)")


def _normalizar_tenant_id(tenant_id: UUID | str) -> str:
    if isinstance(tenant_id, UUID):
        return str(tenant_id)
    try:
        return str(UUID(tenant_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"tenant_id inválido: {tenant_id!r}") from exc


def set_tenant_context(connection: Connection, tenant_id: UUID | str) -> None:
    """Fija el tenant activo en la transacción abierta de ``connection``."""
    valor = _normalizar_tenant_id(tenant_id)
    connection.execute(TENANT_SETTING_SQL, {"tenant_id": valor})
