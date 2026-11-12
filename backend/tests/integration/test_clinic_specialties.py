"""``/api/v1/clinic/specialties`` (task 4.7, escenarios S10.1-S10.3).

El alta de profesional exige ``especialidad_id``. Los ids del seed son UUID5
deterministas, pero un tenant puede tener especialidades propias: el front no
puede hardcodearlos. Este catálogo es la única fuente válida y ``specialty``
**no** tiene RLS, así que la visibilidad se resuelve en la consulta
(``tenant_id IS NULL OR tenant_id = :tid``), no en una política. De ahí que
S10.3 se pruebe también a nivel de uso: una especialidad de B ni se lista ni
se puede usar para crear un profesional en A.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from fastapi.testclient import TestClient
from sqlalchemy import text

SPECIALTIES_URL = "/api/v1/clinic/specialties"
PROS_URL = "/api/v1/clinic/professionals"


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


def _tenant(seeder: Any) -> UUID:
    return seeder.tenant(slug=f"clinic-specialties-{uuid4().hex[:8]}", nombre="Clínica Catálogo")


def _session_as(
    client: TestClient, settings: Settings, seeder: Any, tenant_id: UUID, rol: str
) -> UUID:
    user_id = seeder.user(email=f"{rol}-{uuid4().hex[:8]}@example.test", nombre=rol)
    seeder.membership(tenant_id, user_id, rol)
    _authenticate(client, settings, seeder, tenant_id, user_id)
    return user_id


def _tenant_specialty(seeder: Any, tenant_id: UUID, nombre: str) -> UUID:
    specialty_id = uuid4()
    with seeder.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO specialty (id, tenant_id, nombre, duracion_default_min)
                VALUES (:id, :tenant_id, :nombre, 30)
                """
            ),
            {"id": specialty_id, "tenant_id": tenant_id, "nombre": nombre},
        )
    return specialty_id


def test_el_catalogo_trae_las_globales_y_las_propias_ordenadas(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    own_id = _tenant_specialty(seeder, tenant_id, "Aaa Propia C-05")
    _session_as(client, auth_settings, seeder, tenant_id, "professional")

    response = client.get(SPECIALTIES_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"specialties"}
    specialties = body["specialties"]
    assert all(set(item) == {"id", "nombre"} for item in specialties)
    assert "tenant_id" not in response.text

    names = [item["nombre"] for item in specialties]
    ids = [item["id"] for item in specialties]
    # Globales del seed de C-02 + la propia del tenant.
    assert own_id == UUID(ids[names.index("Aaa Propia C-05")])
    assert {"Odontología general", "Ortodoncia", "Higiene", "Periodoncia"} <= set(names)
    # Orden estable por ``nombre``: la propia va primero y H antes que P (sin ambigüedad).
    assert names[0] == "Aaa Propia C-05"
    assert names.index("Higiene") < names.index("Periodoncia")

    # Dos llamadas consecutivas devuelven exactamente el mismo orden.
    again = client.get(SPECIALTIES_URL)
    assert again.status_code == 200
    assert [item["id"] for item in again.json()["specialties"]] == ids


def test_un_tenant_sin_propias_ve_solo_las_globales(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "professional")

    response = client.get(SPECIALTIES_URL)

    assert response.status_code == 200, response.text
    returned = {item["id"] for item in response.json()["specialties"]}
    with seeder.engine.connect() as connection:
        globals_ = set(
            connection.execute(
                text("SELECT id FROM specialty WHERE tenant_id IS NULL")
            ).scalars()
        )
    assert returned == {str(specialty_id) for specialty_id in globals_}
    assert len(returned) >= 9  # seed de C-02


def test_sin_professional_read_el_catalogo_es_403(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    # ``billing`` no tiene ``professional.read`` en la matriz de la KB.
    _session_as(client, auth_settings, seeder, tenant_id, "billing")

    response = client.get(SPECIALTIES_URL)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    assert "specialties" not in response.text


def test_la_especialidad_de_otro_tenant_no_se_lista_ni_se_puede_usar(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    specialty_b = _tenant_specialty(seeder, tenant_b, "Solo de B C-05")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    catalog = client.get(SPECIALTIES_URL)

    assert catalog.status_code == 200, catalog.text
    assert "Solo de B C-05" not in catalog.text
    assert str(specialty_b) not in catalog.text

    created = client.post(
        PROS_URL,
        json={
            "nombre": "Paula",
            "apellido": "Pérez",
            "matricula": f"MP-{uuid4().hex[:8]}",
            "especialidad_id": str(specialty_b),
            "duracion_default_min": 30,
            "porcentaje_liquidacion": 40,
            "color_agenda": "#2563EB",
        },
    )

    assert created.status_code == 404, created.text
    assert created.json()["code"] == "specialty_not_found"
    with seeder.engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM professional WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_a},
        ).scalar_one() == 0
