"""Servicio de gestión de equipo (design D6/D7/D8, RN-TEN-04).

Todo se ejecuta sobre el ``Session`` del request, que ya tiene el GUC
``app.current_tenant`` fijado por ``require_auth``: las lecturas y escrituras
quedan filtradas por RLS y la app **nunca** recibe un ``tenant_id`` del cliente.

Sin invitaciones por email (PQ-08): el alta exige un usuario existente o una
``password_temporal`` elegida por el owner, que se comunica por fuera del
sistema. La contraseña nunca se devuelve ni se registra en la auditoría.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Environment
from app.domain.auth.passwords import hash_password
from app.domain.rbac.errors import RbacError, RbacErrorCode
from app.models.tenancy import Membership, Role, Tenant, User
from app.schemas.team import (
    AssignMemberRequest,
    ChangeRoleRequest,
    MemberListOut,
    MemberOut,
    OwnershipTransferRequest,
)

#: Roles que se asignan por ``POST``/``PATCH``. ``owner`` se transfiere, y los
#: roles de portal tienen su propia vía de alta (RN-TEN-04).
ASSIGNABLE_ROLES: frozenset[str] = frozenset(
    {
        "clinical_admin",
        "professional",
        "assistant",
        "front_desk",
        "billing",
        "accountant",
    }
)


def _to_member(membership: Membership, user: User) -> MemberOut:
    return MemberOut(
        id=membership.id,
        user_id=membership.user_id,
        email=user.email,
        nombre=user.nombre,
        apellido=user.apellido,
        rol=membership.rol.value,
        activo=membership.activo,
        professional_id=membership.professional_id,
    )


def list_members(db: Session) -> list[MemberOut]:
    """Memberships del tenant del contexto (activas e inactivas), orden estable.

    ``membership`` no tiene ``created_at`` (el DDL de 002 no lo declara), así que
    el orden se fija por rol, apellido/nombre y ``id``: determinista entre
    llamadas y con un desempate único.
    """
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .order_by(Membership.rol, User.apellido, User.nombre, Membership.id)
    ).all()
    return [_to_member(membership, user) for membership, user in rows]


def _assignable_role(rol: str) -> Role:
    """Traduce el rol pedido a ``Role`` o falla con el ``code`` del contrato."""
    if rol == Role.owner.value:
        raise RbacError(RbacErrorCode.owner_must_be_transferred)
    if rol not in ASSIGNABLE_ROLES:
        raise RbacError(RbacErrorCode.role_not_assignable)
    return Role(rol)


def _previous_owner_role(value: str | None) -> Role:
    """El rol que recibe el owner saliente: asignable y distinto de ``owner``.

    Cualquier otro valor —ausente, ``owner`` o un rol de portal— es ``422
    role_not_assignable`` con ``code`` estable del contrato (design D7 paso 1).
    """
    if value is None or value not in ASSIGNABLE_ROLES:
        raise RbacError(RbacErrorCode.role_not_assignable)
    return Role(value)


def _record_event(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None,
    target_user_id: UUID | None,
    tipo: str,
    detail: dict[str, object],
) -> None:
    """Anexa el evento de auditoría en la misma transacción (design D8)."""
    db.execute(
        text(
            """
            INSERT INTO membership_event
                (tenant_id, actor_user_id, target_user_id, tipo, detail)
            VALUES (:tenant_id, :actor_user_id, :target_user_id,
                    CAST(:tipo AS membership_event_tipo), CAST(:detail AS jsonb))
            """
        ),
        {
            "tenant_id": tenant_id,
            "actor_user_id": actor_user_id,
            "target_user_id": target_user_id,
            "tipo": tipo,
            "detail": json.dumps(detail, sort_keys=True),
        },
    )


def _create_new_user(
    db: Session, email: str, password_temporal: str | None, environment: Environment | str
) -> User:
    """Crea el ``user`` global con Argon2id; la contraseña no se registra."""
    if password_temporal is None:
        # S2.8: se valida antes de escribir cualquier fila.
        raise RbacError(RbacErrorCode.invalid_request)
    local_part = email.split("@", 1)[0][:80] or "Miembro"
    user = User(
        id=uuid4(),
        email=email,
        nombre=local_part,
        apellido="",
        password_hash=hash_password(password_temporal, environment),
        activo=True,
    )
    db.add(user)
    db.flush()
    return user


def assign_member(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    payload: AssignMemberRequest,
    environment: Environment | str,
) -> MemberOut:
    """Alta (o readmisión) de una membership en el tenant de la sesión."""
    email = payload.email.strip().lower()
    role = _assignable_role(payload.rol)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = _create_new_user(db, email, payload.password_temporal, environment)

    existing = db.execute(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user.id,
            Membership.rol == role,
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.activo:
            raise RbacError(RbacErrorCode.membership_exists)
        # Readmisión: el único ``(tenant_id, user_id, rol)`` no es parcial, así
        # que se reactiva la fila existente en lugar de insertar otra (S2.7).
        existing.activo = True
        db.flush()
        membership, tipo = existing, "member_reactivated"
    else:
        membership = Membership(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user.id,
            rol=role,
            activo=True,
        )
        db.add(membership)
        db.flush()
        tipo = "member_created"

    _record_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_user_id=user.id,
        tipo=tipo,
        detail={"rol": role.value},
    )
    db.commit()
    return _to_member(membership, user)


def _get_membership(db: Session, membership_id: UUID) -> Membership:
    """Membership del tenant del contexto; una de otro tenant es indistinguible.

    ``RLS`` ya filtra por ``app.current_tenant``, así que una membership ajena y
    un id inexistente devuelven exactamente el mismo ``404`` (S3.3/S5.2b).
    """
    membership = db.execute(
        select(Membership).where(Membership.id == membership_id)
    ).scalar_one_or_none()
    if membership is None:
        raise RbacError(RbacErrorCode.membership_not_found)
    return membership


def _user_of(db: Session, membership: Membership) -> User:
    return db.execute(select(User).where(User.id == membership.user_id)).scalar_one()


def _active_owner_count(db: Session) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Membership)
            .where(Membership.rol == Role.owner, Membership.activo.is_(True))
        ).scalar_one()
    )


def _guard_last_owner(db: Session, membership: Membership) -> None:
    """El único camino para dejar de ser owner es la transferencia (RN-TEN-04)."""
    if membership.rol is Role.owner and membership.activo and _active_owner_count(db) <= 1:
        raise RbacError(RbacErrorCode.last_owner)


def change_role(
    db: Session,
    *,
    actor_user_id: UUID,
    membership_id: UUID,
    payload: ChangeRoleRequest,
) -> MemberOut:
    """Cambia el rol de una membership; ``owner`` solo llega por transferencia."""
    role = _assignable_role(payload.rol)
    membership = _get_membership(db, membership_id)
    user = _user_of(db, membership)

    if membership.rol is role:
        # Idempotente: mismo estado final, sin evento nuevo (S3.4).
        return _to_member(membership, user)

    _guard_last_owner(db, membership)

    conflict = db.execute(
        select(Membership.id).where(
            Membership.user_id == membership.user_id,
            Membership.rol == role,
            Membership.id != membership.id,
        )
    ).scalar_one_or_none()
    if conflict is not None:
        raise RbacError(RbacErrorCode.membership_exists)

    previous = membership.rol.value
    membership.rol = role
    db.flush()
    _record_event(
        db,
        tenant_id=membership.tenant_id,
        actor_user_id=actor_user_id,
        target_user_id=membership.user_id,
        tipo="member_role_changed",
        detail={"rol_anterior": previous, "rol_nuevo": role.value},
    )
    db.commit()
    return _to_member(membership, user)


def deactivate_member(
    db: Session, *, actor_user_id: UUID, membership_id: UUID
) -> None:
    """Baja lógica idempotente (RN-EX-03) con guarda de último owner activo."""
    membership = _get_membership(db, membership_id)
    if not membership.activo:
        # Segunda baja: 204 sin un segundo evento (S4.3).
        return

    _guard_last_owner(db, membership)

    rol = membership.rol.value
    membership.activo = False
    db.flush()
    _record_event(
        db,
        tenant_id=membership.tenant_id,
        actor_user_id=actor_user_id,
        target_user_id=membership.user_id,
        tipo="member_deactivated",
        detail={"rol": rol},
    )
    db.commit()


def _active_owner_membership(db: Session, user_id: UUID) -> Membership | None:
    return db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.rol == Role.owner,
            Membership.activo.is_(True),
        )
    ).scalar_one_or_none()


def _role_conflict(
    db: Session, *, user_id: UUID, role: Role, exclude_id: UUID
) -> bool:
    """True si el usuario ya tiene otra membership con ese rol (único no parcial)."""
    return (
        db.execute(
            select(Membership.id).where(
                Membership.user_id == user_id,
                Membership.rol == role,
                Membership.id != exclude_id,
            )
        ).scalar_one_or_none()
        is not None
    )


def transfer_ownership(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    payload: OwnershipTransferRequest,
) -> MemberListOut:
    """Transferencia atómica de ownership (design D7, RN-TEN-04).

    ``SELECT … FOR UPDATE`` sobre la fila ``tenant`` serializa las transferencias
    del mismo tenant: la que pierde la carrera ya no encuentra al actor como
    owner activo y responde ``409 ownership_changed``. El orden "liberar →
    promover" mantiene la invariante de exactamente un owner activo.
    """
    previous_role = _previous_owner_role(payload.previous_owner_role)

    # Lock del tenant: no lee datos de negocio, solo serializa (D7 paso 2).
    locked = db.execute(
        select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
    ).scalar_one_or_none()
    if locked is None:
        raise RbacError(RbacErrorCode.membership_not_found)

    actor_membership = _active_owner_membership(db, actor_user_id)
    if actor_membership is None:
        raise RbacError(RbacErrorCode.ownership_changed)

    target = db.execute(
        select(Membership)
        .where(Membership.id == payload.target_membership_id)
        .with_for_update()
    ).scalar_one_or_none()
    if target is None:
        raise RbacError(RbacErrorCode.membership_not_found)
    if target.user_id == actor_user_id:
        raise RbacError(RbacErrorCode.member_is_actor)
    if target.rol is Role.owner:
        raise RbacError(RbacErrorCode.member_already_owner)
    if not target.activo:
        raise RbacError(RbacErrorCode.member_inactive)

    # Simétricos: el único ``(tenant_id, user_id, rol)`` no es parcial (S5.6/S5.7).
    if _role_conflict(
        db, user_id=actor_user_id, role=previous_role, exclude_id=actor_membership.id
    ):
        raise RbacError(RbacErrorCode.role_conflict)
    if _role_conflict(
        db, user_id=target.user_id, role=Role.owner, exclude_id=target.id
    ):
        raise RbacError(RbacErrorCode.role_conflict)

    target_rol_anterior = target.rol.value
    # Se cambia el rol en la misma fila y **sin** darla de baja: el actor
    # conserva el acceso con su rol nuevo (S5.1/S5.5). El slot del índice
    # parcial ``uq_membership_owner_activo`` se libera porque el índice solo
    # cubre ``rol = 'owner' AND activo``; darlo de baja lo dejaría en ``401``
    # en vez del ``403`` que exige S5.5.
    #
    # El orden importa y el índice es inmediato: primero se libera el slot del
    # actor y recién después se promueve al destino. El ``flush`` intermedio fija
    # el orden de los UPDATE en vez de depender del identity map.
    actor_membership.rol = previous_role
    db.flush()
    target.rol = Role.owner
    db.flush()

    _record_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_user_id=target.user_id,
        tipo="ownership_transferred",
        detail={
            "rol_anterior": Role.owner.value,
            "rol_nuevo": previous_role.value,
            "target_rol_anterior": target_rol_anterior,
        },
    )
    # Se lee dentro de la misma transacción: después del commit el GUC
    # transaction-local se limpia y RLS devolvería cero filas.
    members = list_members(db)
    db.commit()
    return MemberListOut(members=members)
