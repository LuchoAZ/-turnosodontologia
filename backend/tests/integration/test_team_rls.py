"""Gate de aislamiento cross-tenant de equipo (task §9, RN-TEN-02).

Este archivo es **bloqueante de merge**: si algo de acá se pone rojo, el change
no cuenta. Cubre los dos niveles que importan:

* **SQL**, con una conexión real como ``odontologia_app`` (``SET ROLE``): el rol
  de la app no es superusuario, no hace ``BYPASSRLS`` y ve exactamente las filas
  de su ``app.current_tenant``.
* **HTTP**, con la app conectada por su propio engine (``create_db_engine``): el
  ``tenant_id`` nunca sale del cliente, un id ajeno es indistinguible de uno
  inexistente y la guarda de permisos corre antes de validar el body.

La prueba de mutación (9.2) desactiva ``ROW LEVEL SECURITY`` sobre ``membership``
y comprueba que el gate se pone rojo; después la restaura y comprueba el verde.
Sin la restauración, toda la suite quedaría mintiendo, de ahí el ``finally``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from app.db.engine import APP_ROLE, create_db_engine
from app.db.tenant_context import set_tenant_context
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import ProgrammingError

MEMBERS_URL = "/api/v1/team/members"
TRANSFER_URL = "/api/v1/team/ownership-transfer"
HEADER_TENANT = "X-Tenant-Id"


def _app_engine(settings: Settings) -> Engine:
    return create_db_engine(settings)


def _membership_ids(
    connection: Connection, tenant_id: UUID | None = None
) -> list[UUID]:
    if tenant_id is not None:
        set_tenant_context(connection, tenant_id)
    return list(connection.execute(text("SELECT id FROM membership")).scalars())


def _membership_of(engine: Engine, tenant_id: UUID, user_id: UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT id, rol::text AS rol, activo
                FROM membership WHERE tenant_id = :tenant_id AND user_id = :user_id
                """
            ),
            {"tenant_id": tenant_id, "user_id": user_id},
        ).mappings().one()
        return dict(row)


