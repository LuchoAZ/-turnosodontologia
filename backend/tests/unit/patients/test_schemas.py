"""DTOs de pacientes: entrada estricta y salida sin campos internos (task 4.1, D7).

``extra="forbid"`` convierte un ``tenant_id`` en el body en ``422`` global; el
``PatientOut`` es una lista blanca sin ``tenant_id``, ``deleted_at``,
``alergias`` ni ``alerta_clinica`` (RN-CMP-04).
"""

from __future__ import annotations

from typing import Any

import pytest
from app.schemas.patients import (
    Domicilio,
    PatientCandidate,
    PatientCreate,
    PatientOut,
    PatientUpdate,
    Sexo,
)
from pydantic import ValidationError

VALIDO: dict[str, Any] = {
    "nombre": "Ana",
    "apellido": "Pérez",
    "telefono": "11 5555-1234",
    "dni": "30111222",
    # ``EmailStr`` rechaza los TLD special-use (``.test``, ``.invalid``): se usa
    # ``example.com``, también reservado por IANA para documentación.
    "email": "ana.perez@example.com",
}


def test_el_alta_minima_solo_necesita_nombre_apellido_y_telefono() -> None:
    alta = PatientCreate(nombre="Ana", apellido="Pérez", telefono="11 5555-1234")
    assert alta.dni is None
    assert alta.confirmar_duplicado is False
    assert alta.sexo is None


def test_nombre_y_apellido_se_recortan() -> None:
    alta = PatientCreate(nombre="  Ana  ", apellido="  Pérez ", telefono="11")
    assert (alta.nombre, alta.apellido) == ("Ana", "Pérez")


@pytest.mark.parametrize("campo", ["nombre", "apellido"])
def test_nombre_y_apellido_vacios_despues_del_trim_se_rechazan(campo: str) -> None:
    with pytest.raises(ValidationError):
        PatientCreate(**{**VALIDO, campo: "   "})


def test_el_telefono_es_obligatorio() -> None:
    with pytest.raises(ValidationError):
        PatientCreate(nombre="Ana", apellido="Pérez")


@pytest.mark.parametrize("dni", ["123456", "123456789012", "30-111-222", "abcdefgh"])
def test_el_dni_fuera_de_7_a_11_digitos_se_rechaza(dni: str) -> None:
    with pytest.raises(ValidationError):
        PatientCreate(**{**VALIDO, "dni": dni})


@pytest.mark.parametrize("dni", [None, "1234567", "30111222", "12345678901"])
def test_el_dni_valido_o_ausente_se_acepta(dni: str | None) -> None:
    assert PatientCreate(**{**VALIDO, "dni": dni}).dni == dni


def test_un_email_invalido_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        PatientCreate(**{**VALIDO, "email": "no-es-email"})


def test_un_sexo_fuera_del_enum_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        PatientCreate(**{**VALIDO, "sexo": "indefinido"})
    assert PatientCreate(**{**VALIDO, "sexo": "no_declara"}).sexo is Sexo.no_declara


@pytest.mark.parametrize(
    "campo",
    ["tenant_id", "numero_historia_clinica", "deleted_at", "alergias", "alerta_clinica"],
)
def test_los_campos_reservados_del_alta_se_rechazan(campo: str) -> None:
    with pytest.raises(ValidationError):
        PatientCreate(**{**VALIDO, campo: "x"})


def test_el_alta_no_expone_confirmar_duplicado_en_la_salida() -> None:
    assert "confirmar_duplicado" not in PatientOut.model_fields


def test_el_patch_distingue_no_enviado_de_null() -> None:
    solo_telefono = PatientUpdate(telefono="11 4444-0000")
    assert solo_telefono.model_dump(exclude_unset=True) == {"telefono": "11 4444-0000"}

    email_vacio = PatientUpdate(email=None)
    assert email_vacio.model_dump(exclude_unset=True) == {"email": None}


@pytest.mark.parametrize(
    "campo",
    ["tenant_id", "numero_historia_clinica", "deleted_at", "alergias", "alerta_clinica"],
)
def test_los_campos_reservados_del_patch_se_rechazan(campo: str) -> None:
    with pytest.raises(ValidationError):
        PatientUpdate(**{campo: "x"})


def test_la_salida_es_una_lista_blanca_sin_campos_internos() -> None:
    assert set(PatientOut.model_fields) == {
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
    for prohibido in ("tenant_id", "deleted_at", "alergias", "alerta_clinica", "user_id"):
        assert prohibido not in PatientOut.model_fields


def test_el_domicilio_no_acepta_campos_extra() -> None:
    with pytest.raises(ValidationError):
        Domicilio(calle="Siempreviva", numero="742", extra="x")
    assert Domicilio(calle="Siempreviva", localidad="Springfield").localidad == "Springfield"


def test_el_candidato_tiene_los_seis_campos_del_409() -> None:
    assert set(PatientCandidate.model_fields) == {
        "id",
        "numero_historia_clinica",
        "nombre",
        "apellido",
        "dni",
        "telefono",
    }
