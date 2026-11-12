"""Agenda: tabla ``appointment`` con la garantía dura de no doble booking.

Change ``agendar-turno-sin-solapamiento`` (D2). Orden deliberado, igual que
002/005/006: extensión → tipos → tabla → índices → constraints de integridad →
grants → RLS.

El anti-solapamiento es un ``EXCLUDE USING gist`` **por recurso** sobre el rango
bloqueado ``[inicio - buffer_previo_min, fin + buffer_posterior_min)``, con
``WHERE estado NOT IN ('cancelado', 'no_asistio')`` para que un turno liberado no
bloquee el horario (RN-AG-02/03). Se expresa sobre ``tsrange`` de marcas UTC
(``tsrange((inicio AT TIME ZONE 'UTC') - interval, ...)``) y no sobre
``tstzrange``: ``timestamptz - interval`` es ``STABLE`` porque depende del
``TimeZone`` de la sesión y Postgres rechaza funciones no inmutables en un índice
(*"functions in index expression must be marked IMMUTABLE"*). ``AT TIME ZONE
'UTC'`` es inmutable, compara exactamente los mismos instantes y conserva el
rango semiabierto: ``inicio == fin`` de un turno contiguo no es solape.

``btree_gist`` se crea acá porque solo esta migración lo consume; en el
``downgrade`` **no** se elimina (extensión compartida, igual que ``pg_trgm`` en
006): dropearla podría romper objetos de otras bases o cambios futuros.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_agenda"
down_revision = "006_patients"
branch_labels = None
depends_on = None

APP_ROLE = "odontologia_app"

TENANT_PREDICATE = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"

# Rango bloqueado por el turno: incluye los buffers de higiene/esterilización.
# Semánticamente es el mismo instante que ``[inicio - buffer_previo, fin +
# buffer_posterior)`` en timestamptz, pero inmutable para el planner.
RANGO_BLOQUEADO = (
    "tsrange("
    "(inicio AT TIME ZONE 'UTC') - make_interval(mins => buffer_previo_min), "
    "(fin AT TIME ZONE 'UTC') + make_interval(mins => buffer_posterior_min)"
    ")"
)


def upgrade() -> None:

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "CREATE TYPE appointment_estado AS ENUM "
        "('pendiente', 'confirmado', 'en_curso', 'atendido', 'cancelado', "
        "'no_asistio', 'reprogramado')"
    )
    op.execute(
        "CREATE TYPE appointment_origen AS ENUM "
        "('recepcion', 'portal', 'whatsapp', 'api', 'importacion')"
    )

    op.create_table(
        "appointment",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duracion_min", sa.Integer(), nullable=False),
        sa.Column(
            "buffer_previo_min", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "buffer_posterior_min", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "estado",
            postgresql.ENUM(
                "pendiente",
                "confirmado",
                "en_curso",
                "atendido",
                "cancelado",
                "no_asistio",
                "reprogramado",
                name="appointment_estado",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'pendiente'"),
        ),
        sa.Column("tipo_practica", sa.String(40), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column(
            "origen",
            postgresql.ENUM(
                "recepcion",
                "portal",
                "whatsapp",
                "api",
                "importacion",
                name="appointment_origen",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'recepcion'"),
        ),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recordatorio_24h_enviado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recordatorio_2h_enviado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelado_motivo", sa.String(200), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointment"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_appointment_tenant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patient.id"], name="fk_appointment_patient", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["professional_id"],
            ["professional.id"],
            name="fk_appointment_professional",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chair_id"], ["chair.id"], name="fk_appointment_chair", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["creado_por"], ["user.id"], name="fk_appointment_creado_por", ondelete="SET NULL"
        ),
    )

    op.create_index("ix_appointment_tenant_inicio", "appointment", ["tenant_id", "inicio"])
    op.create_index("ix_appointment_patient_inicio", "appointment", ["patient_id", "inicio"])
    op.create_index(
        "ix_appointment_estado_activos",
        "appointment",
        ["tenant_id", "estado"],
        postgresql_where=sa.text("estado NOT IN ('cancelado', 'no_asistio')"),
    )

    op.execute(
        "ALTER TABLE appointment ADD CONSTRAINT ck_appointment_fin_posterior_a_inicio "
        "CHECK (fin > inicio)"
    )

    # La garantía dura (RN-AG-02): ni el pre-chequeo ni la aplicación pueden
    # saltearla; dos transacciones concurrentes no pueden insertar el mismo rango.
    for resource in ("professional", "chair"):
        op.execute(
            f"""
            ALTER TABLE appointment
            ADD CONSTRAINT ex_appointment_{resource}_no_overlap
            EXCLUDE USING gist (
                tenant_id WITH =,
                {resource}_id WITH =,
                {RANGO_BLOQUEADO} WITH &&
            )
            WHERE (estado NOT IN ('cancelado', 'no_asistio'))
            """
        )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON appointment TO odontologia_app")

    op.execute("ALTER TABLE appointment ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointment FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY appointment_tenant_isolation ON appointment
        FOR ALL
        USING (tenant_id = {TENANT_PREDICATE})
        WITH CHECK (tenant_id = {TENANT_PREDICATE})
        """
    )


def downgrade() -> None:
    op.drop_table("appointment")
    op.execute("DROP TYPE appointment_origen")
    op.execute("DROP TYPE appointment_estado")
