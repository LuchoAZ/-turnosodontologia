"""Validación pura de ventanas y solapes de disponibilidad (design D5/D6).

Sin imports de base: el servicio la usa como precondición y los unitarios la
ejercitan sin contenedor. Los mensajes explican la regla (RN-AG-03) y nunca
ecoan el valor recibido.
"""

from __future__ import annotations

from datetime import date, time


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def validate_window(
    *,
    hora_inicio: time,
    hora_fin: time,
    slot_min: int,
    buffer_previo_min: int,
    buffer_posterior_min: int,
    fecha_desde: date,
    fecha_hasta: date | None,
) -> list[str]:
    """Devuelve los motivos por los que la ventana no es válida (vacío = válida)."""
    issues: list[str] = []

    if hora_fin <= hora_inicio:
        issues.append("la hora de fin debe ser posterior a la hora de inicio")

    if slot_min <= 0:
        issues.append("el slot debe ser mayor que cero")
    elif hora_fin > hora_inicio:
        total = _minutes(hora_fin) - _minutes(hora_inicio)
        if total % slot_min != 0:
            issues.append("la ventana debe ser múltiplo exacto del slot")

    if buffer_previo_min < 0:
        issues.append("el buffer previo no puede ser negativo")
    if buffer_posterior_min < 0:
        issues.append("el buffer posterior no puede ser negativo")
    if (
        buffer_previo_min >= 0
        and buffer_posterior_min >= 0
        and slot_min > 0
        and buffer_previo_min + buffer_posterior_min >= slot_min
    ):
        issues.append("los buffers deben dejar al menos un minuto de turno en el slot")

    if fecha_hasta is not None and fecha_hasta < fecha_desde:
        issues.append("la fecha de fin no puede ser anterior a la fecha de inicio")

    return issues


def ranges_overlap(
    start_a: date,
    end_a: date | None,
    start_b: date,
    end_b: date | None,
) -> bool:
    """Intersección de dos rangos de fechas; ``None`` en el fin significa abierto."""
    if end_b is not None and start_a > end_b:
        return False
    return not (end_a is not None and start_b > end_a)


def time_ranges_overlap(
    start_a: time,
    end_a: time,
    start_b: time,
    end_b: time,
) -> bool:
    """Intersección de dos ventanas horarias; tocarse en el extremo no es solape."""
    return start_a < end_b and end_a > start_b
