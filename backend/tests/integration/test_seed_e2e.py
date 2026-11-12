"""Idempotencia del seed de e2e (task 11.1).

El seed corre una vez por arranque del servidor de Playwright, pero los tests
cambian roles y el segundo arranque debe dejar **exactamente** la misma matriz:
mismos ids, mismas memberships, sin duplicados. Si esto se rompe, el e2e falla
por estado heredado y no por la aplicación.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from app.core.crypto import decrypt_secret
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

TESTS_ROOT = Path(__file__).resolve().parents[1]
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from fixtures import seed_auth_e2e as seed_e2e  # noqa: E402  (path del seed)


def _snapshot(engine: Engine, tenant_ids: tuple[Any, Any]) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT m.tenant_id, u.email, m.rol::text AS rol, m.activo
                FROM membership m JOIN "user" u ON u.id = m.user_id
                WHERE m.tenant_id IN (:a, :b)
                ORDER BY u.email, m.rol
                """
            ),
            {"a": tenant_ids[0], "b": tenant_ids[1]},
        ).all()
        return [tuple(row) for row in rows]


def _clinic_snapshot(engine: Engine, tenant_id: Any) -> list[tuple[Any, ...]]:
    """Configuración clínica del tenant (C-05): sillones + profesionales, estable."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT 'chair' AS kind, c.nombre, c.tipo::text AS detalle,
                       c.activo, NULL::text AS extra
                FROM chair c WHERE c.tenant_id = :tenant_id
                UNION ALL
                SELECT 'professional', p.matricula, s.nombre, p.activo, p.color_agenda
                FROM professional p
                JOIN specialty s ON s.id = p.especialidad_id
                WHERE p.tenant_id = :tenant_id
                ORDER BY kind, nombre
                """
            ),
            {"tenant_id": tenant_id},
        ).all()
        return [tuple(row) for row in rows]


def _patient_snapshot(engine: Engine, tenant_id: Any) -> list[tuple[Any, ...]]:
    """Pacientes del tenant (C-06): datos estables + HCE, ordenados por apellido."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT apellido, nombre, dni, numero_historia_clinica,
                       telefono_norm, activo, (deleted_at IS NULL) AS vigente
                FROM patient
                WHERE tenant_id = :tenant_id
                ORDER BY apellido_norm, nombre_norm
                """
            ),
            {"tenant_id": tenant_id},
        ).all()
        return [tuple(row) for row in rows]


def _patient_counter(engine: Engine, tenant_id: Any) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT ultimo_numero FROM patient_counter WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar_one()


def _mfa_secret(engine: Engine, user_id: Any) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            text('SELECT mfa_secret FROM "user" WHERE id = :id'), {"id": user_id}
        ).scalar_one()


def _cleanup(engine: Engine) -> None:
    """Borra lo sembrado para no dejar usuarios globales que choquen con otros tests.

    ``"user"`` es global (el email es único en toda la base) y el ``Seeder`` de
    integración inserta con ``email`` explícito: si este test dejara
    ``profe@example.test`` vivo, el test de cambio de rol fallaría con
    ``uq_user_email``. ``membership`` cae por ``ON DELETE CASCADE``.
    """
    with engine.begin() as connection:
        connection.execute(
            text('DELETE FROM "user" WHERE email = ANY(:emails)'),
            {
                "emails": [user.email for user in seed_e2e.FLOW_USERS]
                + [seed_e2e.OTHER_TENANT_USER.email]
            },
        )
        connection.execute(
            text("DELETE FROM tenant WHERE slug = ANY(:slugs)"),
            {"slugs": [seed_e2e.TENANT_SLUG, seed_e2e.OTHER_TENANT_SLUG]},
        )


