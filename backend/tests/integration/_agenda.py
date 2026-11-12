"""Helpers compartidos de los tests HTTP/integración de la agenda.

No es un módulo de tests (no empieza con ``test_``): lo importan
``test_appointments_http.py``, ``test_appointments_overlap.py`` y el gate
cross-tenant. Evita que cada archivo redefina el payload y la siembra, y mantiene
un único shape de autenticación (``create_access_token`` + cookie) para todos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.config import Settings
from app.core.security import ACCESS_COOKIE, create_access_token
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

APPOINTMENTS_URL = "/api/v1/appointments"

APPOINTMENT_KEYS = {
    "id",
    "professional_id",
    "chair_id",
    "patient_id",
    "inicio",
    "fin",
    "duracion_min",
    "buffer_previo_min",
    "buffer_posterior_min",
    "estado",
    "origen",
    "tipo_practica",
}

# Lunes 16/11/2026 09:00 en Buenos Aires (UTC-3): dentro de la ventana 09-12 y
# del ``dia_semana = 0`` que usan las reglas sembradas por los tests.
INICIO_LOCAL = "2026-11-16T09:00:00-03:00"
INICIO_UTC = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def authenticate(
    client: TestClient,
    settings: Settings,
    seeder: Any,
    tenant_id: UUID,
    user_id: UUID,
) -> None:
    """Cookie de access con una sesión real sembrada (no se prueba el login acá)."""
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


def member(seeder: Any, tenant_id: UUID, rol: str = "front_desk") -> UUID:
    """Usuario con membership activa en el tenant y rol con ``appointment.create``."""
    user_id = seeder.user(
        email=f"{rol}-{uuid4().hex[:8]}@example.test", nombre=rol, apellido="Prueba"
    )
    seeder.membership(tenant_id, user_id, rol)
    return user_id


def agenda(
    seeder: Any,
    *,
    prefix: str = "agenda",
    duracion_default_min: int = 30,
    professional_activo: bool = True,
    chair_activo: bool = True,
    con_paciente: bool = True,
) -> dict[str, Any]:
    """Tenant con sillón, profesional, (paciente) y un recepcionista autenticable."""
    tenant_id = seeder.tenant(slug=f"{prefix}-{uuid4().hex[:8]}", nombre="Clínica Agenda")
    data: dict[str, Any] = {
        "tenant_id": tenant_id,
        "chair_id": seeder.chair(tenant_id, nombre="Sillón A", activo=chair_activo),
        "professional_id": seeder.professional(
            tenant_id,
            duracion_default_min=duracion_default_min,
            activo=professional_activo,
        ),
        "patient_id": seeder.patient(tenant_id, dni=None) if con_paciente else None,
        "user_id": member(seeder, tenant_id),
    }
    return data


def payload(data: dict[str, Any], **overrides: object) -> dict[str, object]:
    """Payload válido mínimo; los overrides permiten romper un campo por test."""
    body: dict[str, object] = {
        "professional_id": str(data["professional_id"]),
        "chair_id": str(data["chair_id"]),
        "inicio": INICIO_LOCAL,
    }
    if data.get("patient_id") is not None:
        body["patient_id"] = str(data["patient_id"])
    body.update(overrides)
    return body


def rows(db_engine: Engine, tenant_id: UUID) -> list[dict[str, Any]]:
    """Filas de la agenda del tenant, leídas como superusuario (setup/aserción)."""
    with db_engine.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM appointment WHERE tenant_id = :tenant_id ORDER BY inicio, id"),
                {"tenant_id": tenant_id},
            ).mappings()
        ]
