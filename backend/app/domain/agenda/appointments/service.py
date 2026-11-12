"""Servicio de creación de turnos (tasks 2.2-5.1; design D2/D3/D8).

El orden de las validaciones es deliberado y falla temprano:

1. **Scoping** — ``professional``, ``chair`` y (si viene) ``patient`` se leen con
   ``tenant_id`` en el ``WHERE`` además de RLS: un id de otro tenant es
   indistinguible de uno inexistente (``404``, RN-EX-06), nunca ``403``.
2. **Activo** — un recurso desactivado no recibe turnos (``409
   recurso_inactivo``). Se valida antes del rango para que el ``motivo`` sea el del
   recurso y no el de una duración que no existe.
3. **Rango** — ``resolve_turno_range`` (dominio puro) congela duración y buffers.
4. **RN-AG-10** — el paciente con un turno solapado del mismo profesional es
   ``409 paciente_solapado``. Va antes del solape de recursos para que el mensaje
   nombre la regla que el usuario puede accionar (cambiar el horario del paciente).
5. **Solape de recursos** — pre-chequeo sobre el **rango bloqueado** de cada
   recurso (``professional`` y luego ``chair``), con los estados bloqueantes.
6. **Insert** — en un ``SAVEPOINT``: si el ``EXCLUDE USING gist`` rechaza la fila
   (``23P01``) por una carrera entre 5 y 6, se revierte solo el savepoint (el GUC
   del tenant sigue vivo) y se busca el turno que ganó para devolver el mismo
   contrato ``409`` con ``recurso`` y ``rangoEnConflicto``. Sin el savepoint, el
   rollback limpiaría el contexto de tenant y la lectura del conflicto daría
   ``ProgrammingError`` por RLS.

``tenant_id`` y ``creado_por`` no vienen del payload: los pasa el router desde la
sesión (RN-TEN-03).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.agenda.appointments.errors import AgendaError, AgendaErrorCode
from app.domain.agenda.appointments.range import ReglaTurno, TurnoRange, resolve_turno_range
from app.models.agenda import (
    ESTADOS_NO_BLOQUEANTES,
    ESTADOS_RN_AG_10,
    Appointment,
    AppointmentEstado,
    AppointmentOrigen,
)
from app.models.clinic import AvailabilityRule, Chair, Professional
from app.models.patients import Patient
from app.models.tenancy import Tenant
from app.schemas.appointments import AppointmentOut, CreateAppointment

# Constraint del EXCLUDE -> recurso que el usuario tiene que cambiar.
_RECURSO_POR_CONSTRAINT = {
    "ex_appointment_professional_no_overlap": "professional",
    "ex_appointment_chair_no_overlap": "chair",
}


def _no_encontrado(recurso: str) -> AgendaError:
    return AgendaError(
        AgendaErrorCode.recurso_no_encontrado,
        recurso=recurso,
        motivo=AgendaErrorCode.recurso_no_encontrado.value,
    )


def _inactivo(recurso: str) -> AgendaError:
    return AgendaError(
        AgendaErrorCode.recurso_inactivo,
        recurso=recurso,
        motivo=AgendaErrorCode.recurso_inactivo.value,
    )


def _solapado(*, recurso: str, fila: Appointment | None) -> AgendaError:
    return AgendaError(
        AgendaErrorCode.turno_solapado,
        recurso=recurso,
        motivo=AgendaErrorCode.turno_solapado.value,
        rango_en_conflicto=(fila.inicio, fila.fin) if fila is not None else None,
    )


def _get_professional(db: Session, *, tenant_id: UUID, professional_id: UUID) -> Professional:
    fila = db.execute(
        select(Professional).where(
            Professional.id == professional_id,
            Professional.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if fila is None:
        raise _no_encontrado("professional")
    return fila


def _get_chair(db: Session, *, tenant_id: UUID, chair_id: UUID) -> Chair:
    fila = db.execute(
        select(Chair).where(Chair.id == chair_id, Chair.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if fila is None:
        raise _no_encontrado("chair")
    return fila


def _get_patient(db: Session, *, tenant_id: UUID, patient_id: UUID) -> Patient:
    """Un paciente dado de baja (``deleted_at``) no existe para la agenda."""
    fila = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if fila is None or fila.deleted_at is not None:
        raise _no_encontrado("patient")
    return fila


def _tenant_timezone(db: Session, tenant_id: UUID) -> str:
    timezone = db.execute(
        select(Tenant.timezone).where(Tenant.id == tenant_id)
    ).scalar_one_or_none()
    # El default de la base es America/Argentina/Buenos_Aires; si el tenant no
    # existe (no puede pasar: la sesión ya lo validó) se usa el mismo default.
    return timezone or "America/Argentina/Buenos_Aires"


def _reglas(db: Session, tenant_id: UUID) -> list[ReglaTurno]:
    """Reglas del tenant como vista de dominio (sin objetos ORM en el cálculo)."""
    filas = (
        db.execute(
            select(AvailabilityRule).where(AvailabilityRule.tenant_id == tenant_id)
        )
        .scalars()
        .all()
    )
    return [
        ReglaTurno(
            professional_id=fila.professional_id,
            chair_id=fila.chair_id,
            dia_semana=fila.dia_semana,
            hora_inicio=fila.hora_inicio,
            hora_fin=fila.hora_fin,
            slot_min=fila.slot_min,
            buffer_previo_min=fila.buffer_previo_min,
            buffer_posterior_min=fila.buffer_posterior_min,
            fecha_desde=fila.fecha_desde,
            fecha_hasta=fila.fecha_hasta,
            tipo_practica=fila.tipo_practica,
        )
        for fila in filas
    ]


def _rango_bloqueado_del_existente() -> tuple[ColumnElement[datetime], ColumnElement[datetime]]:
    """``[inicio - buffer_previo, fin + buffer_posterior)`` del turno en la fila.

    ``make_interval`` posicional (años, meses, semanas, días, horas, minutos)
    replica exactamente la expresión del ``EXCLUDE`` de la migración 007.
    """
    desde = Appointment.inicio - func.make_interval(
        0, 0, 0, 0, 0, Appointment.buffer_previo_min
    )
    hasta = Appointment.fin + func.make_interval(
        0, 0, 0, 0, 0, Appointment.buffer_posterior_min
    )
    return desde, hasta


def _solape_de_recurso(
    db: Session,
    *,
    tenant_id: UUID,
    turno: TurnoRange,
    recurso: str,
    recurso_id: UUID,
) -> Appointment | None:
    """Primer turno activo del recurso cuyo rango bloqueado se solapa con ``turno``."""
    desde, hasta = _rango_bloqueado_del_existente()
    columna = Appointment.professional_id if recurso == "professional" else Appointment.chair_id
    return db.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.estado.not_in(ESTADOS_NO_BLOQUEANTES),
            columna == recurso_id,
            desde < turno.bloqueado_hasta,
            hasta > turno.bloqueado_desde,
        )
        .order_by(Appointment.inicio, Appointment.id)
        .limit(1)
    ).scalar_one_or_none()


def _solape_de_paciente(
    db: Session, *, tenant_id: UUID, turno: TurnoRange, professional_id: UUID, patient_id: UUID
) -> Appointment | None:
    """RN-AG-10: mismo paciente y mismo profesional, estados explícitos, rango clínico."""
    return db.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == patient_id,
            Appointment.professional_id == professional_id,
            Appointment.estado.in_(ESTADOS_RN_AG_10),
            Appointment.inicio < turno.fin,
            Appointment.fin > turno.inicio,
        )
        .order_by(Appointment.inicio, Appointment.id)
        .limit(1)
    ).scalar_one_or_none()


def _conflicto_de_base(
    db: Session,
    exc: IntegrityError,
    *,
    tenant_id: UUID,
    turno: TurnoRange,
    professional_id: UUID,
    chair_id: UUID,
) -> AgendaError:
    """Traduce la *exclusion violation* ``23P01`` al contrato ``409`` de aplicación."""
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    recurso = _RECURSO_POR_CONSTRAINT.get(constraint or "")
    if recurso is None:
        # Otra violación de integridad no es un solape accionable por la agenda.
        return AgendaError(
            AgendaErrorCode.turno_solapado, motivo=AgendaErrorCode.turno_solapado.value
        )
    fila = _solape_de_recurso(
        db,
        tenant_id=tenant_id,
        turno=turno,
        recurso=recurso,
        recurso_id=professional_id if recurso == "professional" else chair_id,
    )
    return _solapado(recurso=recurso, fila=fila)


def _appointment_out(appointment: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=appointment.id,
        professional_id=appointment.professional_id,
        chair_id=appointment.chair_id,
        patient_id=appointment.patient_id,
        inicio=appointment.inicio,
        fin=appointment.fin,
        duracion_min=appointment.duracion_min,
        buffer_previo_min=appointment.buffer_previo_min,
        buffer_posterior_min=appointment.buffer_posterior_min,
        estado=appointment.estado.value,
        origen=appointment.origen.value,
        tipo_practica=appointment.tipo_practica,
    )


def create_appointment(
    db: Session, *, tenant_id: UUID, user_id: UUID, payload: CreateAppointment
) -> AppointmentOut:
    """Crea el turno reservando profesional y sillón en una sola transacción."""
    professional = _get_professional(
        db, tenant_id=tenant_id, professional_id=payload.professional_id
    )
    chair = _get_chair(db, tenant_id=tenant_id, chair_id=payload.chair_id)
    patient = (
        _get_patient(db, tenant_id=tenant_id, patient_id=payload.patient_id)
        if payload.patient_id is not None
        else None
    )

    if not professional.activo:
        raise _inactivo("professional")
    if not chair.activo:
        raise _inactivo("chair")

    turno = resolve_turno_range(
        inicio=payload.inicio,
        tipo_practica=payload.tipo_practica.value if payload.tipo_practica is not None else None,
        professional_id=professional.id,
        chair_id=chair.id,
        duracion_default_min=professional.duracion_default_min,
        reglas=_reglas(db, tenant_id),
        timezone=_tenant_timezone(db, tenant_id),
    )

    if patient is not None:
        paciente_solapado = _solape_de_paciente(
            db,
            tenant_id=tenant_id,
            turno=turno,
            professional_id=professional.id,
            patient_id=patient.id,
        )
        if paciente_solapado is not None:
            raise AgendaError(
                AgendaErrorCode.paciente_solapado,
                recurso="patient",
                motivo=AgendaErrorCode.paciente_solapado.value,
                rango_en_conflicto=(paciente_solapado.inicio, paciente_solapado.fin),
            )

    for recurso, recurso_id in (("professional", professional.id), ("chair", chair.id)):
        conflicto = _solape_de_recurso(
            db, tenant_id=tenant_id, turno=turno, recurso=recurso, recurso_id=recurso_id
        )
        if conflicto is not None:
            raise _solapado(recurso=recurso, fila=conflicto)

    appointment = Appointment(
        tenant_id=tenant_id,
        patient_id=patient.id if patient is not None else None,
        professional_id=professional.id,
        chair_id=chair.id,
        inicio=turno.inicio,
        fin=turno.fin,
        duracion_min=turno.duracion_min,
        buffer_previo_min=turno.buffer_previo_min,
        buffer_posterior_min=turno.buffer_posterior_min,
        estado=AppointmentEstado.pendiente,
        tipo_practica=payload.tipo_practica.value if payload.tipo_practica is not None else None,
        origen=AppointmentOrigen.recepcion,
        creado_por=user_id,
    )

    savepoint = db.begin_nested()
    try:
        db.add(appointment)
        db.flush()
        savepoint.commit()
    except IntegrityError as exc:
        savepoint.rollback()
        raise _conflicto_de_base(
            db,
            exc,
            tenant_id=tenant_id,
            turno=turno,
            professional_id=professional.id,
            chair_id=chair.id,
        ) from exc

    creado = _appointment_out(appointment)
    db.commit()
    return creado