def test_el_seed_e2e_es_idempotente(migrated_database: str) -> None:
    engine = create_engine(migrated_database, future=True)
    try:
        first = seed_e2e.seed(engine)
        after_first = _snapshot(engine, (first.tenant_id, first.other_tenant_id))
        clinic_first = _clinic_snapshot(engine, first.tenant_id)
        patients_first = _patient_snapshot(engine, first.tenant_id)
        counter_first = _patient_counter(engine, first.tenant_id)
        second = seed_e2e.seed(engine)
        after_second = _snapshot(engine, (second.tenant_id, second.other_tenant_id))
        clinic_second = _clinic_snapshot(engine, second.tenant_id)
        patients_second = _patient_snapshot(engine, second.tenant_id)
        counter_second = _patient_counter(engine, second.tenant_id)

        assert first.tenant_id == second.tenant_id
        assert first.other_tenant_id == second.other_tenant_id
        assert first.users == second.users
        assert after_first == after_second
        assert clinic_first == clinic_second
        assert first.chair_id == second.chair_id
        assert first.professional_id == second.professional_id
        assert patients_first == patients_second
        assert first.patient_id == second.patient_id
        assert first.patient_hce == second.patient_hce
        # El contador no se resetea ni se incrementa al re-sembrar: la HCE no se recicla.
        assert counter_first == counter_second
        assert first.patient_hce is not None
        assert len(first.patient_hce) == 6
        assert patients_first[0][3] == first.patient_hce

        # 5 usuarios del flujo en clínica A y 1 ajeno en B, sin duplicados.
        assert len(after_first) == len(seed_e2e.FLOW_USERS) + 1
        roles_a = {
            (email, rol)
            for tenant_id, email, rol, activo in after_first
            if tenant_id == first.tenant_id and activo
        }
        assert roles_a == {
            (seed_e2e.USER_EMAIL, "professional"),
            (seed_e2e.OWNER_EMAIL, "owner"),
            (seed_e2e.CLINICAL_ADMIN_EMAIL, "clinical_admin"),
            (seed_e2e.FRONT_DESK_EMAIL, "front_desk"),
            (seed_e2e.PROFESSIONAL_EMAIL, "professional"),
        }
        roles_b = {
            (email, rol)
            for tenant_id, email, rol, activo in after_first
            if tenant_id == first.other_tenant_id
        }
        assert roles_b == {(seed_e2e.OTHER_TENANT_EMAIL, "professional")}

        # C-05: un sillón y un profesional canónicos, ligados al usuario del flujo.
        assert clinic_first == [
            ("chair", seed_e2e.SEED_CHAIR_NAME, "consultorio", True, None),
            (
                "professional",
                seed_e2e.SEED_PROFESSIONAL_MATRICULA,
                seed_e2e.SEED_SPECIALTY_NAME,
                True,
                "#2563EB",
            ),
        ]
        # Los usuarios se crean antes que el profesional: el vínculo es real.
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT user_id FROM professional WHERE id = :id"),
                    {"id": second.professional_id},
                ).scalar_one()
                == second.users[seed_e2e.PROFESSIONAL_EMAIL]
            )

        # C-06: un único paciente canónico, con DNI reservado y HCE de 6 dígitos.
        assert patients_first == [
            (
                seed_e2e.SEED_PATIENT_APELLIDO,
                seed_e2e.SEED_PATIENT_NOMBRE,
                seed_e2e.SEED_PATIENT_DNI,
                second.patient_hce,
                "1155550199",
                True,
                True,
            )
        ]

        # Solo el owner tiene el segundo factor pre-enrolado, con el secreto fijo
        # cifrado en reposo y descifrable con la clave ficticia del e2e.
        owner_secret = _mfa_secret(engine, second.users[seed_e2e.OWNER_EMAIL])
        assert owner_secret is not None
        assert (
            decrypt_secret(
                owner_secret,
                seed_e2e.DEFAULT_MFA_ENCRYPTION_KEY,
                key_version=1,
            )
            == seed_e2e.OWNER_TOTP_SECRET
        )
        for email in (
            seed_e2e.USER_EMAIL,
            seed_e2e.CLINICAL_ADMIN_EMAIL,
            seed_e2e.FRONT_DESK_EMAIL,
            seed_e2e.PROFESSIONAL_EMAIL,
            seed_e2e.OTHER_TENANT_EMAIL,
        ):
            assert _mfa_secret(engine, second.users[email]) is None
    finally:
        _cleanup(engine)
        engine.dispose()


def test_el_seed_borra_las_filas_que_dejo_el_e2e(migrated_database: str) -> None:
    """El spec crea un sillón y un profesional por corrida: el seed los limpia."""
    engine = create_engine(migrated_database, future=True)
    try:
        seeded = seed_e2e.seed(engine)
        with engine.begin() as connection:
            specialty_id = connection.execute(
                text(
                    """
                    SELECT id FROM specialty
                    WHERE nombre = :nombre AND tenant_id IS NULL
                    """
                ),
                {"nombre": seed_e2e.SEED_SPECIALTY_NAME},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO chair (tenant_id, nombre, tipo, activo)
                    VALUES (:tenant_id, :nombre, 'otro', true)
                    """
                ),
                {"tenant_id": seeded.tenant_id, "nombre": f"{seed_e2e.E2E_PREFIX}Sillón"},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO professional
                        (tenant_id, nombre, apellido, matricula, especialidad_id,
                         duracion_default_min, porcentaje_liquidacion, activo)
                    VALUES
                        (:tenant_id, 'Eva', 'E2E', :matricula, :especialidad_id,
                         30, 10, true)
                    """
                ),
                {
                    "tenant_id": seeded.tenant_id,
                    "matricula": f"{seed_e2e.E2E_PREFIX}MP-1",
                    "especialidad_id": specialty_id,
                },
            )

        assert len(_clinic_snapshot(engine, seeded.tenant_id)) == 4
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO patient
                        (tenant_id, apellido, nombre, apellido_norm, nombre_norm,
                         telefono, telefono_norm, numero_historia_clinica, activo)
                    VALUES
                        (:tenant_id, 'E2E-Residual', 'Paciente', 'e2e-residual',
                         'paciente', '11 5555-9999', '1155559999', '099999', true)
                    """
                ),
                {"tenant_id": seeded.tenant_id},
            )
        assert len(_patient_snapshot(engine, seeded.tenant_id)) == 2

        again = seed_e2e.seed(engine)

        assert _clinic_snapshot(engine, again.tenant_id) == [
            ("chair", seed_e2e.SEED_CHAIR_NAME, "consultorio", True, None),
            (
                "professional",
                seed_e2e.SEED_PROFESSIONAL_MATRICULA,
                seed_e2e.SEED_SPECIALTY_NAME,
                True,
                "#2563EB",
            ),
        ]
        # El paciente residual se borra; el canónico y su número siguen igual.
        assert _patient_snapshot(engine, again.tenant_id) == [
            (
                seed_e2e.SEED_PATIENT_APELLIDO,
                seed_e2e.SEED_PATIENT_NOMBRE,
                seed_e2e.SEED_PATIENT_DNI,
                seeded.patient_hce,
                "1155550199",
                True,
                True,
            )
        ]
        assert _patient_counter(engine, again.tenant_id) == 1
    finally:
        _cleanup(engine)
        engine.dispose()
