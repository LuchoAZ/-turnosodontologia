"""Contrato Pydantic del turno y cálculo del rango (task 1.1, design D3/D5).

Dos grupos de casos:

* **Schema** — lo que el payload acepta y lo que no: ``fin``/``duracion_min``
  enviados por el cliente son ``422`` (``extra="forbid"``), ``inicio`` sin offset
  es ``422`` y ``tipo_practica`` fuera del enum del dominio es ``422``. Lo que
  sale (``AppointmentOut``) no expone ``tenant_id``.
* **Rango** — ``resolve_turno_range`` es puro: duración por ``slot_min`` de la
  regla que declara el tipo, si no ``duracion_default_min``; buffers snapshot de
  la regla aplicable; rango bloqueado semiabierto; duración ``<= 0`` es error de
  negocio (``duracion_invalida``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
from app.domain.agenda.appointments.errors import AgendaError, AgendaErrorCode
from app.domain.agenda.appointments.range import ReglaTurno, TurnoRange, resolve_turno_range
from app.schemas.appointments import AppointmentOut, CreateAppointment, TipoPractica
from pydantic import ValidationError

# Lunes 16/11/2026 09:00 en Buenos Aires (UTC-3).
INICIO_UTC = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
TZ = "America/Argentina/Buenos_Aires"


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "professional_id": uuid4(),
        "chair_id": uuid4(),
        "patient_id": uuid4(),
        "inicio": "2026-11-16T09:00:00-03:00",
        "tipo_practica": "endodoncia",
    }
    base.update(overrides)
    return base


def _regla(**overrides: object) -> ReglaTurno:
    base: dict[str, object] = {
        "professional_id": None,
        "chair_id": None,
        "dia_semana": 0,
        "hora_inicio": time(9, 0),
        "hora_fin": time(12, 0),
        "slot_min": 30,
        "buffer_previo_min": 0,
        "buffer_posterior_min": 0,
        "fecha_desde": date(2026, 1, 1),
        "fecha_hasta": None,
        "tipo_practica": None,
    }
    base.update(overrides)
    return ReglaTurno(**base)  # type: ignore[arg-type]


def _resolver(
    *,
    inicio: datetime = INICIO_UTC,
    tipo_practica: str | None = "endodoncia",
    professional_id: UUID | None = None,
    chair_id: UUID | None = None,
    duracion_default_min: int = 30,
    reglas: list[ReglaTurno] | None = None,
    timezone: str = TZ,
) -> TurnoRange:
    return resolve_turno_range(
        inicio=inicio,
        tipo_practica=tipo_practica,
        professional_id=professional_id or uuid4(),
        chair_id=chair_id or uuid4(),
        duracion_default_min=duracion_default_min,
        reglas=reglas or [],
        timezone=timezone,
    )


# --- Schema ----------------------------------------------------------------


def test_el_payload_valido_normaliza_inicio_a_utc() -> None:
    turno = CreateAppointment.model_validate(_payload())
    assert turno.inicio == INICIO_UTC
    assert turno.inicio.utcoffset() == timedelta(0)
    assert turno.tipo_practica is TipoPractica.endodoncia


def test_fin_y_duracion_no_se_aceptan_porque_los_deriva_el_servidor() -> None:
    for campo, valor in (("fin", "2026-11-16T10:00:00-03:00"), ("duracion_min", 60)):
        with pytest.raises(ValidationError) as failure:
            CreateAppointment.model_validate(_payload(**{campo: valor}))
        assert any(error["loc"] == (campo,) for error in failure.value.errors())


def test_el_payload_no_acepta_estado_ni_origen_del_cliente() -> None:
    for campo, valor in (("estado", "confirmado"), ("origen", "whatsapp")):
        with pytest.raises(ValidationError):
            CreateAppointment.model_validate(_payload(**{campo: valor}))


def test_un_tenant_id_en_el_body_se_ignora_en_vez_de_ser_422() -> None:
    ajeno = uuid4()
    payload = _payload(tenant_id=str(ajeno))
    turno = CreateAppointment.model_validate(payload)
    assert "tenant_id" not in turno.model_dump()
    assert turno.professional_id == payload["professional_id"]


def test_inicio_sin_offset_es_un_error_de_contrato() -> None:
    with pytest.raises(ValidationError):
        CreateAppointment.model_validate(_payload(inicio="2026-11-20T09:00:00"))


def test_tipo_practica_fuera_del_enum_es_un_error_de_contrato() -> None:
    with pytest.raises(ValidationError) as failure:
        CreateAppointment.model_validate(_payload(tipo_practica="blanqueamiento"))
    assert any(error["loc"] == ("tipo_practica",) for error in failure.value.errors())


def test_patient_id_es_opcional_porque_hay_turnos_sin_paciente() -> None:
    sin_paciente = _payload()
    del sin_paciente["patient_id"]
    assert CreateAppointment.model_validate(sin_paciente).patient_id is None


def test_los_campos_obligatorios_faltantes_son_error() -> None:
    for campo in ("professional_id", "chair_id", "inicio"):
        payload = _payload()
        del payload[campo]
        with pytest.raises(ValidationError) as failure:
            CreateAppointment.model_validate(payload)
        assert any(error["loc"] == (campo,) for error in failure.value.errors())


def test_la_respuesta_no_expone_tenant_id() -> None:
    assert "tenant_id" not in AppointmentOut.model_fields
    for campo in ("id", "inicio", "fin", "duracion_min", "estado", "origen"):
        assert campo in AppointmentOut.model_fields


# --- Rango -----------------------------------------------------------------


def test_la_duracion_sale_del_slot_de_la_regla_que_declara_el_tipo() -> None:
    rango = _resolver(
        reglas=[_regla(slot_min=45, tipo_practica="Endodoncia", buffer_previo_min=10)],
    )
    assert rango.duracion_min == 45
    assert rango.fin == INICIO_UTC + timedelta(minutes=45)
    assert rango.buffer_previo_min == 10


def test_sin_regla_aplicable_usa_la_duracion_del_profesional() -> None:
    rango = _resolver(duracion_default_min=40, reglas=[])
    assert rango.duracion_min == 40
    assert rango.fin == INICIO_UTC + timedelta(minutes=40)
    assert (rango.buffer_previo_min, rango.buffer_posterior_min) == (0, 0)


def test_el_rango_bloqueado_incluye_los_buffers() -> None:
    rango = _resolver(
        reglas=[
            _regla(
                slot_min=30,
                tipo_practica="endodoncia",
                buffer_previo_min=10,
                buffer_posterior_min=15,
            )
        ]
    )
    assert rango.bloqueado_desde == INICIO_UTC - timedelta(minutes=10)
    assert rango.bloqueado_hasta == INICIO_UTC + timedelta(minutes=45)


def test_una_regla_generica_aporta_buffers_pero_no_duracion_por_tipo() -> None:
    rango = _resolver(
        duracion_default_min=30,
        reglas=[_regla(slot_min=60, tipo_practica=None, buffer_posterior_min=20)],
    )
    assert rango.duracion_min == 30
    assert rango.buffer_posterior_min == 20


def test_la_regla_de_otro_dia_o_fuera_de_ventana_no_aplica() -> None:
    for regla in (
        _regla(dia_semana=2, tipo_practica="endodoncia", slot_min=90),
        _regla(
            hora_inicio=time(15, 0),
            hora_fin=time(18, 0),
            tipo_practica="endodoncia",
            slot_min=90,
        ),
        _regla(fecha_desde=date(2026, 12, 1), tipo_practica="endodoncia", slot_min=90),
        _regla(fecha_hasta=date(2026, 10, 1), tipo_practica="endodoncia", slot_min=90),
    ):
        assert _resolver(reglas=[regla], duracion_default_min=30).duracion_min == 30


def test_la_regla_de_otro_profesional_o_sillon_no_aplica() -> None:
    ajeno = uuid4()
    for regla in (
        _regla(professional_id=ajeno, tipo_practica="endodoncia", slot_min=90),
        _regla(chair_id=ajeno, tipo_practica="endodoncia", slot_min=90),
    ):
        assert _resolver(reglas=[regla], duracion_default_min=30).duracion_min == 30


def test_el_match_del_tipo_ignora_mayusculas_y_acentos() -> None:
    rango = _resolver(
        tipo_practica="cirugia",
        reglas=[_regla(slot_min=75, tipo_practica="Cirugía")],
    )
    assert rango.duracion_min == 75


def test_la_regla_del_tipo_gana_a_la_generica_del_mismo_horario() -> None:
    rango = _resolver(
        reglas=[
            _regla(slot_min=30, tipo_practica=None, buffer_previo_min=5),
            _regla(slot_min=60, tipo_practica="endodoncia", buffer_previo_min=10),
        ]
    )
    assert rango.duracion_min == 60
    assert rango.buffer_previo_min == 10


def test_una_duracion_no_positiva_es_error_de_negocio() -> None:
    for kwargs in (
        {"duracion_default_min": 0},
        {"duracion_default_min": -5},
        {"reglas": [_regla(slot_min=0, tipo_practica="endodoncia")]},
    ):
        with pytest.raises(AgendaError) as failure:
            _resolver(**kwargs)  # type: ignore[arg-type]
        assert failure.value.code is AgendaErrorCode.duracion_invalida
        assert failure.value.status_code == 409
        assert failure.value.to_payload()["motivo"] == "duracion_invalida"
