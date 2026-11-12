"""Validación pura de ventanas y solapes de disponibilidad (tasks 2.3/2.5).

``validate_window`` y ``ranges_overlap`` no importan SQLAlchemy: son la unidad
del ciclo RED→GREEN y la precondición que el servicio corre antes de escribir
cualquier fila. Un test extra comprueba que el módulo siga siendo puro.
"""

from __future__ import annotations

import sys
from datetime import date, time

import pytest
from app.domain.clinic.validation import ranges_overlap, time_ranges_overlap, validate_window

VALID = {
    "hora_inicio": time(9, 0),
    "hora_fin": time(12, 0),
    "slot_min": 30,
    "buffer_previo_min": 10,
    "buffer_posterior_min": 15,
    "fecha_desde": date(2026, 11, 16),
    "fecha_hasta": None,
}


def test_una_ventana_correcta_no_tiene_motivos() -> None:
    assert validate_window(**VALID) == []


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"hora_inicio": time(12, 0), "hora_fin": time(12, 0)}, "posterior"),
        ({"hora_inicio": time(13, 0), "hora_fin": time(12, 0)}, "posterior"),
        ({"hora_fin": time(10, 10)}, "múltiplo"),
        ({"slot_min": 0}, "slot"),
        ({"buffer_previo_min": -1}, "buffer"),
        ({"buffer_posterior_min": -5}, "buffer"),
        ({"buffer_previo_min": 20, "buffer_posterior_min": 10}, "buffer"),
        ({"fecha_hasta": date(2026, 11, 1)}, "fecha"),
    ],
)
def test_cada_regla_invalida_reporta_su_motivo(changes: dict[str, object], fragment: str) -> None:
    issues = validate_window(**{**VALID, **changes})
    assert issues, changes
    assert any(fragment in issue.lower() for issue in issues), issues


def test_una_ventana_que_cierra_exacta_en_slots_es_valida() -> None:
    assert validate_window(**{**VALID, "hora_inicio": time(8, 0), "hora_fin": time(9, 0)}) == []


def test_los_buffers_que_dejan_cero_minutos_de_turno_se_rechazan() -> None:
    issues = validate_window(**{**VALID, "slot_min": 15, "buffer_previo_min": 10,
                                "buffer_posterior_min": 5})
    assert issues


def test_fecha_hasta_igual_a_fecha_desde_es_valida() -> None:
    same = VALID["fecha_desde"]
    assert validate_window(**{**VALID, "fecha_hasta": same}) == []


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ((date(2026, 1, 1), None), (date(2026, 6, 1), None), True),
        ((date(2026, 1, 1), date(2026, 3, 1)), (date(2026, 4, 1), None), False),
        ((date(2026, 1, 1), date(2026, 3, 1)), (date(2026, 3, 1), date(2026, 5, 1)), True),
        ((date(2026, 1, 1), date(2026, 3, 1)), (date(2026, 3, 2), None), False),
        ((date(2026, 1, 1), None), (date(2025, 1, 1), date(2025, 12, 31)), False),
    ],
)
def test_ranges_overlap_trata_none_como_infinito(
    left: tuple[date, date | None],
    right: tuple[date, date | None],
    expected: bool,
) -> None:
    assert ranges_overlap(left[0], left[1], right[0], right[1]) is expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((time(9, 0), time(12, 0)), (time(11, 0), time(14, 0)), True),
        ((time(9, 0), time(12, 0)), (time(12, 0), time(14, 0)), False),
        ((time(9, 0), time(12, 0)), (time(9, 0), time(12, 0)), True),
        ((time(9, 0), time(12, 0)), (time(8, 0), time(9, 0)), False),
    ],
)
def test_time_ranges_overlap_no_considera_solape_tocarse(
    a: tuple[time, time], b: tuple[time, time], expected: bool
) -> None:
    assert time_ranges_overlap(a[0], a[1], b[0], b[1]) is expected


def test_el_modulo_de_validacion_no_depende_de_la_base() -> None:
    from app.domain.clinic import validation

    source = sys.modules[validation.__name__].__loader__.get_source(validation.__name__)  # type: ignore[attr-defined]
    assert source is not None
    assert "sqlalchemy" not in source.lower()
    assert "app.models" not in source
