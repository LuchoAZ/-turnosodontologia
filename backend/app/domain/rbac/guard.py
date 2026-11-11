"""Guarda HTTP por permiso: `require_permission(*permissions)` (design D3).

La cadena es siempre `require_auth` → `require_tenant` → `require_permission`:
el guard nunca resuelve el tenant ni la membership, solo compara los roles ya
validados contra la matriz. Varios permisos se combinan con **AND** (todos) — el
criterio lo fija el endpoint, no hay OR implícito — y el permiso que falta se
registra en el log de aplicación, nunca en la respuesta.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Depends

from app.api.v1.deps import AuthContext, require_tenant
from app.domain.rbac.errors import RbacError, RbacErrorCode
from app.domain.rbac.matrix import Permission, resolve_permissions

logger = logging.getLogger(__name__)


def require_permission(*permissions: Permission) -> Callable[..., Awaitable[AuthContext]]:
    """Dependencia que exige **todos** los permisos indicados.

    Sin permisos no hay guard útil: se trata como error de programación y se
    falla cerrado (403), nunca se deja pasar.
    """
    if not permissions:
        raise ValueError("require_permission necesita al menos un permiso")

    async def _guard(context: AuthContext = Depends(require_tenant)) -> AuthContext:
        granted = resolve_permissions(context.roles)
        missing = [permission.value for permission in permissions if permission not in granted]
        if missing:
            logger.warning(
                "rbac: acceso denegado tenant=%s user=%s roles=%s faltan=%s",
                context.tenant_id,
                context.user.id,
                [role.value for role in context.roles],
                missing,
            )
            raise RbacError(RbacErrorCode.forbidden)
        return context

    return _guard
