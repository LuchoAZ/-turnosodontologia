"""Cálculo puro del rango del turno (task 1.1, design D3; RN-AG-03).

``resolve_turno_range`` es el seam de TDD del change: sin ORM, sin base y sin
reloj. Recibe el ``inicio`` en UTC, el ``tipo_practica`` pedido, las reglas de
disponibilidad candidatas y la duración por defecto del profesional, y devuelve el
rango que se persiste:

* **Duración base** — ``slot_min`` de la regla aplicable **que declara el
  ``tipo_practica``**; si ninguna lo declara (o no hay regla aplicable), la
  ``duracion_default_min`` del profesional.
* **Buffers** — snapshot de la regla aplicable aunque no declare el tipo (son
  tiempo real de higiene, RN-AG-03); sin regla, 0/0.
* **Rango clínico** — ``[inicio, fin)`` con ``fin = inicio + duracion_min``.
* **Rango bloqueado** — ``[inicio - buffer_previo, fin + buffer_posterior)``, el
  que usan el pre-chequeo y el ``EXCLUDE`` de la base.
* **Duración ``<= 0``** — error de negocio ``duracion_invalida`` (nunca un turno
  de duración cero).

La regla aplicable es la que matchea profesional (o ``NULL`` = cualquiera),
sillón (o ``NULL``), día de la semana y ventana horaria **en la zona del tenant**,
y el rango de fechas vigente. Entre varias, gana la que declara el tipo pedido;
si empatan, la más específica (profesional + sillón > uno solo > genérica).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.domain.agenda.appointments.errors import AgendaError, AgendaErrorCode
from app.domain.patients.normalize import normalizar_texto


@dataclass(frozen=True)
class ReglaTurno:
    """Vista inmutable de una ``availability_rule`` para el cálculo (sin ORM)."""

    professional_id: UUID | None
    chair_id: UUID | None
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    slot_min: int
    buffer_previo_min: int = 0
    buffer_posterior_min: int = 0
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    tipo_practica: str | None = None


@dataclass(frozen=True)
class TurnoRange:
    """Rango resuelto del turno, con los buffers ya congelados."""

    inicio: datetime
    fin: datetime
    duracion_min: int
    buffer_previo_min: int
    buffer_posterior_min: int

    @property
    def bloqueado_desde(self) -> datetime:
        """Inicio del rango bloqueado: ``inicio - buffer_previo``."""
        return self.inicio - timedelta(minutes=self.buffer_previo_min)

    @property
    def bloqueado_hasta(self) -> datetime:
        """Fin exclusivo del rango bloqueado: ``fin + buffer_posterior``."""
        return self.fin + timedelta(minutes=self.buffer_posterior_min)


def _normalizar_practica(valor: str | None) -> str | None:
    if valor is None:
        return None
    normalizado = normalizar_texto(valor)
    return normalizado or None


def _aplica(regla: ReglaTurno, *, local: datetime) -> bool:
    """Día, ventana y vigencia de la regla contra el ``inicio`` local del tenant."""
    fecha_local = local.date()
    return (
        regla.dia_semana == local.weekday()
        and regla.hora_inicio <= local.time() < regla.hora_fin
        and (regla.fecha_desde is None or fecha_local >= regla.fecha_desde)
        and (regla.fecha_hasta is None or fecha_local <= regla.fecha_hasta)
    )


def _alcance(regla: ReglaTurno, *, professional_id: UUID, chair_id: UUID) -> bool:
    """La regla aplica al par pedido: ``NULL`` significa "cualquiera"."""
    professional_ok = regla.professional_id is None or regla.professional_id == professional_id
    chair_ok = regla.chair_id is None or regla.chair_id == chair_id
    return professional_ok and chair_ok


def _especificidad(regla: ReglaTurno, *, tipo: str | None) -> tuple[int, int]:
    """Ordena candidatas: tipo declarado > tipo genérico; más alcance > menos."""
    declara_tipo = tipo is not None and _normalizar_practica(regla.tipo_practica) == tipo
    return (
        1 if declara_tipo else 0,
        int(regla.professional_id is not None) + int(regla.chair_id is not None),
    )


def resolve_turno_range(
    *,
    inicio: datetime,
    tipo_practica: str | None,
    professional_id: UUID,
    chair_id: UUID,
    duracion_default_min: int,
    reglas: Sequence[ReglaTurno],
    timezone: str,
) -> TurnoRange:
    """Resuelve duración, buffers y rango bloqueado del turno (RN-AG-03)."""
    local = inicio.astimezone(ZoneInfo(timezone))
    tipo = _normalizar_practica(tipo_practica)

    candidatas = [
        regla
        for regla in reglas
        if _aplica(regla, local=local)
        and _alcance(regla, professional_id=professional_id, chair_id=chair_id)
    ]
    aplicable = max(candidatas, key=lambda r: _especificidad(r, tipo=tipo), default=None)

    declara_tipo = (
        aplicable is not None
        and tipo is not None
        and _normalizar_practica(aplicable.tipo_practica) == tipo
    )
    duracion = (
        aplicable.slot_min if (aplicable is not None and declara_tipo) else duracion_default_min
    )

    if duracion <= 0:
        raise AgendaError(
            AgendaErrorCode.duracion_invalida,
            motivo="duracion_invalida",
        )

    return TurnoRange(
        inicio=inicio,
        fin=inicio + timedelta(minutes=duracion),
        duracion_min=duracion,
        buffer_previo_min=aplicable.buffer_previo_min if aplicable else 0,
        buffer_posterior_min=aplicable.buffer_posterior_min if aplicable else 0,
    )
