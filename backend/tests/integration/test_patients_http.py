"""``/api/v1/patients`` (tasks 4.2-4.7, escenarios S1.1-S9.3).

El HTTP corre como ``odontologia_app`` con el GUC del tenant fijado por
``require_auth``: el ``tenant_id`` sale de la sesión y RLS lo vuelve a exigir. Las
sesiones se emiten con ``create_access_token`` (patrón de ``test_clinic_chairs``),
porque lo que se prueba es autorización y contrato, no el login.

La concurrencia (S4.4, S4.5, S5.5) vive en ``test_patients_service.py``, que puede
abrir dos transacciones reales en paralelo. La mutación de RLS (4.9) vive en
``test_patients_rls.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from fastapi.testclient import TestClient
from sqlalchemy import text

PATIENTS_URL = "/api/v1/patients"
CLINICAL_URL = "/api/v1/clinical/patients"

PATIENT_KEYS = {
    "id",
    "numero_historia_clinica",
    "nombre",
    "apellido",
    "dni",
    "fecha_nacimiento",
    "sexo",
    "telefono",
    "email",
    "domicilio",
    "activo",
    "created_at",
    "updated_at",
}
FORBIDDEN_KEYS = {"tenant_id", "deleted_at", "alergias", "alerta_clinica", "user_id"}
RESERVED_FIELDS = {
    "tenant_id": str(uuid4()),
    "numero_historia_clinica": "000999",
    "deleted_at": "2026-01-01T00:00:00Z",
    "alergias": "penicilina",
    "alerta_clinica": True,
}


# --- helpers ---------------------------------------------------------------


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
    return seeder.tenant(slug=f"patients-{uuid4().hex[:8]}", nombre="Clínica Pacientes")


def _member(seeder: Any, tenant_id: UUID, rol: str) -> UUID:
    user_id = seeder.user(
        email=f"{rol}-{uuid4().hex[:8]}@example.test", nombre=rol, apellido="Prueba"
    )
    seeder.membership(tenant_id, user_id, rol)
    return user_id


def _session_as(
    client: TestClient, settings: Settings, seeder: Any, tenant_id: UUID, rol: str
) -> UUID:
    user_id = _member(seeder, tenant_id, rol)
    _authenticate(client, settings, seeder, tenant_id, user_id)
    return user_id


def _counter(seeder: Any, tenant_id: UUID) -> int | None:
    with seeder.engine.connect() as connection:
        return connection.execute(
            text("SELECT ultimo_numero FROM patient_counter WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar_one_or_none()


def _patient_rows(seeder: Any, tenant_id: UUID) -> int:
    with seeder.engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM patient WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar_one()


def _alive(seeder: Any, patient_id: UUID) -> bool:
    with seeder.engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM patient WHERE id = :id AND deleted_at IS NULL"),
            {"id": patient_id},
        ).scalar_one() == 1


def _soft_delete(seeder: Any, patient_id: UUID) -> None:
    with seeder.engine.begin() as connection:
        connection.execute(
            text("UPDATE patient SET deleted_at = now() WHERE id = :id"), {"id": patient_id}
        )


def _set_counter(seeder: Any, tenant_id: UUID, valor: int) -> None:
    with seeder.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO patient_counter (tenant_id, ultimo_numero)
                VALUES (:tenant_id, :valor)
                ON CONFLICT (tenant_id) DO UPDATE SET ultimo_numero = :valor
                """
            ),
            {"tenant_id": tenant_id, "valor": valor},
        )


def _alta(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "nombre": "Ana",
        "apellido": "Pérez",
        "telefono": "11 5555-1234",
    }
    payload.update(overrides)
    return payload


def _create(client: TestClient, **overrides: Any) -> Any:
    return client.post(PATIENTS_URL, json=_alta(**overrides))


def _ids(response: Any) -> list[str]:
    return [item["id"] for item in response.json()["patients"]]


def _keys(payload: Any) -> set[str]:
    """Todas las claves de un JSON anidado (S9.1)."""
    encontradas: set[str] = set()
    if isinstance(payload, dict):
        for clave, valor in payload.items():
            encontradas.add(clave)
            encontradas |= _keys(valor)
    elif isinstance(payload, list):
        for item in payload:
            encontradas |= _keys(item)
    return encontradas


