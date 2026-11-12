"""Router de la agenda (change ``agendar-turno-sin-solapamiento``, D1).

Un solo endpoint en v0.1: ``POST /api/v1/appointments``. El permiso se declara con
``require_permission`` y corre **antes** del body: un rol sin ``appointment.create``
recibe ``403`` sin que el payload se parsee ni se toque la base. El ``tenant_id`` y
el ``creado_por`` salen del ``AuthContext``, nunca del cliente (RN-TEN-03).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import AuthContext
from app.db.engine import get_db
from app.domain.agenda.appointments import service
from app.domain.rbac.guard import require_permission
from app.domain.rbac.matrix import Permission
from app.schemas.appointments import AppointmentOut, CreateAppointment

router = APIRouter(prefix="/api/v1/appointments", tags=["agenda"])


@router.post("", response_model=AppointmentOut, status_code=201)
def create_appointment(
    payload: CreateAppointment,
    context: AuthContext = Depends(require_permission(Permission.appointment_create)),
    db: Session = Depends(get_db),
) -> AppointmentOut:
    return service.create_appointment(
        db, tenant_id=context.tenant_id, user_id=context.user.id, payload=payload
    )
