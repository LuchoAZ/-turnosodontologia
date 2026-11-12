"""Garantía dura de la base: doble booking concurrente (task 4.1; RN-AG-02, S2.5).

El escenario no se puede simular con el pre-chequeo apagado y una sola sesión: la
carrera ocurre **dentro** de la base. La prueba lo fuerza de forma determinista:

1. La sesión A inserta el turno y **no** commitea: la entrada del ``EXCLUDE`` queda
   reservada pero invisible para cualquier otra transacción.
2. El thread B llama al servicio con el mismo rango. Su pre-chequeo (``SELECT`` en
   ``READ COMMITTED``) no ve la fila de A, así que llega al ``INSERT`` y **se
   bloquea** esperando la entrada del índice.
3. A commitea. B recibe la *exclusion violation* ``23P01`` y el ``SAVEPOINT`` del
   servicio la traduce al mismo contrato ``409`` de aplicación, con ``recurso`` y
   ``rangoEnConflicto`` del turno que ganó.

Se verifica que B está vivo mientras A no commitea: eso demuestra que el rechazo
vino de la base y no de la validación de aplicación.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any
from uuid import uuid4

from _agenda import agenda, payload, rows
from app.config import Settings
from app.db.engine import create_db_engine, create_session_factory
from app.db.tenant_context import set_tenant_context
from app.domain.agenda.appointments import service
from app.domain.agenda.appointments.errors import AgendaError, AgendaErrorCode
from app.schemas.appointments import CreateAppointment
from sqlalchemy import text
from sqlalchemy.engine import Engine

INSERT_SQL = text(
    """
    INSERT INTO appointment
        (id, tenant_id, professional_id, chair_id, inicio, fin, duracion_min,
         buffer_previo_min, buffer_posterior_min, estado, origen)
    VALUES
        (:id, :tenant_id, :professional_id, :chair_id, :inicio, :fin, 30,
         0, 0, CAST('pendiente' AS appointment_estado), CAST('recepcion' AS appointment_origen))
    """
)


def test_s2_5_con_dos_altas_simultaneas_la_base_rechaza_el_doble_booking(
    auth_settings: Settings, seeder: Any, db_engine: Engine
) -> None:
    data = agenda(seeder, prefix="concurrencia")
    engine = create_db_engine(auth_settings)
    factory = create_session_factory(engine)
    turno = CreateAppointment.model_validate(payload(data))

    ganadora = factory()
    resultado: dict[str, Any] = {}
    try:
        set_tenant_context(ganadora.connection(), data["tenant_id"])
        ganadora.execute(
            INSERT_SQL,
            {
                "id": uuid4(),
                "tenant_id": data["tenant_id"],
                "professional_id": data["professional_id"],
                "chair_id": data["chair_id"],
                "inicio": turno.inicio,
                "fin": turno.inicio + timedelta(minutes=30),
            },
        )

        def _crear_perdedora() -> None:
            sesion = factory()
            try:
                set_tenant_context(sesion.connection(), data["tenant_id"])
                resultado["turno"] = service.create_appointment(
                    sesion,
                    tenant_id=data["tenant_id"],
                    user_id=data["user_id"],
                    payload=turno,
                )
            except AgendaError as exc:
                resultado["error"] = exc
                sesion.rollback()
            finally:
                sesion.close()

        hilo = threading.Thread(target=_crear_perdedora)
        hilo.start()
        hilo.join(timeout=3)
        # B no puede avanzar: está esperando la entrada del EXCLUDE de A.
        assert hilo.is_alive(), "el INSERT de B no se bloqueó en el EXCLUDE"

        ganadora.commit()
        hilo.join(timeout=30)
        assert not hilo.is_alive(), "B quedó colgado después del commit de A"
    finally:
        ganadora.close()
        engine.dispose()

    error = resultado["error"]
    assert isinstance(error, AgendaError)
    assert error.code is AgendaErrorCode.turno_solapado
    assert error.status_code == 409
    assert error.recurso in {"professional", "chair"}
    assert error.rango_en_conflicto is not None
    assert error.to_payload()["motivo"] == "turno_solapado"
    # Solo sobrevive el turno de la transacción que commiteó.
    assert len(rows(db_engine, data["tenant_id"])) == 1
