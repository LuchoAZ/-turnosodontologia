"""Servicio de la ficha demográfica del paciente (C-06, design D4/D5).

Toda la lógica sensible vive acá:

* **Dedupe duro por DNI** sin filtrar ``deleted_at``: un DNI nunca se recicla
  (S5.6) y ``confirmar_duplicado`` no lo vence (S5.2). La consulta explícita da un
  ``409`` legible; el índice único parcial es el backstop y su ``IntegrityError``
  también se traduce a ``409``, nunca a ``500`` (S5.5).
* **Dedupe blando** por nombre completo y teléfono normalizados, solo sobre
  pacientes activos y con tope de 5 candidatos (S6.6, S6.7).
* **HCE** reservada con el upsert atómico de ``patient_counter`` dentro de la
  misma transacción del ``INSERT``: si el alta falla, no deja hueco (S4.5).

El ``tenant_id`` no se acepta en ningún DTO: lo pasa el router desde la sesión y
RLS vuelve a exigirlo en el ``WITH CHECK`` (RN-TEN-02).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.patients.errors import PatientError, PatientErrorCode
from app.domain.patients.hce import siguiente_numero_historia_clinica
from app.domain.patients.normalize import normalizar_telefono, normalizar_texto
from app.domain.patients.search import LIKE_ESCAPE, build_like_pattern
from app.models.patients import Patient, SexoPaciente
from app.schemas.patients import (
    Domicilio,
    PatientCandidate,
    PatientCreate,
    PatientListOut,
    PatientOut,
    PatientUpdate,
)

MAX_CANDIDATOS = 5


def _patient_out(patient: Patient) -> PatientOut:
    return PatientOut(
        id=patient.id,
        numero_historia_clinica=patient.numero_historia_clinica,
        nombre=patient.nombre,
        apellido=patient.apellido,
        dni=patient.dni,
        fecha_nacimiento=patient.fecha_nacimiento,
        sexo=patient.sexo.value if patient.sexo is not None else None,
        telefono=patient.telefono,
        email=patient.email,
        domicilio=patient.domicilio,
        activo=patient.activo,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


def _candidato(patient: Patient) -> dict[str, Any]:
    return PatientCandidate.model_validate(patient).model_dump(mode="json")


def _not_found() -> PatientError:
    return PatientError(PatientErrorCode.patient_not_found)


def _dni_duplicado(candidatos: list[dict[str, Any]] | None = None) -> PatientError:
    return PatientError(PatientErrorCode.patient_dni_duplicado, candidatos=candidatos)


def _posible_duplicado(candidatos: list[dict[str, Any]]) -> PatientError:
    return PatientError(PatientErrorCode.patient_posible_duplicado, candidatos=candidatos)


def _get(db: Session, patient_id: UUID) -> Patient:
    patient = db.execute(select(Patient).where(Patient.id == patient_id)).scalar_one_or_none()
    if patient is None:
        raise _not_found()
    return patient


def _existente_por_dni(db: Session, dni: str) -> dict[str, Any] | None:
    """Busca el dueño del DNI sin filtrar ``deleted_at`` (S5.6)."""
    row = db.execute(
        select(Patient.id, Patient.numero_historia_clinica).where(Patient.dni == dni)
    ).first()
    if row is None:
        return None
    return {"id": str(row.id), "numero_historia_clinica": row.numero_historia_clinica}


def list_patients(
    db: Session,
    *,
    q: str | None = None,
    incluir_inactivos: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> PatientListOut:
    """Listado y búsqueda del tenant, ordenados por apellido, nombre y HCE."""
    if not incluir_inactivos:
        filtros: list[ColumnElement[bool]] = [Patient.deleted_at.is_(None)]
    else:
        filtros = []

    termino = (q or "").strip()
    if termino:
        patron = build_like_pattern(normalizar_texto(termino))
        coincidencias: list[ColumnElement[bool]] = [
            Patient.apellido_norm.like(patron, escape=LIKE_ESCAPE),
            Patient.nombre_norm.like(patron, escape=LIKE_ESCAPE),
        ]
        if termino.isdigit():
            coincidencias.append(Patient.dni == termino)
        digitos = normalizar_telefono(termino)
        if digitos:
            coincidencias.append(
                Patient.telefono_norm.like(build_like_pattern(digitos), escape=LIKE_ESCAPE)
            )
        filtros.append(or_(*coincidencias))

    total = db.execute(select(func.count()).select_from(Patient).where(*filtros)).scalar_one()
    filas = (
        db.execute(
            select(Patient)
            .where(*filtros)
            .order_by(
                Patient.apellido,
                Patient.nombre,
                Patient.numero_historia_clinica,
            )
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return PatientListOut(patients=[_patient_out(patient) for patient in filas], total=int(total))


def get_patient(db: Session, patient_id: UUID) -> PatientOut:
    """Lectura por id; un id ajeno es indistinguible de uno inexistente (S7.2)."""
    return _patient_out(_get(db, patient_id))


def _blandos(
    db: Session, *, apellido_norm: str, nombre_norm: str, telefono_norm: str
) -> list[dict[str, Any]]:
    """Coincidencias activas por nombre completo o teléfono, tope 5 (S6.6, S6.7)."""
    filas = (
        db.execute(
            select(Patient)
            .where(
                Patient.deleted_at.is_(None),
                or_(
                    and_(
                        Patient.apellido_norm == apellido_norm,
                        Patient.nombre_norm == nombre_norm,
                    ),
                    Patient.telefono_norm == telefono_norm,
                ),
            )
            .order_by(Patient.apellido, Patient.nombre, Patient.numero_historia_clinica)
            .limit(MAX_CANDIDATOS)
        )
        .scalars()
        .all()
    )
    return [_candidato(patient) for patient in filas]


def create_patient(db: Session, *, tenant_id: UUID, payload: PatientCreate) -> PatientOut:
    """Alta con dedupe duro por DNI y blando por nombre/teléfono, en una transacción."""
    if payload.dni is not None:
        existente = _existente_por_dni(db, payload.dni)
        if existente is not None:
            raise _dni_duplicado([existente])

    nombre_norm = normalizar_texto(payload.nombre)
    apellido_norm = normalizar_texto(payload.apellido)
    telefono_norm = normalizar_telefono(payload.telefono)

    if not payload.confirmar_duplicado:
        candidatos = _blandos(
            db,
            apellido_norm=apellido_norm,
            nombre_norm=nombre_norm,
            telefono_norm=telefono_norm,
        )
        if candidatos:
            raise _posible_duplicado(candidatos)

    patient = Patient(
        tenant_id=tenant_id,
        nombre=payload.nombre,
        apellido=payload.apellido,
        apellido_norm=apellido_norm,
        nombre_norm=nombre_norm,
        dni=payload.dni,
        fecha_nacimiento=payload.fecha_nacimiento,
        sexo=_sexo_modelo(payload.sexo),
        telefono=payload.telefono,
        telefono_norm=telefono_norm,
        email=payload.email,
        domicilio=_domicilio_json(payload.domicilio),
        numero_historia_clinica=siguiente_numero_historia_clinica(db, tenant_id),
        activo=True,
    )
    db.add(patient)
    try:
        db.flush()
    except IntegrityError as exc:
        # Carrera chequeo→INSERT: el índice parcial gana. El rollback revierte
        # también el incremento del contador, así que no queda hueco (S4.5).
        db.rollback()
        existente = _existente_por_dni(db, payload.dni) if payload.dni else None
        raise _dni_duplicado([existente] if existente is not None else None) from exc
    db.commit()
    return _patient_out(patient)


def update_patient(db: Session, *, patient_id: UUID, payload: PatientUpdate) -> PatientOut:
    """Actualización parcial; recalcula los normalizados y revalida el DNI."""
    patient = _get(db, patient_id)
    cambios = payload.model_dump(exclude_unset=True)

    if cambios.get("dni") is not None:
        row = db.execute(
            select(Patient.id, Patient.numero_historia_clinica).where(
                Patient.dni == cambios["dni"], Patient.id != patient_id
            )
        ).first()
        if row is not None:
            raise _dni_duplicado(
                [{"id": str(row.id), "numero_historia_clinica": row.numero_historia_clinica}]
            )

    if "nombre" in cambios:
        patient.nombre = cambios["nombre"]
        patient.nombre_norm = normalizar_texto(cambios["nombre"])
    if "apellido" in cambios:
        patient.apellido = cambios["apellido"]
        patient.apellido_norm = normalizar_texto(cambios["apellido"])
    if "telefono" in cambios:
        patient.telefono = cambios["telefono"]
        patient.telefono_norm = normalizar_telefono(cambios["telefono"])
    if "dni" in cambios:
        patient.dni = cambios["dni"]
    if "fecha_nacimiento" in cambios:
        patient.fecha_nacimiento = cambios["fecha_nacimiento"]
    if "sexo" in cambios:
        patient.sexo = _sexo_modelo(cambios["sexo"])
    if "email" in cambios:
        patient.email = cambios["email"]
    if "domicilio" in cambios:
        patient.domicilio = _domicilio_json(cambios["domicilio"])

    try:
        db.flush()
        # ``updated_at`` es ``onupdate=now()``: tras el UPDATE el ORM lo marca
        # expirado. Se refresca **antes** del commit porque el GUC del tenant es
        # transaction-local: después del commit RLS esconde la fila y el refresh
        # sería un ``ObjectDeletedError``.
        db.refresh(patient)
    except IntegrityError as exc:
        db.rollback()
        raise _dni_duplicado() from exc
    db.commit()
    return _patient_out(patient)


def _sexo_modelo(sexo: Any) -> SexoPaciente | None:
    if sexo is None:
        return None
    return SexoPaciente(sexo.value if hasattr(sexo, "value") else sexo)


def _domicilio_json(domicilio: Domicilio | dict[str, Any] | None) -> dict[str, Any] | None:
    if domicilio is None:
        return None
    if isinstance(domicilio, dict):
        return domicilio
    return domicilio.model_dump()
