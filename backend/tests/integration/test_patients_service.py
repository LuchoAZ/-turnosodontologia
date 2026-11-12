"""Concurrencia real del alta de pacientes (tasks 4.4, escenarios S4.4/S4.5/S5.5).

HTTP no puede probar dos transacciones simultáneas: ``TestClient`` corre la app
en el mismo proceso y cada request abre y cierra su sesión en serie. Acá se usan
dos sesiones de verdad (dos conexiones del mismo engine como ``odontologia_app``)
en dos hilos, con el GUC del tenant fijado en cada una.

Lo que se prueba es la garantía del contador: el upsert sobre ``patient_counter``
toma un lock de fila y serializa las altas, y si una transacción falla el
incremento se revierte con ella, sin dejar huecos en la secuencia.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from app.config import Settings
from app.db.engine import create_db_engine, create_session_factory
from app.db.tenant_context import set_tenant_context
from app.domain.patients import service
from app.domain.patients.errors import PatientError, PatientErrorCode
from app.schemas.patients import PatientCreate
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass
class Resultado:
    paciente: dict[str, Any] | None = None
    code: str | None = None


def _factory(settings: Settings) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_db_engine(settings)
    return engine, create_session_factory(engine)


def _alta(factory: sessionmaker[Session], tenant_id: UUID, payload: PatientCreate) -> Resultado:
    db = factory()
    try:
        set_tenant_context(db.connection(), tenant_id)
        creado = service.create_patient(db, tenant_id=tenant_id, payload=payload)
        return Resultado(paciente=creado.model_dump(mode="json"))
    except PatientError as exc:
        return Resultado(code=exc.code.value)
    finally:
        db.close()


def _en_paralelo(
    factory: sessionmaker[Session],
    tenant_id: UUID,
    payloads: list[PatientCreate],
    *,
    barrier: threading.Barrier | None = None,
) -> list[Resultado]:
    def correr(payload: PatientCreate) -> Resultado:
        if barrier is not None:
            barrier.wait(timeout=15)
        return _alta(factory, tenant_id, payload)

    with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
        return list(pool.map(correr, payloads))


def _counter(seeder: Any, tenant_id: UUID) -> int | None:
    with seeder.engine.connect() as connection:
        return connection.execute(
            text("SELECT ultimo_numero FROM patient_counter WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar_one_or_none()


def _numeros(seeder: Any, tenant_id: UUID) -> list[str]:
    with seeder.engine.connect() as connection:
        return sorted(
            connection.execute(
                text("SELECT numero_historia_clinica FROM patient WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).scalars()
        )


@pytest.fixture
def factory(auth_settings: Settings) -> Any:
    engine, session_factory = _factory(auth_settings)
    try:
        yield session_factory
    finally:
        engine.dispose()


def test_s4_4_dos_altas_concurrentes_no_colisionan(
    factory: sessionmaker[Session], seeder: Any
) -> None:
    tenant_id = seeder.tenant(slug="conc-a", nombre="Clínica Concurrente")

    resultados = _en_paralelo(
        factory,
        tenant_id,
        [
            PatientCreate(nombre="Ana", apellido="Alvarez", telefono="11 1111-0001"),
            PatientCreate(nombre="Beto", apellido="Benitez", telefono="11 1111-0002"),
        ],
    )

    numeros = sorted(r.paciente["numero_historia_clinica"] for r in resultados if r.paciente)
    assert len(numeros) == 2, resultados
    assert numeros == ["000001", "000002"]
    assert _counter(seeder, tenant_id) == 2
    assert _numeros(seeder, tenant_id) == ["000001", "000002"]


def test_s4_5_una_alta_fallida_por_dni_no_deja_hueco(
    factory: sessionmaker[Session], seeder: Any
) -> None:
    tenant_id = seeder.tenant(slug="conc-b", nombre="Clínica Concurrente")
    duplicado = PatientCreate(
        nombre="Ana",
        apellido="Perez",
        telefono="11 1111-0000",
        dni="30111222",
        confirmar_duplicado=True,
    )

    resultados = _en_paralelo(factory, tenant_id, [duplicado, duplicado])

    exitos = [r for r in resultados if r.paciente is not None]
    fallos = [r for r in resultados if r.code is not None]
    assert len(exitos) == 1, resultados
    assert len(fallos) == 1, resultados
    assert fallos[0].code == PatientErrorCode.patient_dni_duplicado.value

    # El alta fallida no reservó número: la siguiente toma el inmediato posterior.
    siguiente = _alta(
        factory,
        tenant_id,
        PatientCreate(nombre="Carla", apellido="Costa", telefono="11 1111-0003"),
    )
    assert siguiente.paciente is not None, siguiente
    assert (
        siguiente.paciente["numero_historia_clinica"]
        == f"{int(exitos[0].paciente['numero_historia_clinica']) + 1:06d}"
    )
    assert _counter(seeder, tenant_id) == 2
    assert len(_numeros(seeder, tenant_id)) == 2


def test_s5_5_la_carrera_chequeo_insert_se_traduce_en_409(
    factory: sessionmaker[Session], seeder: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ambas sesiones pasan el chequeo explícito y chocan en el índice único."""
    tenant_id = seeder.tenant(slug="conc-c", nombre="Clínica Concurrente")
    original: Callable[[Session, str], dict[str, Any] | None] = service._existente_por_dni
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    llamadas = 0

    def chequeo_ciego(db: Session, dni: str) -> dict[str, Any] | None:
        nonlocal llamadas
        with lock:
            llamadas += 1
            es_racer = llamadas <= 2
        if es_racer:
            barrier.wait(timeout=15)
            return None
        return original(db, dni)

    monkeypatch.setattr(service, "_existente_por_dni", chequeo_ciego)

    payload = PatientCreate(
        nombre="Ana",
        apellido="Perez",
        telefono="11 1111-0000",
        dni="30111222",
        confirmar_duplicado=True,
    )
    resultados = _en_paralelo(factory, tenant_id, [payload, payload])

    exitos = [r for r in resultados if r.paciente is not None]
    fallos = [r for r in resultados if r.code is not None]
    assert len(exitos) == 1, resultados
    assert len(fallos) == 1, resultados
    # Nunca un 500: el ``IntegrityError`` se traduce a 409 de dominio.
    assert fallos[0].code == PatientErrorCode.patient_dni_duplicado.value
    assert _numeros(seeder, tenant_id) == ["000001"]
    assert _counter(seeder, tenant_id) == 1


