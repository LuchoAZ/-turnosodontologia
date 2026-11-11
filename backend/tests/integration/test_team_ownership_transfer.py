"""``POST /api/v1/team/ownership-transfer`` (tasks 8.1/8.3/8.4, design D7).

La transferencia es atómica y serializada por tenant (``SELECT … FOR UPDATE``
sobre ``tenant``). La invariante es "exactamente un owner activo", nunca cero y
nunca dos: el actor cambia de rol en la misma transacción en la que el destino
pasa a ``owner``.

El actor **no** se da de baja: conserva el acceso con su rol nuevo, que es lo
que exigen S5.1 y S5.5 (un segundo intento responde ``403``, no ``401``).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from app.db.engine import create_db_engine, create_session_factory
from app.db.tenant_context import set_tenant_context
from app.domain.rbac.errors import RbacError
from app.domain.team import service
from app.schemas.team import OwnershipTransferRequest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

TRANSFER_URL = "/api/v1/team/ownership-transfer"
ME_URL = "/api/v1/auth/me"
MEMBERS_URL = "/api/v1/team/members"


def _service_transfer(
    settings: Settings,
    tenant_id: UUID,
    actor_id: UUID,
    membership_id: UUID,
) -> tuple[int, str | None]:
    """Llama al servicio con una sesión propia (dos conexiones reales).

    ``TestClient`` no admite dos requests simultáneos sobre el mismo portal, así
    que la concurrencia se ejerce contra el servicio, que es donde viven el lock
    y la transacción; el ``200``/``409`` es el mismo mapeo que hace el router.
    """
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            set_tenant_context(session.connection(), tenant_id)
            try:
                service.transfer_ownership(
                    session,
                    tenant_id=tenant_id,
                    actor_user_id=actor_id,
                    payload=OwnershipTransferRequest(
                        target_membership_id=membership_id,
                        previous_owner_role="clinical_admin",
                    ),
                )
            except RbacError as exc:
                session.rollback()
                return exc.status_code, exc.code.value
        return 200, None
    finally:
        engine.dispose()


def _authenticate(
    client: TestClient,
    settings: Settings,
    seeder: Any,
    tenant_id: UUID,
    user_id: UUID,
) -> None:
    seeded = seeder.session(tenant_id, user_id)
    client.cookies.clear()
    client.cookies.set(
        ACCESS_COOKIE,
        create_access_token(
            settings,
            user_id=user_id,
            session_id=seeded.session_id,
            tenant_id=tenant_id,
            mfa=True,
            now=datetime.now(UTC),
        ),
        path="/",
    )


def _events(engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tipo::text AS tipo, actor_user_id, target_user_id, detail
                FROM membership_event WHERE tenant_id = :tenant_id ORDER BY id
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings()
        return [dict(row) for row in rows]


def _memberships(engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id, user_id, rol::text AS rol, activo
                FROM membership WHERE tenant_id = :tenant_id ORDER BY rol, id
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings()
        return [dict(row) for row in rows]


def _active_owners(engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    return [
        row
        for row in _memberships(engine, tenant_id)
        if row["rol"] == "owner" and row["activo"]
    ]


def _owner(seeder: Any) -> tuple[UUID, UUID]:
    tenant_id = seeder.tenant()
    owner_id = seeder.user(email=f"owner-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_id, owner_id, "owner")
    return tenant_id, owner_id


def _membership_of(engine: Engine, tenant_id: UUID, user_id: UUID) -> dict[str, Any]:
    return next(
        row for row in _memberships(engine, tenant_id) if row["user_id"] == user_id
    )


def _member(
    seeder: Any, tenant_id: UUID, rol: str, *, activo: bool = True
) -> tuple[UUID, dict[str, Any]]:
    user_id = seeder.user(email=f"{rol}-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_id, user_id, rol, activo=activo)
    return user_id, {"user_id": user_id, "rol": rol, "activo": activo}


def test_la_transferencia_deja_exactamente_un_owner_activo(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id, _ = _member(seeder, tenant_id, "clinical_admin")
    target_membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(target_membership["id"]),
            "previous_owner_role": "clinical_admin",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"members"}
    by_user = {member["user_id"]: member for member in body["members"]}
    assert by_user[str(target_id)]["rol"] == "owner"
    assert by_user[str(target_id)]["activo"] is True
    assert by_user[str(owner_id)]["rol"] == "clinical_admin"
    assert by_user[str(owner_id)]["activo"] is True

    owners = _active_owners(db_engine, tenant_id)
    assert len(owners) == 1
    assert owners[0]["user_id"] == target_id

    events = _events(db_engine, tenant_id)
    assert [event["tipo"] for event in events] == ["ownership_transferred"]
    assert events[0]["actor_user_id"] == owner_id
    assert events[0]["target_user_id"] == target_id
    assert events[0]["detail"] == {
        "rol_anterior": "owner",
        "rol_nuevo": "clinical_admin",
        "target_rol_anterior": "clinical_admin",
    }


@pytest.mark.parametrize(
    ("caso", "rol", "activo", "code"),
    [
        ("target_inactivo", "professional", False, "member_inactive"),
        ("target_ya_owner", "owner", False, "member_already_owner"),
    ],
)
def test_un_destino_invalido_no_altera_el_ownership(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
    caso: str,
    rol: str,
    activo: bool,
    code: str,
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id, _ = _member(seeder, tenant_id, rol, activo=activo)
    target_membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(target_membership["id"]),
            "previous_owner_role": "clinical_admin",
        },
    )

    assert response.status_code == 409, caso
    assert response.json()["code"] == code
    assert _membership_of(db_engine, tenant_id, target_id)["rol"] == rol
    assert _membership_of(db_engine, tenant_id, owner_id)["rol"] == "owner"
    assert len(_active_owners(db_engine, tenant_id)) == 1
    assert _events(db_engine, tenant_id) == []


def test_no_puede_transferirse_a_si_mismo(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    own_membership = _membership_of(db_engine, tenant_id, owner_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(own_membership["id"]),
            "previous_owner_role": "clinical_admin",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "member_is_actor"
    assert _membership_of(db_engine, tenant_id, owner_id)["rol"] == "owner"
    assert _events(db_engine, tenant_id) == []


@pytest.mark.parametrize(
    "payload_extra",
    [
        {},
        {"previous_owner_role": None},
        {"previous_owner_role": "owner"},
        {"previous_owner_role": "patient"},
    ],
)
def test_previous_owner_role_debe_ser_asignable(
    client: TestClient,
    auth_settings: Settings,
    seeder: Any,
    db_engine: Engine,
    payload_extra: dict[str, Any],
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id, _ = _member(seeder, tenant_id, "clinical_admin")
    target_membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        TRANSFER_URL,
        json={"target_membership_id": str(target_membership["id"]), **payload_extra},
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "role_not_assignable"
    assert _membership_of(db_engine, tenant_id, owner_id)["rol"] == "owner"
    assert _membership_of(db_engine, tenant_id, target_id)["rol"] == "clinical_admin"
    assert _events(db_engine, tenant_id) == []


def test_un_destino_inexistente_y_uno_de_otro_tenant_son_indistinguibles(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_a, owner_a = _owner(seeder)
    tenant_b = seeder.tenant()
    foreign_id, _ = _member(seeder, tenant_b, "clinical_admin")
    foreign_membership = _membership_of(db_engine, tenant_b, foreign_id)
    _authenticate(client, auth_settings, seeder, tenant_a, owner_a)
    payload = {"previous_owner_role": "clinical_admin"}

    foreign = client.post(
        TRANSFER_URL,
        json={**payload, "target_membership_id": str(foreign_membership["id"])},
    )
    missing = client.post(
        TRANSFER_URL, json={**payload, "target_membership_id": str(uuid4())}
    )

    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["code"] == "membership_not_found"
    assert _membership_of(db_engine, tenant_b, foreign_id)["rol"] == "clinical_admin"
    assert _events(db_engine, tenant_a) == []
    assert _events(db_engine, tenant_b) == []


def test_el_actor_no_puede_quedar_con_dos_memberships_del_mismo_rol(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    seeder.membership(tenant_id, owner_id, "clinical_admin")
    target_id, _ = _member(seeder, tenant_id, "front_desk")
    target_membership = _membership_of(db_engine, tenant_id, target_id)
    before = _memberships(db_engine, tenant_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(target_membership["id"]),
            "previous_owner_role": "clinical_admin",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "role_conflict"
    assert _memberships(db_engine, tenant_id) == before
    assert len(_active_owners(db_engine, tenant_id)) == 1
    assert _events(db_engine, tenant_id) == []


def test_el_destino_no_puede_tener_otra_membership_owner_inactiva(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id, _ = _member(seeder, tenant_id, "clinical_admin")
    seeder.membership(tenant_id, target_id, "owner", activo=False)
    target_membership = next(
        row
        for row in _memberships(db_engine, tenant_id)
        if row["user_id"] == target_id and row["rol"] == "clinical_admin"
    )
    before = _memberships(db_engine, tenant_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    response = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(target_membership["id"]),
            "previous_owner_role": "clinical_admin",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "role_conflict"
    assert _memberships(db_engine, tenant_id) == before
    assert len(_active_owners(db_engine, tenant_id)) == 1
    assert _events(db_engine, tenant_id) == []


def test_sin_ownership_transfer_no_hay_transferencia(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    actor_id, _ = _member(seeder, tenant_id, "clinical_admin")
    target_id, _ = _member(seeder, tenant_id, "front_desk")
    target_membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, actor_id)

    response = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(target_membership["id"]),
            "previous_owner_role": "professional",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert _membership_of(db_engine, tenant_id, owner_id)["rol"] == "owner"
    assert _membership_of(db_engine, tenant_id, target_id)["rol"] == "front_desk"
    assert _events(db_engine, tenant_id) == []


def test_dos_transferencias_simultaneas_una_gana_y_nunca_hay_cero_owners(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    first_target, _ = _member(seeder, tenant_id, "clinical_admin")
    second_target, _ = _member(seeder, tenant_id, "professional")
    first_membership = _membership_of(db_engine, tenant_id, first_target)
    second_membership = _membership_of(db_engine, tenant_id, second_target)
    barrier = threading.Barrier(2)

    def transfer(membership_id: UUID) -> tuple[int, str | None]:
        barrier.wait(timeout=30)
        return _service_transfer(auth_settings, tenant_id, owner_id, membership_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result(timeout=60)
            for future in (
                pool.submit(transfer, first_membership["id"]),
                pool.submit(transfer, second_membership["id"]),
            )
        ]

    statuses = sorted(status for status, _ in results)
    assert statuses == [200, 409], results
    loser = next(code for status, code in results if status == 409)
    assert loser == "ownership_changed"

    owners = _active_owners(db_engine, tenant_id)
    assert len(owners) == 1
    assert owners[0]["user_id"] in {first_target, second_target}
    # El actor perdió el rol en ambas carreras: quedó con el rol pedido.
    assert _membership_of(db_engine, tenant_id, owner_id)["rol"] == "clinical_admin"
    assert [
        event["tipo"] for event in _events(db_engine, tenant_id)
    ] == ["ownership_transferred"]


def test_la_transferencia_espera_el_lock_del_tenant(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    """La serialización es real: con la fila ``tenant`` bloqueada, la petición espera."""
    tenant_id, owner_id = _owner(seeder)
    target_id, _ = _member(seeder, tenant_id, "clinical_admin")
    target_membership = _membership_of(db_engine, tenant_id, target_id)

    with db_engine.connect() as blocker:
        blocker.execute(
            text("SELECT id FROM tenant WHERE id = :id FOR UPDATE"), {"id": tenant_id}
        )
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(
            _service_transfer,
            auth_settings,
            tenant_id,
            owner_id,
            target_membership["id"],
        )
        try:
            # Con el lock tomado, la transferencia no puede haber completado.
            with pytest.raises(TimeoutError):
                future.result(timeout=1)
        finally:
            # El lock se libera siempre, incluso si la aserción falla: si no, el
            # hilo quedaría esperando para siempre.
            blocker.rollback()

    status, code = future.result(timeout=60)
    pool.shutdown(wait=True)

    assert (status, code) == (200, None)
    assert len(_active_owners(db_engine, tenant_id)) == 1


def test_el_actor_ve_sus_permisos_nuevos_y_el_destino_puede_revertir(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    tenant_id, owner_id = _owner(seeder)
    target_id, _ = _member(seeder, tenant_id, "clinical_admin")
    target_membership = _membership_of(db_engine, tenant_id, target_id)
    _authenticate(client, auth_settings, seeder, tenant_id, owner_id)

    transfer = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(target_membership["id"]),
            "previous_owner_role": "clinical_admin",
        },
    )
    assert transfer.status_code == 200, transfer.text

    me = client.get(ME_URL)
    assert me.status_code == 200, me.text
    assert "owner" not in me.json()["roles"]
    assert "clinical_admin" in me.json()["roles"]
    assert "ownership.transfer" not in me.json()["permissions"]
    assert "team.update" not in me.json()["permissions"]

    retry = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(target_membership["id"]),
            "previous_owner_role": "clinical_admin",
        },
    )
    assert retry.status_code == 403
    assert retry.json()["code"] == "forbidden"

    # El destino, ya owner, puede revertir la transferencia.
    former_owner_membership = _membership_of(db_engine, tenant_id, owner_id)
    _authenticate(client, auth_settings, seeder, tenant_id, target_id)
    back = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(former_owner_membership["id"]),
            "previous_owner_role": "clinical_admin",
        },
    )

    assert back.status_code == 200, back.text
    owners = _active_owners(db_engine, tenant_id)
    assert len(owners) == 1
    assert owners[0]["user_id"] == owner_id
    assert _membership_of(db_engine, tenant_id, target_id)["rol"] == "clinical_admin"
