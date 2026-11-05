"""Resolución del tenant activo desde los claims de la sesión (RN-TEN-03).

El contrato es deliberadamente estrecho: la función **solo** recibe los claims.
No acepta body, query ni headers, así que por construcción no puede leer un
``tenant_id`` enviado por el cliente. El borde HTTP (C-03) traduce
``TenantClaimError`` a ``401``.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID


class TenantClaimError(Exception):
    """La sesión no permite resolver un tenant: se traduce a ``401``."""


def tenant_id_from_claims(claims: Mapping[str, object]) -> UUID:
    """Devuelve el ``tenant_id`` del claim o lanza ``TenantClaimError``."""
    raw = claims.get("tenant_id")
    if raw is None:
        raise TenantClaimError("missing tenant claim")

    if isinstance(raw, UUID):
        return raw

    try:
        return UUID(str(raw))
    except (ValueError, AttributeError, TypeError) as exc:
        raise TenantClaimError("invalid tenant claim") from exc
