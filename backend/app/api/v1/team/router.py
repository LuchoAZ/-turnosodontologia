"""Router de equipo (design D6).

Cada endpoint declara su permiso con ``require_permission``: la guarda corre
antes del body y antes de tocar la base. El ``tenant_id`` nunca se lee del
cliente; sale de la sesión (``require_auth``) y se revalida con ``require_tenant``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import AuthContext, get_settings
from app.config import Settings
from app.db.engine import get_db
from app.domain.rbac.guard import require_permission
from app.domain.rbac.matrix import Permission
from app.domain.team import service
from app.schemas.team import (
    AssignMemberRequest,
    ChangeRoleRequest,
    MemberListOut,
    MemberOut,
    OwnershipTransferRequest,
)

router = APIRouter(prefix="/api/v1/team", tags=["team"])


@router.get("/members", response_model=MemberListOut)
def list_members(
    _: AuthContext = Depends(require_permission(Permission.team_read)),
    db: Session = Depends(get_db),
) -> MemberListOut:
    return MemberListOut(members=service.list_members(db))


@router.post("/members", response_model=MemberOut, status_code=201)
def create_member(
    payload: AssignMemberRequest,
    context: AuthContext = Depends(require_permission(Permission.team_create)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemberOut:
    return service.assign_member(
        db,
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        payload=payload,
        environment=settings.environment,
    )


@router.patch("/members/{membership_id}", response_model=MemberOut)
def update_member_role(
    membership_id: UUID,
    payload: ChangeRoleRequest,
    context: AuthContext = Depends(require_permission(Permission.team_update)),
    db: Session = Depends(get_db),
) -> MemberOut:
    return service.change_role(
        db,
        actor_user_id=context.user.id,
        membership_id=membership_id,
        payload=payload,
    )


@router.delete("/members/{membership_id}", status_code=204)
def deactivate_member(
    membership_id: UUID,
    context: AuthContext = Depends(require_permission(Permission.team_delete)),
    db: Session = Depends(get_db),
) -> None:
    service.deactivate_member(
        db, actor_user_id=context.user.id, membership_id=membership_id
    )


@router.post("/ownership-transfer", response_model=MemberListOut)
def transfer_ownership(
    payload: OwnershipTransferRequest,
    context: AuthContext = Depends(require_permission(Permission.ownership_transfer)),
    db: Session = Depends(get_db),
) -> MemberListOut:
    return service.transfer_ownership(
        db,
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        payload=payload,
    )