def test_la_misma_sesion_no_puede_dejar_el_contador_adelantado(
    factory: sessionmaker[Session], seeder: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un alta que falla después de reservar revierte el contador con la transacción."""
    tenant_id = seeder.tenant(slug="conc-d", nombre="Clínica Concurrente")
    original = service.siguiente_numero_historia_clinica

    def falla_despues_de_reservar(session: Session, tenant: UUID) -> str:
        original(session, tenant)
        raise RuntimeError("falla simulada después de reservar")

    monkeypatch.setattr(service, "siguiente_numero_historia_clinica", falla_despues_de_reservar)

    db = factory()
    try:
        set_tenant_context(db.connection(), tenant_id)
        with pytest.raises(RuntimeError):
            service.create_patient(
                db,
                tenant_id=tenant_id,
                payload=PatientCreate(nombre="Ana", apellido="Perez", telefono="11 1111-0000"),
            )
    finally:
        db.rollback()
        db.close()

    # El contador quedó en cero: la reserva se revirtió con la transacción.
    assert _counter(seeder, tenant_id) in (None, 0)

    monkeypatch.undo()
    siguiente = _alta(
        factory,
        tenant_id,
        PatientCreate(nombre="Beto", apellido="Benitez", telefono="11 1111-0001"),
    )
    assert siguiente.paciente is not None, siguiente
    assert siguiente.paciente["numero_historia_clinica"] == "000001"
