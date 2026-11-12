"""Gate de aislamiento cross-tenant de la configuración clínica (tasks 6.1-6.4, RN-TEN-02).

**Bloqueante de merge**: si algo de acá se pone rojo, C-05 no cuenta. Cubre los
dos niveles que importan, igual que ``test_team_rls.py``:

* **SQL**, con una conexión real como ``odontologia_app`` (``SET ROLE``): el rol
  de la app no es superusuario, no hace ``BYPASSRLS`` y ve exactamente las filas
  de su ``app.current_tenant``.
* **HTTP**, con la app conectada por su propio engine: el ``tenant_id`` nunca
  sale del cliente, un id ajeno es indistinguible de uno inexistente y la guarda
  de permisos corre antes de validar el body.

La prueba de mutación (6.4) desactiva ``ROW LEVEL SECURITY`` sobre ``chair`` y
comprueba que el gate se pone rojo; después la restaura y comprueba el verde.
Sin la restauración, toda la suite quedaría mintiendo, de ahí el ``finally``.
Nunca se hace ``DROP POLICY``: se muta el flag, no el esquema.
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

CHAIRS_URL = "/api/v1/clinic/chairs"
PROFESSIONALS_URL = "/api/v1/clinic/professionals"
AVAILABILITY_URL = "/api/v1/clinic/availability"
HEADER_TENANT = "X-Tenant-Id"

CLINIC_TABLES = ("chair", "professional", "availability_rule")


def _app_engine(settings: Settings) -> Engine:
    return create_db_engine(settings)


def _visible_ids(
    connection: Connection, table: str, tenant_id: UUID | None = None
) -> set[UUID]:
    if tenant_id is not None:
        set_tenant_context(connection, tenant_id)
    return set(connection.execute(text(f"SELECT id FROM {table}")).scalars())


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
    """Dos clínicas con un sillón, un profesional y una regla cada una."""
    tenant_a = seeder.tenant(slug=f"rls-clinic-a-{uuid4().hex[:8]}", nombre="Clínica A")
    tenant_b = seeder.tenant(slug=f"rls-clinic-b-{uuid4().hex[:8]}", nombre="Clínica B")
    specialty = seeder.specialty()

    owner_a = seeder.user(email=f"owner-a-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_a, owner_a, "owner")
    owner_b = seeder.user(email=f"owner-b-{uuid4().hex[:8]}@example.test")
    seeder.membership(tenant_b, owner_b, "owner")

    chair_a = seeder.chair(tenant_a, "Sillón A")
    chair_b = seeder.chair(tenant_b, "Sillón B")
    professional_a = seeder.professional(
        tenant_a, nombre="Paula", apellido="Aria", matricula="A-1", especialidad_id=specialty
    )
    professional_b = seeder.professional(
        tenant_b, nombre="Bruno", apellido="Berra", matricula="B-1", especialidad_id=specialty
    )
    rule_a = seeder.availability_rule(tenant_a, professional_id=professional_a, dia_semana=1)
    rule_b = seeder.availability_rule(tenant_b, professional_id=professional_b, dia_semana=1)

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "owner_a": owner_a,
        "owner_b": owner_b,
        "specialty": specialty,
        "ids": {
            "chair": ({chair_a}, {chair_b}),
            "professional": ({professional_a}, {professional_b}),
            "availability_rule": ({rule_a}, {rule_b}),
        },
    }


# --- 6.1a: nivel SQL -------------------------------------------------------


@pytest.mark.parametrize("table", CLINIC_TABLES)
def test_a_nunca_ve_las_filas_de_b(
    auth_settings: Settings, seeder: Any, table: str
) -> None:
    data = _two_tenants(seeder)
    a_ids, b_ids = data["ids"][table]
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            visible = _visible_ids(connection, table, data["tenant_a"])
            assert connection.execute(text("SELECT current_user")).scalar_one() == APP_ROLE

        assert visible == a_ids, (table, visible)
        assert not (visible & b_ids), (table, visible)
    finally:
        engine.dispose()


def test_update_y_delete_con_id_de_b_afectan_cero_filas(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    chair_b = next(iter(data["ids"]["chair"][1]))
    professional_b = next(iter(data["ids"]["professional"][1]))
    rule_b = next(iter(data["ids"]["availability_rule"][1]))
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            set_tenant_context(connection, data["tenant_a"])
            updated_chair = connection.execute(
                text("UPDATE chair SET nombre = 'robado' WHERE id = :id"), {"id": chair_b}
            )
            updated_professional = connection.execute(
                text("UPDATE professional SET nombre = 'robado' WHERE id = :id"),
                {"id": professional_b},
            )
            deleted_rule = connection.execute(
                text("DELETE FROM availability_rule WHERE id = :id"), {"id": rule_b}
            )
            # RLS filtra en el USING: la fila no existe "para" el tenant A.
            assert updated_chair.rowcount == 0
            assert updated_professional.rowcount == 0
            assert deleted_rule.rowcount == 0
            connection.rollback()
    finally:
        engine.dispose()

    with db_engine.connect() as connection:
        assert connection.execute(
            text("SELECT nombre FROM chair WHERE id = :id"), {"id": chair_b}
        ).scalar_one() == "Sillón B"
        assert connection.execute(
            text("SELECT nombre FROM professional WHERE id = :id"), {"id": professional_b}
        ).scalar_one() == "Bruno"
        assert connection.execute(
            text("SELECT count(*) FROM availability_rule WHERE id = :id"), {"id": rule_b}
        ).scalar_one() == 1


@pytest.mark.parametrize("table", CLINIC_TABLES)
def test_sin_contexto_rls_es_fail_closed(
    auth_settings: Settings, seeder: Any, table: str
) -> None:
    data = _two_tenants(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            # Sin ``app.current_tenant`` el predicado es NULL: cero filas, nunca todas.
            assert connection.execute(
                text(f"SELECT count(*) FROM {table}")
            ).scalar_one() == 0
            assert connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tenant_id"),
                {"tenant_id": data["tenant_a"]},
            ).scalar_one() == 0
        # El INSERT sin contexto también lo frena el WITH CHECK.
        with engine.connect() as connection:
            with pytest.raises(ProgrammingError) as error:
                connection.execute(
                    text(
                        """
                        INSERT INTO chair (id, tenant_id, nombre, tipo, activo)
                        VALUES (:id, :tenant_id, 'Sin contexto', 'consultorio', true)
                        """
                    ),
                    {"id": uuid4(), "tenant_id": data["tenant_a"]},
                )
            assert "row-level security" in str(error.value)
            connection.rollback()
    finally:
        engine.dispose()


def test_con_contexto_de_a_no_se_puede_insertar_en_b(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    engine = _app_engine(auth_settings)
    try:
        with engine.connect() as connection:
            set_tenant_context(connection, data["tenant_a"])
            with pytest.raises(ProgrammingError) as error:
                connection.execute(
                    text(
                        """
                        INSERT INTO chair (id, tenant_id, nombre, tipo, activo)
                        VALUES (:id, :tenant_id, 'Intruso', 'otro', true)
                        """
                    ),
                    {"id": uuid4(), "tenant_id": data["tenant_b"]},
                )
            # Lo frena el WITH CHECK, no el USING.
            assert "row-level security" in str(error.value)
            connection.rollback()
    finally:
        engine.dispose()

    with db_engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM chair WHERE tenant_id = :tenant_id"),
            {"tenant_id": data["tenant_b"]},
        ).scalar_one() == 1


# --- 6.1b: nivel HTTP ------------------------------------------------------


def test_http_no_devuelve_datos_de_b(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _two_tenants(seeder)
    _authenticate(client, auth_settings, seeder, data["tenant_a"], data["owner_a"])
    chair_a = str(next(iter(data["ids"]["chair"][0])))
    professional_a = str(next(iter(data["ids"]["professional"][0])))
    rule_a = str(next(iter(data["ids"]["availability_rule"][0])))

    chairs = client.get(CHAIRS_URL)
    professionals = client.get(PROFESSIONALS_URL)
    availability = client.get(AVAILABILITY_URL)

    assert chairs.status_code == professionals.status_code == availability.status_code == 200
    assert [chair["id"] for chair in chairs.json()["chairs"]] == [chair_a]
    assert [item["id"] for item in professionals.json()["professionals"]] == [professional_a]
    assert [rule["id"] for rule in availability.json()["availability"]] == [rule_a]
    assert "Sillón B" not in chairs.text
    assert "Berra" not in professionals.text


def test_http_patch_y_delete_con_id_de_b_responden_404(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    chair_b = next(iter(data["ids"]["chair"][1]))
    professional_b = next(iter(data["ids"]["professional"][1]))
    rule_b = next(iter(data["ids"]["availability_rule"][1]))
    _authenticate(client, auth_settings, seeder, data["tenant_a"], data["owner_a"])

    chair_patch = client.patch(f"{CHAIRS_URL}/{chair_b}", json={"ubicacion": "robado"})
    chair_delete = client.delete(f"{CHAIRS_URL}/{chair_b}")
    professional_patch = client.patch(
        f"{PROFESSIONALS_URL}/{professional_b}", json={"nombre": "Robado"}
    )
    rule_patch = client.patch(f"{AVAILABILITY_URL}/{rule_b}", json={"dia_semana": 3})

    missing_chair = client.patch(f"{CHAIRS_URL}/{uuid4()}", json={"ubicacion": "robado"})
    missing_professional = client.patch(
        f"{PROFESSIONALS_URL}/{uuid4()}", json={"nombre": "Robado"}
    )
    missing_rule = client.patch(f"{AVAILABILITY_URL}/{uuid4()}", json={"dia_semana": 3})

    assert chair_patch.status_code == 404
    assert chair_delete.status_code == 404
    assert professional_patch.status_code == 404
    assert rule_patch.status_code == 404
    # Un id ajeno y uno inventado son indistinguibles.
    assert chair_patch.json() == missing_chair.json()
    assert chair_patch.json()["code"] == "chair_not_found"
    assert chair_delete.json()["code"] == "chair_not_found"
    assert professional_patch.json() == missing_professional.json()
    assert professional_patch.json()["code"] == "professional_not_found"
    assert rule_patch.json() == missing_rule.json()
    assert rule_patch.json()["code"] == "availability_not_found"

    with db_engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM chair WHERE id = :id AND activo AND ubicacion IS NULL"),
            {"id": chair_b},
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT nombre FROM professional WHERE id = :id"), {"id": professional_b}
        ).scalar_one() == "Bruno"
        assert connection.execute(
            text("SELECT dia_semana FROM availability_rule WHERE id = :id"), {"id": rule_b}
        ).scalar_one() == 1


def test_tenant_id_en_el_body_es_422_invalid_request(
    client: TestClient, auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = _two_tenants(seeder)
    _authenticate(client, auth_settings, seeder, data["tenant_a"], data["owner_a"])
    foreign_tenant = str(data["tenant_b"])

    chair = client.post(
        CHAIRS_URL, json={"nombre": "Sillón Nuevo", "tipo": "rx", "tenant_id": foreign_tenant}
    )
    professional = client.post(
        PROFESSIONALS_URL,
        json={
            "nombre": "Nueva",
            "apellido": "Profesional",
            "matricula": "N-1",
            "especialidad_id": str(data["specialty"]),
            "tenant_id": foreign_tenant,
        },
    )
    availability = client.post(
        AVAILABILITY_URL,
        json={
            "dia_semana": 2,
            "hora_inicio": "09:00",
            "hora_fin": "12:00",
            "fecha_desde": "2026-11-16",
            "tenant_id": foreign_tenant,
        },
    )

    for response in (chair, professional, availability):
        assert response.status_code == 422, response.text
        assert response.json() == {
            "code": "invalid_request",
            "message": "La petición tiene campos inválidos o no permitidos.",
        }
        # Nunca el ``detail`` de FastAPI: no se filtra el nombre del campo.
        assert "detail" not in response.json()

    # La validación ocurre antes de escribir: nada nuevo en A ni en B.
    for table in CLINIC_TABLES:
        with db_engine.connect() as connection:
            assert connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tenant_id"),
                {"tenant_id": data["tenant_a"]},
            ).scalar_one() == 1


def test_tenant_id_en_query_o_header_se_ignora(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    data = _two_tenants(seeder)
    _authenticate(client, auth_settings, seeder, data["tenant_a"], data["owner_a"])
    chair_a = str(next(iter(data["ids"]["chair"][0])))

    response = client.get(
        CHAIRS_URL,
        params={"tenant_id": str(data["tenant_b"]), "limit": 100},
        headers={HEADER_TENANT: str(data["tenant_b"])},
    )

    assert response.status_code == 200, response.text
    assert [chair["id"] for chair in response.json()["chairs"]] == [chair_a]


# --- 6.4: prueba de mutación ----------------------------------------------


def test_mutar_rls_desactivada_rompe_el_gate_y_restaurarla_lo_deja_verde(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    """Receta 6.4: ``DISABLE ROW LEVEL SECURITY`` sobre ``chair`` -> rojo; restaurar -> verde.

    Mutación **de gate**, no de código: si el test SQL de 6.1a siguiera verde con
    RLS desactivada, no estaría probando nada. Nunca ``DROP POLICY``.
    """
    data = _two_tenants(seeder)
    a_ids, b_ids = data["ids"]["chair"]
    engine = _app_engine(auth_settings)

    def visible_for_a() -> set[UUID]:
        with engine.connect() as connection:
            return _visible_ids(connection, "chair", data["tenant_a"])

    try:
        assert visible_for_a() == a_ids
        print(f"[6.4] RLS ON  -> la app ve {len(a_ids)} sillon(es) de A, 0 de B")

        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE chair DISABLE ROW LEVEL SECURITY"))
        try:
            leaked = visible_for_a()
            # Sin RLS la conexión de la app ve las filas de los dos tenants.
            assert a_ids <= leaked
            assert b_ids <= leaked
            print(
                f"[6.4] RLS OFF -> la app ve {len(leaked)} sillon(es): "
                "el ajeno se filtra (6.1a ROJO)"
            )
        finally:
            with db_engine.begin() as connection:
                connection.execute(text("ALTER TABLE chair ENABLE ROW LEVEL SECURITY"))
                connection.execute(text("ALTER TABLE chair FORCE ROW LEVEL SECURITY"))

        assert visible_for_a() == a_ids
        print("[6.4] RLS ON  -> gate VERDE otra vez: cross-tenant leak = 0")
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("ALTER TABLE chair ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE chair FORCE ROW LEVEL SECURITY"))
        engine.dispose()
