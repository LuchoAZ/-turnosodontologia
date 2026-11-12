"""Router de la ficha demográfica del paciente (C-06, design D1).

Cada endpoint declara su permiso con ``require_permission``: la guarda corre antes
del body y antes de tocar la base, así un rol sin ``patient.*`` recibe ``403`` sin
filtrar datos. El ``tenant_id`` sale de la sesión, nunca del body ni del query.

La sonda ``GET /api/v1/clinical/patients`` **no** se toca: exige
``clinical_record.read`` y es la frontera clínica de C-09 (RN-CMP-04).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import AuthContext
from app.db.engine import get_db
from app.domain.patients import service
from app.domain.rbac.guard import require_permission
from app.domain.rbac.matrix import Permission
from app.schemas.patients import PatientCreate, PatientListOut, PatientOut, PatientUpdate

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


@router.get("", response_model=PatientListOut)
def list_patients(
    q: str | None = Query(default=None, max_length=60),
    incluir_inactivos: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AuthContext = Depends(require_permission(Permission.patient_read)),
    db: Session = Depends(get_db),
) -> PatientListOut:
    return service.list_patients(
        db, q=q, incluir_inactivos=incluir_inactivos, limit=limit, offset=offset
    )


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: UUID,
    _: AuthContext = Depends(require_permission(Permission.patient_read)),
    db: Session = Depends(get_db),
) -> PatientOut:
    return service.get_patient(db, patient_id)


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(
    payload: PatientCreate,
    context: AuthContext = Depends(require_permission(Permission.patient_create)),
    db: Session = Depends(get_db),
) -> PatientOut:
    return service.create_patient(db, tenant_id=context.tenant_id, payload=payload)


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: UUID,
    payload: PatientUpdate,
    _: AuthContext = Depends(require_permission(Permission.patient_update)),
    db: Session = Depends(get_db),
) -> PatientOut:
    return service.update_patient(db, patient_id=patient_id, payload=payload)
