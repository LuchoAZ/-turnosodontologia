"""Servicio de configuración clínica (C-05, design D1/D4/D6).

Todo corre sobre el ``Session`` del request, que ya tiene el GUC
``app.current_tenant`` fijado por ``require_auth``: las filas ajenas no existen
para el servicio y un id de otro tenant responde el mismo ``404`` que uno
inventado. El ``tenant_id`` de las altas sale del contexto, nunca del cliente.
"""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.clinic.errors import ClinicError, ClinicErrorCode
from app.domain.clinic.validation import ranges_overlap, time_ranges_overlap, validate_window
from app.models.clinic import AvailabilityRule, Chair, Professional
from app.schemas.clinic import (
    AvailabilityIn,
    AvailabilityOut,
    AvailabilityPatch,
    ChairIn,
    ChairOut,
    ChairPatch,
    ProfessionalIn,
    ProfessionalOut,
    ProfessionalPatch,
    SpecialtyOut,
)


def _chair_out(chair: Chair) -> ChairOut:
    return ChairOut(
        id=chair.id,
        nombre=chair.nombre,
        tipo=chair.tipo.value,
        ubicacion=chair.ubicacion,
        equipamiento=chair.equipamiento,
        activo=chair.activo,
    )


def list_chairs(db: Session) -> list[ChairOut]:
    """Sillones del tenant (activos e inactivos), orden estable por tipo y nombre."""
    chairs = db.execute(
        select(Chair).order_by(Chair.tipo, Chair.nombre, Chair.id)
    ).scalars()
    return [_chair_out(chair) for chair in chairs]


def _get_chair(db: Session, chair_id: UUID) -> Chair:
    chair = db.execute(select(Chair).where(Chair.id == chair_id)).scalar_one_or_none()
    if chair is None:
        raise ClinicError(ClinicErrorCode.chair_not_found)
    return chair


def _chair_name_taken() -> ClinicError:
    return ClinicError(ClinicErrorCode.chair_name_taken)


def create_chair(db: Session, *, tenant_id: UUID, payload: ChairIn) -> ChairOut:
    """Alta de sillón con unicidad `(tenant_id, nombre)` garantizada por la base."""
    duplicate = db.execute(
        select(Chair.id).where(Chair.nombre == payload.nombre)
    ).scalar_one_or_none()
    if duplicate is not None:
        raise _chair_name_taken()

    chair = Chair(
        tenant_id=tenant_id,
        nombre=payload.nombre,
        tipo=payload.tipo,
        ubicacion=payload.ubicacion,
        equipamiento=payload.equipamiento,
        activo=True,
    )
    db.add(chair)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _chair_name_taken() from exc
    db.commit()
    return _chair_out(chair)


