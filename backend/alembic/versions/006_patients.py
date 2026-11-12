"""Ficha demográfica del paciente y contador de historia clínica (C-06).

Orden deliberado, igual que 002/005: extensión → tipo → tablas → índices → grants
→ RLS. ``pg_trgm`` se crea acá porque solo esta migración lo consume; en el
``downgrade`` **no** se elimina (extensión compartida, igual que ``citext`` en
``002_core_tenancy``): dropearla podría romper objetos de otras bases o cambios
futuros.

``patient_counter`` es una tabla de negocio (tiene ``tenant_id``), así que lleva
RLS ``FORCE``, política y grants como ``patient``. No lleva ``DELETE``: el
contador solo avanza (RN-CLI-01).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006_patients"
down_revision = "005_clinic_setup"
branch_labels = None
depends_on = None

APP_ROLE = "odontologia_app"

TENANT_PREDICATE = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE TYPE sexo_paciente AS ENUM ('femenino', 'masculino', 'otro', 'no_declara')"
    )

    op.create_table(
        "patient_counter",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ultimo_numero", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("tenant_id", name="pk_patient_counter"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_patient_counter_tenant", ondelete="CASCADE"
        ),
    )

    op.create_table(
        "patient",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dni", sa.String(11), nullable=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("apellido", sa.String(80), nullable=False),
        sa.Column("apellido_norm", sa.String(80), nullable=False),
        sa.Column("nombre_norm", sa.String(80), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column(
            "sexo",
            postgresql.ENUM(
                "femenino",
                "masculino",
                "otro",
                "no_declara",
                name="sexo_paciente",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("telefono", sa.String(32), nullable=False),
        sa.Column("telefono_norm", sa.String(32), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("domicilio", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("obra_social_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("numero_historia_clinica", sa.String(20), nullable=False),
        # Columnas clínicas persistidas, no expuestas en C-06 (PQ-17, C-09).
        sa.Column("alergias", sa.Text(), nullable=True),
        sa.Column(
            "alerta_clinica", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_patient"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_patient_tenant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name="fk_patient_user", ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "numero_historia_clinica",
            name="uq_patient_tenant_numero_historia_clinica",
        ),
    )

    op.create_index("ix_patient_tenant_id", "patient", ["tenant_id"])
    # El DNI nunca se recicla: el índice no filtra por `deleted_at` (S5.6).
    op.create_index(
        "uq_patient_dni",
        "patient",
        ["tenant_id", "dni"],
        unique=True,
        postgresql_where=sa.text("dni IS NOT NULL"),
    )
    op.create_index("ix_patient_nombre", "patient", ["tenant_id", "apellido_norm", "nombre_norm"])
    op.create_index("ix_patient_telefono", "patient", ["tenant_id", "telefono_norm"])
    op.create_index(
        "ix_patient_nombre_trgm",
        "patient",
        ["apellido_norm", "nombre_norm"],
        postgresql_using="gin",
        postgresql_ops={
            "apellido_norm": "gin_trgm_ops",
            "nombre_norm": "gin_trgm_ops",
        },
    )
    op.create_index(
        "ix_patient_activos",
        "patient",
        ["tenant_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patient TO odontologia_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON patient_counter TO odontologia_app")

    for table in ("patient", "patient_counter"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            FOR ALL
            USING (tenant_id = {TENANT_PREDICATE})
            WITH CHECK (tenant_id = {TENANT_PREDICATE})
            """
        )


def downgrade() -> None:
    op.drop_table("patient")
    op.drop_table("patient_counter")
    op.execute("DROP TYPE sexo_paciente")
