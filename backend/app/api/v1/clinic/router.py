"""Router de configuración clínica (C-05, design D1).

Cada endpoint declara su permiso con ``require_permission``: la guarda corre
antes del body y antes de tocar la base. El ``tenant_id`` sale de la sesión.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import AuthContext
from app.db.engine import get_db
from app.domain.clinic import service
from app.domain.rbac.guard import require_permission
from app.domain.rbac.matrix import Permission
from app.schemas.clinic import (
    AvailabilityIn,
    AvailabilityListOut,
    AvailabilityOut,
    AvailabilityPatch,
    ChairIn,
    ChairListOut,
    ChairOut,
    ChairPatch,
    ProfessionalIn,
    ProfessionalListOut,
    ProfessionalOut,
    ProfessionalPatch,
    SpecialtyListOut,
)

router = APIRouter(prefix="/api/v1/clinic", tags=["clinic"])


@router.get("/chairs", response_model=ChairListOut)
def list_chairs(
    _: AuthContext = Depends(require_permission(Permission.chair_read)),
    db: Session = Depends(get_db),
) -> ChairListOut:
    return ChairListOut(chairs=service.list_chairs(db))


@router.post("/chairs", response_model=ChairOut, status_code=201)
def create_chair(
    payload: ChairIn,
    context: AuthContext = Depends(require_permission(Permission.chair_create)),
    db: Session = Depends(get_db),
) -> ChairOut:
    return service.create_chair(db, tenant_id=context.tenant_id, payload=payload)


@router.patch("/chairs/{chair_id}", response_model=ChairOut)
def update_chair(
    chair_id: UUID,
    payload: ChairPatch,
    _: AuthContext = Depends(require_permission(Permission.chair_update)),
    db: Session = Depends(get_db),
) -> ChairOut:
    return service.update_chair(db, chair_id=chair_id, payload=payload)


@router.delete("/chairs/{chair_id}", status_code=204)
def deactivate_chair(
    chair_id: UUID,
    _: AuthContext = Depends(require_permission(Permission.chair_delete)),
    db: Session = Depends(get_db),
) -> None:
    service.deactivate_chair(db, chair_id=chair_id)


@router.get("/professionals", response_model=ProfessionalListOut)
def list_professionals(
    _: AuthContext = Depends(require_permission(Permission.professional_read)),
    db: Session = Depends(get_db),
) -> ProfessionalListOut:
    return ProfessionalListOut(professionals=service.list_professionals(db))


@router.post("/professionals", response_model=ProfessionalOut, status_code=201)
def create_professional(
    payload: ProfessionalIn,
    context: AuthContext = Depends(require_permission(Permission.professional_create)),
    db: Session = Depends(get_db),
) -> ProfessionalOut:
    return service.create_professional(db, tenant_id=context.tenant_id, payload=payload)


@router.patch("/professionals/{professional_id}", response_model=ProfessionalOut)
def update_professional(
    professional_id: UUID,
    payload: ProfessionalPatch,
    _: AuthContext = Depends(require_permission(Permission.professional_update)),
    db: Session = Depends(get_db),
) -> ProfessionalOut:
    return service.update_professional(
        db, professional_id=professional_id, payload=payload
    )

@router.get("/specialties", response_model=SpecialtyListOut)
def list_specialties(
    context: AuthContext = Depends(require_permission(Permission.professional_read)),
    db: Session = Depends(get_db),
) -> SpecialtyListOut:
    return SpecialtyListOut(
        specialties=service.list_specialties(db, tenant_id=context.tenant_id)
    )


@router.get("/availability", response_model=AvailabilityListOut)
def list_availability(
    _: AuthContext = Depends(require_permission(Permission.professional_read)),
    db: Session = Depends(get_db),
) -> AvailabilityListOut:
    return AvailabilityListOut(availability=service.list_availability(db))


@router.post("/availability", response_model=AvailabilityOut, status_code=201)
def create_availability(
    payload: AvailabilityIn,
    context: AuthContext = Depends(require_permission(Permission.professional_update)),
    db: Session = Depends(get_db),
) -> AvailabilityOut:
    return service.create_availability(db, tenant_id=context.tenant_id, payload=payload)


@router.patch("/availability/{rule_id}", response_model=AvailabilityOut)
def update_availability(
    rule_id: UUID,
    payload: AvailabilityPatch,
    _: AuthContext = Depends(require_permission(Permission.professional_update)),
    db: Session = Depends(get_db),
) -> AvailabilityOut:
    return service.update_availability(db, rule_id=rule_id, payload=payload)