def update_chair(db: Session, *, chair_id: UUID, payload: ChairPatch) -> ChairOut:
    chair = _get_chair(db, chair_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(chair, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _chair_name_taken() from exc
    db.commit()
    return _chair_out(chair)


def deactivate_chair(db: Session, *, chair_id: UUID) -> None:
    """Baja lógica idempotente: la fila y su historial se conservan (RN-EX-03)."""
    chair = _get_chair(db, chair_id)
    if chair.activo:
        chair.activo = False
        db.flush()
    db.commit()


def _professional_out(professional: Professional, specialty_nombre: str) -> ProfessionalOut:
    return ProfessionalOut(
        id=professional.id,
        user_id=professional.user_id,
        nombre=professional.nombre,
        apellido=professional.apellido,
        matricula=professional.matricula,
        especialidad=SpecialtyOut(
            id=professional.especialidad_id, nombre=specialty_nombre
        ),
        duracion_default_min=professional.duracion_default_min,
        porcentaje_liquidacion=professional.porcentaje_liquidacion,
        color_agenda=professional.color_agenda,
        activo=professional.activo,
    )


def _matricula_taken() -> ClinicError:
    return ClinicError(ClinicErrorCode.professional_matricula_taken)


def _professional_not_found() -> ClinicError:
    return ClinicError(ClinicErrorCode.professional_not_found)


def _specialty_not_found() -> ClinicError:
    return ClinicError(ClinicErrorCode.specialty_not_found)


def _prepare_professional(
    db: Session, *, tenant_id: UUID, payload: ProfessionalIn
) -> Professional:
    """Validaciones de existencia previas a la escritura (S5.4/S5.5)."""
    specialty = db.execute(
        text(
            """
            SELECT nombre FROM specialty
            WHERE id = :id AND (tenant_id IS NULL OR tenant_id = :tenant_id)
            """
        ),
        {"id": payload.especialidad_id, "tenant_id": tenant_id},
    ).scalar_one_or_none()
    if specialty is None:
        raise _specialty_not_found()

    if payload.user_id is not None:
        member = db.execute(
            text(
                """
                SELECT 1 FROM membership
                WHERE user_id = :user_id AND activo
                """
            ),
            {"user_id": payload.user_id},
        ).scalar_one_or_none()
        if member is None:
            raise ClinicError(ClinicErrorCode.user_not_member)

    duplicate = db.execute(
        select(Professional.id).where(Professional.matricula == payload.matricula)
    ).scalar_one_or_none()
    if duplicate is not None:
        raise _matricula_taken()

    return Professional(
        tenant_id=tenant_id,
        user_id=payload.user_id,
        nombre=payload.nombre,
        apellido=payload.apellido,
        matricula=payload.matricula,
        especialidad_id=payload.especialidad_id,
        duracion_default_min=payload.duracion_default_min,
        porcentaje_liquidacion=payload.porcentaje_liquidacion,
        color_agenda=payload.color_agenda,
        activo=True,
    )


def list_specialties(db: Session, *, tenant_id: UUID) -> list[SpecialtyOut]:
    """Catálogo visible: globales del seed (``tenant_id IS NULL``) + propias.

    ``specialty`` no tiene RLS; la visibilidad se resuelve acá y no en una
    política. El orden es estable por ``nombre`` (y ``id`` para desempatar).
    """
    rows = db.execute(
        text(
            """
            SELECT id, nombre FROM specialty
            WHERE tenant_id IS NULL OR tenant_id = :tenant_id
            ORDER BY nombre, id
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings()
    return [SpecialtyOut(id=row["id"], nombre=row["nombre"]) for row in rows]


def list_professionals(db: Session) -> list[ProfessionalOut]:
    rows = db.execute(
        text(
            """
            SELECT p.id, p.user_id, p.nombre, p.apellido, p.matricula,
                   p.especialidad_id, s.nombre AS especialidad_nombre,
                   p.duracion_default_min, p.porcentaje_liquidacion,
                   p.color_agenda, p.activo
            FROM professional p
            JOIN specialty s ON s.id = p.especialidad_id
            ORDER BY p.apellido, p.nombre, p.id
            """
        )
    ).mappings()
    return [
        ProfessionalOut(
            id=row["id"],
            user_id=row["user_id"],
            nombre=row["nombre"],
            apellido=row["apellido"],
            matricula=row["matricula"],
            especialidad=SpecialtyOut(
                id=row["especialidad_id"], nombre=row["especialidad_nombre"]
            ),
            duracion_default_min=row["duracion_default_min"],
            porcentaje_liquidacion=row["porcentaje_liquidacion"],
            color_agenda=row["color_agenda"],
            activo=row["activo"],
        )
        for row in rows
    ]


def create_professional(
    db: Session, *, tenant_id: UUID, payload: ProfessionalIn
) -> ProfessionalOut:
    professional = _prepare_professional(db, tenant_id=tenant_id, payload=payload)
    db.add(professional)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _matricula_taken() from exc
    specialty_name = _specialty_name(db, professional.especialidad_id)
    db.commit()
    return _professional_out(professional, specialty_name)


def _specialty_name(db: Session, specialty_id: UUID) -> str:
    return str(
        db.execute(
            text("SELECT nombre FROM specialty WHERE id = :id"), {"id": specialty_id}
        ).scalar_one()
    )


def update_professional(
    db: Session, *, professional_id: UUID, payload: ProfessionalPatch
) -> ProfessionalOut:
    professional = db.execute(
        select(Professional).where(Professional.id == professional_id)
    ).scalar_one_or_none()
    if professional is None:
        raise _professional_not_found()

    changes = payload.model_dump(exclude_unset=True)
    if "especialidad_id" in changes and changes["especialidad_id"] is not None:
        exists = db.execute(
            text(
                """
                SELECT 1 FROM specialty
                WHERE id = :id AND (tenant_id IS NULL OR tenant_id = :tenant_id)
                """
            ),
            {"id": changes["especialidad_id"], "tenant_id": professional.tenant_id},
        ).scalar_one_or_none()
        if exists is None:
            raise _specialty_not_found()
    for field, value in changes.items():
        setattr(professional, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _matricula_taken() from exc
    db.commit()
    return _professional_out(
        professional, _specialty_name(db, professional.especialidad_id)
    )

def _rule_out(rule: AvailabilityRule) -> AvailabilityOut:
    return AvailabilityOut(
        id=rule.id,
        professional_id=rule.professional_id,
        chair_id=rule.chair_id,
        dia_semana=rule.dia_semana,
        hora_inicio=rule.hora_inicio,
        hora_fin=rule.hora_fin,
        slot_min=rule.slot_min,
        buffer_previo_min=rule.buffer_previo_min,
        buffer_posterior_min=rule.buffer_posterior_min,
        fecha_desde=rule.fecha_desde,
        fecha_hasta=rule.fecha_hasta,
        tipo_practica=rule.tipo_practica,
    )


def list_availability(db: Session) -> list[AvailabilityOut]:
    rules = db.execute(
        select(AvailabilityRule).order_by(
            AvailabilityRule.dia_semana, AvailabilityRule.hora_inicio, AvailabilityRule.id
        )
    ).scalars()
    return [_rule_out(rule) for rule in rules]


def _assert_window(
    *,
    hora_inicio: time,
    hora_fin: time,
    slot_min: int,
    buffer_previo_min: int,
    buffer_posterior_min: int,
    fecha_desde: date,
    fecha_hasta: date | None,
) -> None:
    issues = validate_window(
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        slot_min=slot_min,
        buffer_previo_min=buffer_previo_min,
        buffer_posterior_min=buffer_posterior_min,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    if issues:
        message = " ".join(f"{issue[0].upper()}{issue[1:]}." for issue in issues)
        raise ClinicError(ClinicErrorCode.invalid_request, message)


def _assert_professional_visible(db: Session, professional_id: UUID | None) -> None:
    if professional_id is None:
        return
    exists = db.execute(
        select(Professional.id).where(Professional.id == professional_id)
    ).scalar_one_or_none()
    if exists is None:
        raise _professional_not_found()


def _assert_chair_visible(db: Session, chair_id: UUID | None) -> None:
    if chair_id is None:
        return
    exists = db.execute(select(Chair.id).where(Chair.id == chair_id)).scalar_one_or_none()
    if exists is None:
        raise ClinicError(ClinicErrorCode.chair_not_found)


def _has_overlap(
    db: Session,
    *,
    professional_id: UUID | None,
    chair_id: UUID | None,
    dia_semana: int,
    hora_inicio: time,
    hora_fin: time,
    fecha_desde: date,
    fecha_hasta: date | None,
    exclude_id: UUID | None = None,
) -> bool:
    """Solape del mismo alcance y día; ``None`` en el alcance compara IS NOT DISTINCT."""
    statement = (
        select(AvailabilityRule)
        .where(
            AvailabilityRule.dia_semana == dia_semana,
            AvailabilityRule.professional_id.is_not_distinct_from(professional_id),
            AvailabilityRule.chair_id.is_not_distinct_from(chair_id),
        )
        .with_for_update()
    )
    if exclude_id is not None:
        statement = statement.where(AvailabilityRule.id != exclude_id)
    for rule in db.execute(statement).scalars():
        if not ranges_overlap(
            fecha_desde, fecha_hasta, rule.fecha_desde, rule.fecha_hasta
        ):
            continue
        if time_ranges_overlap(hora_inicio, hora_fin, rule.hora_inicio, rule.hora_fin):
            return True
    return False


def _availability_overlap() -> ClinicError:
    return ClinicError(ClinicErrorCode.availability_overlap)


def create_availability(
    db: Session, *, tenant_id: UUID, payload: AvailabilityIn
) -> AvailabilityOut:
    _assert_window(
        hora_inicio=payload.hora_inicio,
        hora_fin=payload.hora_fin,
        slot_min=payload.slot_min,
        buffer_previo_min=payload.buffer_previo_min,
        buffer_posterior_min=payload.buffer_posterior_min,
        fecha_desde=payload.fecha_desde,
        fecha_hasta=payload.fecha_hasta,
    )
    _assert_professional_visible(db, payload.professional_id)
    _assert_chair_visible(db, payload.chair_id)
    if _has_overlap(
        db,
        professional_id=payload.professional_id,
        chair_id=payload.chair_id,
        dia_semana=payload.dia_semana,
        hora_inicio=payload.hora_inicio,
        hora_fin=payload.hora_fin,
        fecha_desde=payload.fecha_desde,
        fecha_hasta=payload.fecha_hasta,
    ):
        raise _availability_overlap()

    rule = AvailabilityRule(tenant_id=tenant_id, **payload.model_dump())
    db.add(rule)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _availability_overlap() from exc
    db.commit()
    return _rule_out(rule)


def _get_availability(db: Session, rule_id: UUID) -> AvailabilityRule:
    rule = db.execute(
        select(AvailabilityRule).where(AvailabilityRule.id == rule_id)
    ).scalar_one_or_none()
    if rule is None:
        raise ClinicError(ClinicErrorCode.availability_not_found)
    return rule


def update_availability(
    db: Session, *, rule_id: UUID, payload: AvailabilityPatch
) -> AvailabilityOut:
    rule = _get_availability(db, rule_id)
    changes = payload.model_dump(exclude_unset=True)
    merged = {
        "professional_id": rule.professional_id,
        "chair_id": rule.chair_id,
        "dia_semana": rule.dia_semana,
        "hora_inicio": rule.hora_inicio,
        "hora_fin": rule.hora_fin,
        "slot_min": rule.slot_min,
        "buffer_previo_min": rule.buffer_previo_min,
        "buffer_posterior_min": rule.buffer_posterior_min,
        "fecha_desde": rule.fecha_desde,
        "fecha_hasta": rule.fecha_hasta,
        "tipo_practica": rule.tipo_practica,
    }
    merged.update(changes)
    # Revalidar el estado final tipado: el PATCH es parcial y la ventana se
    # juzga sobre el resultado, no sobre los campos sueltos.
    candidate = AvailabilityIn.model_validate(merged)

    _assert_window(
        hora_inicio=candidate.hora_inicio,
        hora_fin=candidate.hora_fin,
        slot_min=candidate.slot_min,
        buffer_previo_min=candidate.buffer_previo_min,
        buffer_posterior_min=candidate.buffer_posterior_min,
        fecha_desde=candidate.fecha_desde,
        fecha_hasta=candidate.fecha_hasta,
    )
    if "professional_id" in changes:
        _assert_professional_visible(db, candidate.professional_id)
    if "chair_id" in changes:
        _assert_chair_visible(db, candidate.chair_id)
    if _has_overlap(
        db,
        professional_id=candidate.professional_id,
        chair_id=candidate.chair_id,
        dia_semana=candidate.dia_semana,
        hora_inicio=candidate.hora_inicio,
        hora_fin=candidate.hora_fin,
        fecha_desde=candidate.fecha_desde,
        fecha_hasta=candidate.fecha_hasta,
        exclude_id=rule_id,
    ):
        raise _availability_overlap()

    for field, value in changes.items():
        setattr(rule, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _availability_overlap() from exc
    db.commit()
    return _rule_out(rule)