# --- S1: listado -----------------------------------------------------------


def test_s1_1_el_owner_ve_solo_su_tenant_ordenado_y_sin_datos_internos(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Zarate", nombre="Bruno", dni="30000111")
    seeder.patient(tenant_id, apellido="Alvarez", nombre="Ana", dni="30000222")
    seeder.patient(tenant_id, apellido="Baja", nombre="Carlos", deleted_at=datetime.now(UTC))
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(PATIENTS_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"patients", "total"}
    assert body["total"] == 2
    assert [item["apellido"] for item in body["patients"]] == ["Alvarez", "Zarate"]
    for item in body["patients"]:
        assert set(item) == PATIENT_KEYS
        assert not (set(item) & FORBIDDEN_KEYS)


def test_s1_2_sin_patient_read_la_lista_no_existe_para_el_backend(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Secreto", nombre="Ficha", dni="30000333")
    _session_as(client, auth_settings, seeder, tenant_id, "accountant")

    response = client.get(PATIENTS_URL)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    assert "Secreto" not in response.text
    assert "30000333" not in response.text


def test_s1_3_un_tenant_sin_pacientes_devuelve_lista_vacia_con_total_cero(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(PATIENTS_URL)

    assert response.status_code == 200, response.text
    assert response.json() == {"patients": [], "total": 0}


def test_s1_4_paginacion_acota_la_pagina_pero_no_el_total(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Aaa", nombre="Uno")
    seeder.patient(tenant_id, apellido="Bbb", nombre="Dos")
    seeder.patient(tenant_id, apellido="Ccc", nombre="Tres")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(PATIENTS_URL, params={"limit": 1, "offset": 1})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert [item["apellido"] for item in body["patients"]] == ["Bbb"]


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}],
)
def test_s1_4_limites_fuera_de_rango_responden_422(
    client: TestClient, auth_settings: Settings, seeder: Any, params: dict[str, int]
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(PATIENTS_URL, params=params)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"


def test_s1_5_un_paciente_de_otro_tenant_nunca_aparece(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    own = seeder.patient(tenant_a, apellido="Pérez", nombre="Ana", dni="30111222")
    foreign = seeder.patient(tenant_b, apellido="Pérez", nombre="Ana", dni="30111222")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    response = client.get(PATIENTS_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["patients"]] == [str(own)]
    assert str(foreign) not in response.text


def test_s1_6_incluir_inactivos_trae_la_baja_sin_exponer_deleted_at(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Activo", nombre="Ana")
    seeder.patient(tenant_id, apellido="Inactivo", nombre="Beto", deleted_at=datetime.now(UTC))
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    con_bajas = client.get(PATIENTS_URL, params={"incluir_inactivos": "true"})
    sin_bajas = client.get(PATIENTS_URL)

    assert con_bajas.status_code == 200, con_bajas.text
    assert con_bajas.json()["total"] == 2
    assert sin_bajas.json()["total"] == 1
    for item in con_bajas.json()["patients"]:
        assert "deleted_at" not in item


# --- S2: búsqueda ----------------------------------------------------------


@pytest.mark.parametrize("termino", ["perez", "PEREZ", "Pérez", "PÉREZ"])
def test_s2_1_la_busqueda_ignora_mayusculas_y_acentos(
    client: TestClient, auth_settings: Settings, seeder: Any, termino: str
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Pérez", nombre="Ana")
    seeder.patient(tenant_id, apellido="Gómez", nombre="Beto")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(PATIENTS_URL, params={"q": termino})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["patients"][0]["apellido"] == "Pérez"


def test_s2_2_la_busqueda_resuelve_dni_y_telefono(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    objetivo = seeder.patient(
        tenant_id,
        apellido="Pérez",
        nombre="Ana",
        dni="30111222",
        telefono="+54 11 5555-4321",
    )
    seeder.patient(tenant_id, apellido="Gómez", nombre="Beto", dni="30999888", telefono="11 4444-1")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    por_dni = client.get(PATIENTS_URL, params={"q": "30111222"})
    por_telefono = client.get(PATIENTS_URL, params={"q": "4321"})

    for response in (por_dni, por_telefono):
        body = response.json()
        assert body["total"] == 1, response.text
        assert body["patients"][0]["id"] == str(objetivo)


@pytest.mark.parametrize("termino", ["%", "_", "\\", "' OR 1=1 --", "%%", "a_b"])
def test_s2_3_los_comodines_se_escapan_y_no_hay_inyeccion_de_patron(
    client: TestClient, auth_settings: Settings, seeder: Any, termino: str
) -> None:
    tenant_id = _tenant(seeder)
    # Teléfonos sin "1" para que el término "' OR 1=1 --" (dígitos "11") tampoco
    # matchee por teléfono: el único motivo de coincidencia sería un comodín.
    seeder.patient(tenant_id, apellido="Pérez", nombre="Ana", telefono="4444-0000")
    seeder.patient(tenant_id, apellido="Gómez", nombre="Beto", telefono="5555-2222")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(PATIENTS_URL, params={"q": termino})

    assert response.status_code == 200, response.text
    # ``%``/``_`` literales no matchean "todos": el total es 0, nunca 2.
    assert response.json()["total"] == 0


def test_s2_4_la_busqueda_no_cruza_tenants(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    seeder.patient(tenant_a, apellido="Gómez", nombre="Ana")
    foreign = seeder.patient(tenant_b, apellido="Pérez", nombre="Ana")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    response = client.get(PATIENTS_URL, params={"q": "perez"})

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0
    assert str(foreign) not in response.text


def test_s2_5_un_q_de_61_caracteres_se_rechaza_antes_de_consultar(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Pérez", nombre="Ana")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(PATIENTS_URL, params={"q": "a" * 61})

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"


@pytest.mark.parametrize("termino", ["", "   "])
def test_s2_6_un_q_en_blanco_equivale_a_listar_sin_filtro(
    client: TestClient, auth_settings: Settings, seeder: Any, termino: str
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Pérez", nombre="Ana")
    seeder.patient(tenant_id, apellido="Gómez", nombre="Beto")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    sin_q = client.get(PATIENTS_URL)
    con_q = client.get(PATIENTS_URL, params={"q": termino})

    assert con_q.status_code == 200, con_q.text
    assert con_q.json()["total"] == sin_q.json()["total"] == 2


# --- S3: alta --------------------------------------------------------------


def test_s3_1_el_alta_completa_devuelve_la_ficha_y_persiste_la_fila(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(
        client,
        dni="30111222",
        email="ana.perez@example.com",
        fecha_nacimiento="1990-05-04",
        sexo="femenino",
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == PATIENT_KEYS
    assert len(created["numero_historia_clinica"]) == 6
    assert created["numero_historia_clinica"].isdigit()
    assert created["activo"] is True
    with seeder.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT tenant_id, dni, apellido_norm, telefono_norm "
                "FROM patient WHERE id = :id"
            ),
            {"id": created["id"]},
        ).one()
    assert row.tenant_id == tenant_id
    assert row.dni == "30111222"
    assert row.apellido_norm == "perez"
    assert row.telefono_norm == "1155551234"


def test_s3_2_sin_patient_create_no_se_crea_nada(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "accountant")

    response = _create(client)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    assert _patient_rows(seeder, tenant_id) == 0
    assert _counter(seeder, tenant_id) is None


@pytest.mark.parametrize("campo", list(RESERVED_FIELDS))
def test_s3_3_los_campos_reservados_del_cuerpo_se_rechazan(
    client: TestClient, auth_settings: Settings, seeder: Any, campo: str
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, **{campo: RESERVED_FIELDS[campo]})

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    assert _patient_rows(seeder, tenant_id) == 0


@pytest.mark.parametrize(
    "invalido",
    [
        {"telefono": None},
        {"dni": "30-111-222"},
        {"dni": "abcdefgh"},
        {"email": "no-es-email"},
        {"sexo": "indefinido"},
    ],
)
def test_s3_4_datos_invalidos_no_generan_historia_clinica(
    client: TestClient, auth_settings: Settings, seeder: Any, invalido: dict[str, Any]
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, **invalido)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    assert _patient_rows(seeder, tenant_id) == 0
    assert _counter(seeder, tenant_id) is None


def test_s3_5_recepcion_da_de_alta_la_ficha_y_sigue_fuera_de_lo_clinico(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "front_desk")

    created = _create(client, apellido="Recepción", nombre="Rita")

    assert created.status_code == 201, created.text
    assert created.json()["apellido"] == "Recepción"
    assert _ids(client.get(PATIENTS_URL)) == [created.json()["id"]]
    boundary = client.get(CLINICAL_URL)
    assert boundary.status_code == 403, boundary.text
    assert boundary.json()["code"] == "forbidden"


def test_s3_6_los_espacios_se_recortan_y_el_apellido_vacio_se_rechaza(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    vacio = _create(client, nombre="  Ana  ", apellido="   ")
    assert vacio.status_code == 422, vacio.text
    assert _patient_rows(seeder, tenant_id) == 0

    valido = _create(client, nombre="  Ana  ", apellido="  Pérez ")
    assert valido.status_code == 201, valido.text
    assert valido.json()["nombre"] == "Ana"
    assert valido.json()["apellido"] == "Pérez"


# --- S4: secuencia de historia clínica -------------------------------------


def test_s4_1_tres_altas_consecutivas_dan_000001_000002_y_000003(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    numeros = [
        _create(client, apellido=apellido, nombre=nombre, telefono=telefono).json()[
            "numero_historia_clinica"
        ]
        for apellido, nombre, telefono in (
            ("Zarate", "Bruno", "11 1111-0001"),
            ("Alvarez", "Ana", "11 1111-0002"),
            ("Benitez", "Carla", "11 1111-0003"),
        )
    ]

    assert numeros == ["000001", "000002", "000003"]
    # El listado ordena por apellido y nombre, no por número.
    assert [item["apellido"] for item in client.get(PATIENTS_URL).json()["patients"]] == [
        "Alvarez",
        "Benitez",
        "Zarate",
    ]


def test_s4_2_cada_tenant_arranca_su_propia_secuencia(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    seeder.patient(tenant_a, apellido="Aaa", nombre="Ana")

    _session_as(client, auth_settings, seeder, tenant_b, "owner")
    created = _create(client, apellido="Bbb", nombre="Beto")

    assert created.status_code == 201, created.text
    assert created.json()["numero_historia_clinica"] == "000001"
    assert _counter(seeder, tenant_a) == 1
    assert _counter(seeder, tenant_b) == 1


def test_s4_3_dar_de_baja_al_ultimo_no_recicla_su_numero(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")
    _create(client, apellido="Aaa", nombre="Uno", telefono="11 1111-0001")
    ultimo = _create(client, apellido="Bbb", nombre="Dos", telefono="11 1111-0002").json()
    assert ultimo["numero_historia_clinica"] == "000002"

    _soft_delete(seeder, UUID(ultimo["id"]))
    nuevo = _create(client, apellido="Ccc", nombre="Tres", telefono="11 1111-0003").json()

    assert nuevo["numero_historia_clinica"] == "000003"
    assert not _alive(seeder, UUID(ultimo["id"]))


def test_s4_6_el_formato_crece_por_encima_de_999999(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _set_counter(seeder, tenant_id, 999_999)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, apellido="Millón", nombre="Marta")

    assert response.status_code == 201, response.text
    assert response.json()["numero_historia_clinica"] == "1000000"


# --- S5: duplicado por DNI -------------------------------------------------


def test_s5_1_el_mismo_dni_responde_409_con_el_existente(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    existente = seeder.patient(tenant_id, apellido="Pérez", nombre="Ana", dni="30111222")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, apellido="Otra", nombre="Persona", dni="30111222")

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "patient_dni_duplicado"
    assert body["candidatos"][0]["id"] == str(existente)
    assert _patient_rows(seeder, tenant_id) == 1
    assert _counter(seeder, tenant_id) == 1


def test_s5_2_confirmar_duplicado_no_vence_la_regla_del_dni(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Pérez", nombre="Ana", dni="30111222")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(
        client, apellido="Pérez", nombre="Ana", dni="30111222", confirmar_duplicado=True
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "patient_dni_duplicado"
    assert _patient_rows(seeder, tenant_id) == 1


def test_s5_3_el_mismo_dni_en_otro_tenant_es_valido(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    seeder.patient(tenant_a, apellido="Pérez", nombre="Ana", dni="30111222")
    _session_as(client, auth_settings, seeder, tenant_b, "owner")

    response = _create(client, apellido="Pérez", nombre="Ana", dni="30111222")

    assert response.status_code == 201, response.text
    assert response.json()["numero_historia_clinica"] == "000001"


def test_s5_4_varios_pacientes_sin_dni_conviven(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    primera = _create(client, apellido="Sin", nombre="Dni", telefono="11 1111-0001")
    segunda = _create(client, apellido="Otro", nombre="Sin Dni", telefono="11 1111-0002")

    assert primera.status_code == segunda.status_code == 201
    assert primera.json()["dni"] is None
    assert primera.json()["numero_historia_clinica"] != segunda.json()["numero_historia_clinica"]


def test_s5_6_el_dni_de_un_paciente_dado_de_baja_sigue_bloqueando(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    baja = seeder.patient(
        tenant_id,
        apellido="Pérez",
        nombre="Ana",
        dni="30111222",
        deleted_at=datetime.now(UTC),
    )
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, apellido="Pérez", nombre="Ana", dni="30111222")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "patient_dni_duplicado"
    assert response.json()["candidatos"][0]["id"] == str(baja)
    assert _patient_rows(seeder, tenant_id) == 1


# --- S6: posible duplicado blando ------------------------------------------


def test_s6_1_nombre_y_apellido_equivalentes_disparan_la_confirmacion(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Pérez", nombre="Ana", telefono="11 4444-0000")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, apellido="PEREZ", nombre="ANA", telefono="11 5555-1111")

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "patient_posible_duplicado"
    assert set(body["candidatos"][0]) == {
        "id",
        "numero_historia_clinica",
        "nombre",
        "apellido",
        "dni",
        "telefono",
    }
    assert body["candidatos"][0]["apellido"] == "Pérez"
    assert _patient_rows(seeder, tenant_id) == 1


def test_s6_2_el_telefono_repetido_tambien_dispara_la_confirmacion(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Pérez", nombre="Ana", telefono="11 5555-1234")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, apellido="Gómez", nombre="Beto", telefono="(11) 5555-1234")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "patient_posible_duplicado"
    assert response.json()["candidatos"][0]["apellido"] == "Pérez"


def test_s6_3_confirmar_el_duplicado_crea_la_segunda_ficha(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(tenant_id, apellido="Pérez", nombre="Ana", telefono="11 4444-0000")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    confirmado = _create(
        client, apellido="Pérez", nombre="Ana", telefono="11 5555-1111", confirmar_duplicado=True
    )

    assert confirmado.status_code == 201, confirmado.text
    assert "confirmar_duplicado" not in confirmado.json()
    body = client.get(PATIENTS_URL).json()
    assert body["total"] == 2
    assert len({item["numero_historia_clinica"] for item in body["patients"]}) == 2


def test_s6_4_sin_coincidencias_el_alta_es_directa(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(
        client, apellido="Nuevo", nombre="Paciente", dni="30111222", telefono="11 0000-0000"
    )

    assert response.status_code == 201, response.text
    assert response.json()["numero_historia_clinica"] == "000001"


def test_s6_5_un_homonimo_de_otro_tenant_no_pide_confirmacion(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    seeder.patient(tenant_b, apellido="Pérez", nombre="Ana", telefono="11 5555-1234")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    response = _create(client, apellido="Pérez", nombre="Ana", telefono="11 5555-1234")

    assert response.status_code == 201, response.text


def test_s6_6_un_homonimo_dado_de_baja_no_dispara_la_confirmacion(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    seeder.patient(
        tenant_id,
        apellido="Pérez",
        nombre="Ana",
        telefono="11 4444-0000",
        deleted_at=datetime.now(UTC),
    )
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, apellido="Pérez", nombre="Ana", telefono="11 5555-1111")

    assert response.status_code == 201, response.text


def test_s6_7_el_409_acota_los_candidatos_a_cinco(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    for indice in range(7):
        seeder.patient(
            tenant_id,
            apellido=f"Candidato{indice}",
            nombre="Persona",
            telefono="11 5555-9999",
        )
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = _create(client, apellido="Nuevo", nombre="Paciente", telefono="11 5555-9999")

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "patient_posible_duplicado"
    assert len(body["candidatos"]) == 5
    assert _patient_rows(seeder, tenant_id) == 7


# --- S7: lectura por id ----------------------------------------------------


def test_s7_1_la_ficha_propia_se_lee_completa_sin_datos_internos(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    patient_id = seeder.patient(
        tenant_id,
        apellido="Pérez",
        nombre="Ana",
        dni="30111222",
        email="ana@example.com",
        sexo="femenino",
        domicilio={"calle": "Siempreviva", "numero": "742"},
    )
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.get(f"{PATIENTS_URL}/{patient_id}")

    assert response.status_code == 200, response.text
    patient = response.json()
    assert set(patient) == PATIENT_KEYS
    assert patient["numero_historia_clinica"] == "000001"
    assert patient["domicilio"] == {"calle": "Siempreviva", "numero": "742"}
    assert not (set(patient) & FORBIDDEN_KEYS)


def test_s7_2_un_id_ajeno_es_indistinguible_de_uno_inexistente(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    foreign = seeder.patient(tenant_b, apellido="Ajeno", nombre="Ficha")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    ajeno = client.get(f"{PATIENTS_URL}/{foreign}")
    inexistente = client.get(f"{PATIENTS_URL}/{uuid4()}")

    assert ajeno.status_code == inexistente.status_code == 404
    assert ajeno.json() == inexistente.json()
    assert ajeno.json()["code"] == "patient_not_found"


def test_s7_3_sin_patient_read_no_hay_lectura(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    patient_id = seeder.patient(tenant_id, apellido="Pérez", nombre="Ana", dni="30111222")
    _session_as(client, auth_settings, seeder, tenant_id, "external_lab")

    response = client.get(f"{PATIENTS_URL}/{patient_id}")

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    assert "30111222" not in response.text


# --- S8: actualización -----------------------------------------------------


def test_s8_1_se_actualizan_los_datos_de_contacto(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    patient_id = seeder.patient(tenant_id, apellido="Pérez", nombre="Ana")
    _session_as(client, auth_settings, seeder, tenant_id, "front_desk")

    response = client.patch(
        f"{PATIENTS_URL}/{patient_id}",
        json={"telefono": "11 4444-0000", "email": "nuevo@example.com"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["telefono"] == "11 4444-0000"
    assert response.json()["email"] == "nuevo@example.com"
    releido = client.get(f"{PATIENTS_URL}/{patient_id}").json()
    assert releido["telefono"] == "11 4444-0000"


@pytest.mark.parametrize("campo", list(RESERVED_FIELDS))
def test_s8_2_los_campos_reservados_no_se_pueden_modificar(
    client: TestClient, auth_settings: Settings, seeder: Any, campo: str
) -> None:
    tenant_id = _tenant(seeder)
    patient_id = seeder.patient(tenant_id, apellido="Pérez", nombre="Ana")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.patch(
        f"{PATIENTS_URL}/{patient_id}", json={campo: RESERVED_FIELDS[campo]}
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_request"
    assert client.get(f"{PATIENTS_URL}/{patient_id}").json()["apellido"] == "Pérez"


def test_s8_3_cambiar_el_dni_a_uno_ya_usado_responde_409(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    primero = seeder.patient(tenant_id, apellido="Pérez", nombre="Ana", dni="30111222")
    segundo = seeder.patient(tenant_id, apellido="Gómez", nombre="Beto", dni="30999888")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.patch(f"{PATIENTS_URL}/{segundo}", json={"dni": "30111222"})

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "patient_dni_duplicado"
    assert client.get(f"{PATIENTS_URL}/{segundo}").json()["dni"] == "30999888"
    assert client.get(f"{PATIENTS_URL}/{primero}").json()["dni"] == "30111222"


def test_s8_4_un_id_ajeno_responde_404_indistinguible(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_a = _tenant(seeder)
    tenant_b = _tenant(seeder)
    foreign = seeder.patient(tenant_b, apellido="Ajeno", nombre="Ficha")
    _session_as(client, auth_settings, seeder, tenant_a, "owner")

    ajeno = client.patch(f"{PATIENTS_URL}/{foreign}", json={"nombre": "Robado"})
    inexistente = client.patch(f"{PATIENTS_URL}/{uuid4()}", json={"nombre": "Robado"})

    assert ajeno.status_code == inexistente.status_code == 404
    assert ajeno.json() == inexistente.json()
    with seeder.engine.connect() as connection:
        nombre = connection.execute(
            text("SELECT nombre FROM patient WHERE id = :id"), {"id": foreign}
        ).scalar_one()
    assert nombre == "Ficha"


def test_s8_5_cambiar_el_nombre_actualiza_la_busqueda(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    patient_id = seeder.patient(tenant_id, apellido="Pérez", nombre="Ana")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    response = client.patch(f"{PATIENTS_URL}/{patient_id}", json={"apellido": "Gómez"})

    assert response.status_code == 200, response.text
    assert client.get(PATIENTS_URL, params={"q": "gomez"}).json()["total"] == 1
    assert client.get(PATIENTS_URL, params={"q": "perez"}).json()["total"] == 0


def test_s8_6_sin_patient_update_no_hay_modificacion(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    patient_id = seeder.patient(tenant_id, apellido="Pérez", nombre="Ana")
    _session_as(client, auth_settings, seeder, tenant_id, "professional")

    response = client.patch(f"{PATIENTS_URL}/{patient_id}", json={"nombre": "Robado"})

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    with seeder.engine.connect() as connection:
        nombre = connection.execute(
            text("SELECT nombre FROM patient WHERE id = :id"), {"id": patient_id}
        ).scalar_one()
    assert nombre == "Ana"


# --- S9: frontera clínica --------------------------------------------------


def test_s9_1_ninguna_respuesta_de_la_ficha_expone_campos_clinicos(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    patient_id = seeder.patient(
        tenant_id, apellido="Pérez", nombre="Ana", alergias="penicilina", alerta_clinica=True
    )
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    respuestas = [
        client.get(PATIENTS_URL),
        client.get(f"{PATIENTS_URL}/{patient_id}"),
        client.post(
            PATIENTS_URL,
            json=_alta(apellido="Nueva", nombre="Ficha", telefono="11 9876-5432"),
        ),
        client.patch(f"{PATIENTS_URL}/{patient_id}", json={"telefono": "11 3333-3333"}),
    ]

    prohibidas = {"alergias", "alerta_clinica", "clinical_record", "historia_clinica"}
    for response in respuestas:
        assert response.status_code in (200, 201), response.text
        assert not (_keys(response.json()) & prohibidas), response.text


def test_s9_2_recepcion_administra_la_ficha_y_sigue_fuera_de_la_historia_clinica(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "front_desk")

    creado = _create(client, apellido="Recepción", nombre="Rita")
    patient_id = creado.json()["id"]
    leido = client.get(f"{PATIENTS_URL}/{patient_id}")
    actualizado = client.patch(f"{PATIENTS_URL}/{patient_id}", json={"telefono": "11 2222-2222"})
    boundary = client.get(CLINICAL_URL)

    assert creado.status_code == 201, creado.text
    assert leido.status_code == 200, leido.text
    assert actualizado.status_code == 200, actualizado.text
    assert boundary.status_code == 403, boundary.text
    assert boundary.json()["code"] == "forbidden"


@pytest.mark.parametrize("campo", ["alergias", "alerta_clinica"])
def test_s9_3_enviar_un_campo_clinico_es_un_error_de_contrato(
    client: TestClient, auth_settings: Settings, seeder: Any, campo: str
) -> None:
    tenant_id = _tenant(seeder)
    patient_id = seeder.patient(tenant_id, apellido="Pérez", nombre="Ana")
    _session_as(client, auth_settings, seeder, tenant_id, "owner")

    alta = _create(client, apellido="Nueva", nombre="Ficha", **{campo: RESERVED_FIELDS[campo]})
    patch = client.patch(
        f"{PATIENTS_URL}/{patient_id}", json={campo: RESERVED_FIELDS[campo]}
    )

    assert alta.status_code == patch.status_code == 422
    assert alta.json()["code"] == patch.json()["code"] == "invalid_request"
    with seeder.engine.connect() as connection:
        row = connection.execute(
            text("SELECT alergias, alerta_clinica FROM patient WHERE id = :id"),
            {"id": patient_id},
        ).one()
    assert row.alergias is None
    assert row.alerta_clinica is False


# --- 4.6: la sonda clínica no se toca --------------------------------------


def test_4_6_los_roles_clinicos_siguen_recibiendo_501_en_la_sonda(
    client: TestClient, auth_settings: Settings, seeder: Any
) -> None:
    tenant_id = _tenant(seeder)
    _session_as(client, auth_settings, seeder, tenant_id, "professional")

    response = client.get(CLINICAL_URL)

    assert response.status_code == 501, response.text
    assert response.json()["code"] == "capability_pending"