def _events(engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tipo::text AS tipo, actor_user_id, target_user_id
                FROM membership_event WHERE tenant_id = :tenant_id ORDER BY id
                """
            ),
            {"tenant_id": tenant_id},
        ).mappings()
        return [dict(row) for row in rows]


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


def _two_tenants(seeder: Any) -> dict[str, Any]:
    """Dos tenants con datos distinguibles: A (owner + professional) y B (owner + professional)."""
    tenant_a = seeder.tenant(nombre="Clínica A")
    tenant_b = seeder.tenant(nombre="Clínica B")
    owner_a = seeder.user(email=f"owner-a-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_a, owner_a, "owner")
    member_a = seeder.user(
        email=f"profe-a-{uuid4().hex[:8]}@example.test", nombre="Paula", apellido="Aria"
    )
    seeder.membership(tenant_a, member_a, "professional")

    owner_b = seeder.user(email=f"owner-b-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_b, owner_b, "owner")
    member_b = seeder.user(
        email=f"profe-b-{uuid4().hex[:8]}@example.test", nombre="Bruno", apellido="Berra"
    )
    seeder.membership(tenant_b, member_b, "professional")
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "owner_a": owner_a,
        "member_a": member_a,
        "owner_b": owner_b,
        "member_b": member_b,
    }


# --- 9.1a: nivel SQL -------------------------------------------------------


def test_a_nunca_ve_memberships_ni_emails_de_b(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            set_tenant_context(connection, data["tenant_a"])
            emails = list(
                connection.execute(
                    text(
                        """
                        SELECT u.email
                        FROM membership m JOIN "user" u ON u.id = m.user_id
                        """
                    )
                ).scalars()
            )
            ids = _membership_ids(connection)
            assert connection.execute(
                text("SELECT current_user")
            ).scalar_one() == APP_ROLE

        a_ids = {
            _membership_of(db_engine, data["tenant_a"], user)["id"]
            for user in (data["owner_a"], data["member_a"])
        }
        b_ids = {
            _membership_of(db_engine, data["tenant_b"], user)["id"]
            for user in (data["owner_b"], data["member_b"])
        }

        assert len(ids) == 2
        assert set(ids) == a_ids
        assert not (set(ids) & b_ids)
        assert len(emails) == 2
        assert all(email.endswith("@example.test") for email in emails)
        assert not any("owner-b-" in email or "profe-b-" in email for email in emails)
    finally:
        engine.dispose()


def test_patch_y_delete_con_id_de_b_no_modifican_filas_de_b(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    foreign = _membership_of(db_engine, data["tenant_b"], data["member_b"])
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            set_tenant_context(connection, data["tenant_a"])
            updated = connection.execute(
                text("UPDATE membership SET rol = 'assistant' WHERE id = :id"),
                {"id": foreign["id"]},
            )
            deleted = connection.execute(
                text("DELETE FROM membership WHERE id = :id"), {"id": foreign["id"]}
            )
            # RLS filtra en el USING: la fila no existe "para" el tenant A.
            assert updated.rowcount == 0
            assert deleted.rowcount == 0
            connection.rollback()
    finally:
        engine.dispose()

    after = _membership_of(db_engine, data["tenant_b"], data["member_b"])
    assert after == foreign
    assert after["rol"] == "professional"
    assert after["activo"] is True
    assert _events(db_engine, data["tenant_b"]) == []


def test_sin_contexto_rls_es_fail_closed(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            # Sin ``app.current_tenant`` el predicado es NULL: cero filas, nunca todas.
            assert connection.execute(
                text("SELECT count(*) FROM membership")
            ).scalar_one() == 0
            assert connection.execute(
                text("SELECT count(*) FROM membership WHERE tenant_id = :tenant_id"),
                {"tenant_id": data["tenant_a"]},
            ).scalar_one() == 0

            with pytest.raises(ProgrammingError) as error:
                connection.execute(
                    text(
                        """
                        INSERT INTO membership (id, tenant_id, user_id, rol, activo)
                        VALUES (:id, :tenant_id, :user_id, 'professional', true)
                        """
                    ),
                    {
                        "id": uuid4(),
                        "tenant_id": data["tenant_a"],
                        "user_id": data["member_a"],
                    },
                )
            assert "row-level security" in str(error.value)
            connection.rollback()

        with engine.connect() as connection:
            # Con el contexto de **A** tampoco se puede insertar en B: lo frena el
            # WITH CHECK, no el USING (S7.2/RN-TEN-02).
            set_tenant_context(connection, data["tenant_a"])
            with pytest.raises(ProgrammingError) as error:
                connection.execute(
                    text(
                        """
                        INSERT INTO membership (id, tenant_id, user_id, rol, activo)
                        VALUES (:id, :tenant_id, :user_id, 'front_desk', true)
                        """
                    ),
                    {
                        "id": uuid4(),
                        "tenant_id": data["tenant_b"],
                        "user_id": data["member_b"],
                    },
                )
            assert "row-level security" in str(error.value)
            connection.rollback()
    finally:
        engine.dispose()

    assert _membership_of(db_engine, data["tenant_b"], data["member_b"])["rol"] == (
        "professional"
    )


def test_odontologia_app_no_puede_leer_membership_event(
    auth_settings: Settings, seeder: Any
) -> None:
    """La auditoría es INSERT-only para la app: leerla es error de permisos, no 0 filas."""
    _two_tenants(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            with pytest.raises(ProgrammingError) as error:
                connection.execute(text("SELECT * FROM membership_event"))
            assert "permission denied" in str(error.value).lower()
            connection.rollback()
    finally:
        engine.dispose()


# --- 9.1b: nivel HTTP ------------------------------------------------------


def test_el_engine_de_la_app_corre_como_odontologia_app(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    """El bug que este test congela: ``SET ROLE`` revertido por el primer ``ROLLBACK``.

    Si el engine de la app quedara como el superusuario del contenedor, RLS se
    ignoraría incluso con ``FORCE`` y el aislamiento sería ficticio. El chequeo
    es explícito y sobrevive a rollback y a la reutilización desde el pool.
    """
    _two_tenants(seeder)
    engine = client.app.state.db_engine
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE
        connection.rollback()
        assert connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE
        connection.commit()
        assert connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE

    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE

    # El engine que crea ``create_db_engine`` (el único camino de la app) es el mismo rol.
    probe = _app_engine(auth_settings)
    try:
        with probe.connect() as connection:
            connection.rollback()
            assert connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE
    finally:
        probe.dispose()


def test_http_no_devuelve_datos_de_b(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    _authenticate(client, auth_settings, seeder, data["tenant_a"], data["owner_a"])

    response = client.get(MEMBERS_URL)

    assert response.status_code == 200, response.text
    members = response.json()["members"]
    emails = {member["email"] for member in members}
    assert len(members) == 2
    assert emails == {
        _email_of(db_engine, data["owner_a"]),
        _email_of(db_engine, data["member_a"]),
    }
    assert not any(email and "example.test" not in email for email in emails)
    assert all(
        "owner-b-" not in (email or "") and "profe-b-" not in (email or "")
        for email in emails
    )
    assert all("tenant_id" not in member for member in members)


def _email_of(engine: Engine, user_id: UUID) -> str:
    with engine.connect() as connection:
        return str(
            connection.execute(
                text('SELECT email FROM "user" WHERE id = :id'), {"id": user_id}
            ).scalar_one()
        )


def test_http_patch_y_delete_con_id_de_b_responden_404(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    foreign = _membership_of(db_engine, data["tenant_b"], data["member_b"])
    _authenticate(client, auth_settings, seeder, data["tenant_a"], data["owner_a"])

    patch = client.patch(
        f"{MEMBERS_URL}/{foreign['id']}", json={"rol": "clinical_admin"}
    )
    delete = client.delete(f"{MEMBERS_URL}/{foreign['id']}")
    missing = client.patch(f"{MEMBERS_URL}/{uuid4()}", json={"rol": "clinical_admin"})

    assert patch.status_code == 404
    assert delete.status_code == 404
    assert patch.json() == missing.json()
    assert patch.json()["code"] == "membership_not_found"
    assert delete.json()["code"] == "membership_not_found"
    assert _membership_of(db_engine, data["tenant_b"], data["member_b"]) == foreign
    assert _events(db_engine, data["tenant_a"]) == []
    assert _events(db_engine, data["tenant_b"]) == []


def test_tenant_id_en_el_body_es_422_invalid_request(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    target = _membership_of(db_engine, data["tenant_a"], data["member_a"])
    _authenticate(client, auth_settings, seeder, data["tenant_a"], data["owner_a"])
    body = {"rol": "assistant", "tenant_id": str(data["tenant_b"])}

    post = client.post(
        MEMBERS_URL,
        json={"email": f"nuevo-{uuid4().hex[:8]}@example.test", **body},
    )
    patch = client.patch(f"{MEMBERS_URL}/{target['id']}", json=body)
    transfer = client.post(
        TRANSFER_URL,
        json={
            "target_membership_id": str(target["id"]),
            "previous_owner_role": "clinical_admin",
            "tenant_id": str(data["tenant_b"]),
        },
    )
    unknown = client.post(
        MEMBERS_URL,
        json={"email": f"otro-{uuid4().hex[:8]}@example.test", "rol": "assistant", "x": 1},
    )

    for response in (post, patch, transfer, unknown):
        assert response.status_code == 422, response.text
        assert response.json() == {
            "code": "invalid_request",
            "message": "La petición tiene campos inválidos o no permitidos.",
        }
        # Nunca el ``detail`` de FastAPI: no se filtra el nombre del campo.
        assert "detail" not in response.json()

    # La validación ocurre antes de tocar la base: nada se escribió ni cambió.
    assert _membership_of(db_engine, data["tenant_a"], data["member_a"]) == target
    assert len(_membership_ids_http(db_engine, data["tenant_a"])) == 2
    assert _events(db_engine, data["tenant_a"]) == []


def _membership_ids_http(engine: Engine, tenant_id: UUID) -> list[UUID]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text("SELECT id FROM membership WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).scalars()
        )


def test_tenant_id_en_query_o_header_se_ignora(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    _authenticate(client, auth_settings, seeder, data["tenant_a"], data["owner_a"])

    response = client.get(
        MEMBERS_URL,
        params={"tenant_id": str(data["tenant_b"]), "clinic": "b"},
        headers={HEADER_TENANT: str(data["tenant_b"])},
    )

    assert response.status_code == 200, response.text
    members = response.json()["members"]
    assert {member["user_id"] for member in members} == {
        str(data["owner_a"]),
        str(data["member_a"]),
    }


def test_sin_permiso_el_403_gana_al_422_del_body(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _two_tenants(seeder)
    desk = seeder.user(email=f"desk-{uuid4().hex[:8]}@example.test")
    seeder.membership(data["tenant_a"], desk, "front_desk")
    _authenticate(client, auth_settings, seeder, data["tenant_a"], desk)

    response = client.post(
        MEMBERS_URL,
        json={
            "email": "x@example.test",
            "rol": "assistant",
            "tenant_id": str(data["tenant_b"]),
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


# --- 9.2: prueba de mutación ----------------------------------------------


def test_mutar_rls_desactivada_rompe_el_gate_y_restaurarla_lo_deja_verde(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    """Receta 9.2: ``DISABLE ROW LEVEL SECURITY`` → rojo; ``ENABLE``/``FORCE`` → verde.

    Mutación **de gate**, no de código: si el test SQL de 9.1a siguiera verde con
    RLS desactivada, no estaría probando nada. Nunca ``DROP POLICY``.
    """
    data = _two_tenants(seeder)
    engine = _app_engine(auth_settings)
    a_ids = {
        _membership_of(db_engine, data["tenant_a"], user)["id"]
        for user in (data["owner_a"], data["member_a"])
    }
    b_ids = {
        _membership_of(db_engine, data["tenant_b"], user)["id"]
        for user in (data["owner_b"], data["member_b"])
    }

    def visible_for_a() -> set[UUID]:
        with engine.connect() as connection:
            return set(_membership_ids(connection, data["tenant_a"]))

    try:
        # Verde de partida: el gate ve solo A.
        assert visible_for_a() == a_ids
        print(f"[9.2] RLS ON  -> la app ve {len(a_ids)} memberships de A, 0 de B")

        with db_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE membership DISABLE ROW LEVEL SECURITY")
            )
        try:
            leaked = visible_for_a()
            # Sin RLS la conexión de la app ve los dos tenants (y lo que hayan
            # dejado otros tests): 9.1a fallaría porque B aparece.
            assert a_ids <= leaked
            assert b_ids <= leaked
            assert b_ids - a_ids
            print(
                f"[9.2] RLS OFF -> la app ve {len(leaked)} memberships: "
                f"las {len(b_ids)} de B se filtrarian (9.1a ROJO)"
            )
        finally:
            with db_engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE membership ENABLE ROW LEVEL SECURITY")
                )
                connection.execute(
                    text("ALTER TABLE membership FORCE ROW LEVEL SECURITY")
                )

        # Restaurada, vuelve el verde.
        assert visible_for_a() == a_ids
        print("[9.2] RLS ON  -> gate VERDE otra vez: cross-tenant leak = 0")
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE membership ENABLE ROW LEVEL SECURITY"))
            connection.execute(
                text("ALTER TABLE membership FORCE ROW LEVEL SECURITY")
            )
        engine.dispose()
