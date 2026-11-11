"""Sondas reservadas de las fronteras duras clínicas (design D4, RN-CMP-04).

La frontera no es un `if rol == front_desk`: es la **ausencia del permiso** en la
matriz. Para probarla por HTTP sin inventar el dominio clínico se declaran dos
endpoints que no consultan ni crean tablas:

- `GET /clinical/patients` exige `clinical_record.read`.
- `POST /clinical/charts/finalize` exige `chart.finalize` (solo `professional`).

Quien no tiene el permiso recibe `403 forbidden` **antes** de ejecutar el
handler; quien lo tiene recibe `501 capability_pending`, porque el recurso real
llega con C-06 y se reemplaza la sonda por el endpoint definitivo con los mismos
permisos y los mismos tests negativos.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import AuthContext
from app.domain.rbac.errors import RbacError, RbacErrorCode
from app.domain.rbac.guard import require_permission
from app.domain.rbac.matrix import Permission

router = APIRouter(prefix="/api/v1/clinical", tags=["clinical"])


@router.get("/patients", status_code=501)
def list_patients(
    _: AuthContext = Depends(require_permission(Permission.clinical_record_read)),
) -> None:
    """Sonda: la lectura de pacientes pertenece a C-06."""
    raise RbacError(RbacErrorCode.capability_pending)


@router.post("/charts/finalize", status_code=501)
def finalize_chart(
    _: AuthContext = Depends(require_permission(Permission.chart_finalize)),
) -> None:
    """Sonda: el cierre de odontograma pertenece a C-06."""
    raise RbacError(RbacErrorCode.capability_pending)
