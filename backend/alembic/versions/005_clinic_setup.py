"""Configuración operativa de la clínica: sillones, profesionales y disponibilidad.

Orden deliberado, igual que 002/004: tipo → tablas → índices → FK diferida de
``membership`` → grants → RLS. ``specialty`` no tiene RLS (es catálogo con filas
globales); por eso la visibilidad se valida en el servicio, no acá.

``availability_rule`` usa ``UNIQUE NULLS NOT DISTINCT`` (PG 16) para que dos
reglas idénticas de alcance "toda la clínica" (`professional_id`/`chair_id`
nulos) no se dupliquen. El solape *parcial* de horarios es regla de negocio y lo
valida ``app.domain.clinic.service`` (design D6).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005_clinic_setup"
down_revision = "004_rbac"
branch_labels = None
depends_on = None

APP_ROLE = "odontologia_app"

TENANT_PREDICATE = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"

CLINIC_TABLES = ("chair", "professional", "availability_rule")


def upgrade() -> None:
    op.execute("CREATE TYPE chair_tipo AS ENUM ('consultorio', 'rx', 'cirugia', 'higiene', 'otro')")

    op.create_table(
        "chair",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column(
            "tipo",
            postgresql.ENUM(
                "consultorio",
                "rx",
                "cirugia",
                "higiene",
                "otro",
                name="chair_tipo",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ubicacion", sa.String(120), nullable=True),
        sa.Column(
            "equipamiento",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chair"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_chair_tenant", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tenant_id", "nombre", name="uq_chair_tenant_nombre"),
    )
    op.create_index("ix_chair_tenant_id", "chair", ["tenant_id"])

    op.create_table(
        "professional",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("apellido", sa.String(80), nullable=False),
        sa.Column("matricula", sa.String(32), nullable=False),
        sa.Column("especialidad_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "porcentaje_liquidacion", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "duracion_default_min", sa.Integer(), nullable=False, server_default=sa.text("30")
        ),
        sa.Column(
            "color_agenda", sa.String(7), nullable=False, server_default=sa.text("'#2563EB'")
        ),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_professional"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_professional_tenant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name="fk_professional_user", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["especialidad_id"], ["specialty.id"], name="fk_professional_especialidad"
        ),
        sa.UniqueConstraint("tenant_id", "matricula", name="uq_professional_tenant_matricula"),
        sa.CheckConstraint(
            "duracion_default_min BETWEEN 5 AND 480",
            name="ck_professional_duracion_default_min",
        ),
        sa.CheckConstraint(
            "porcentaje_liquidacion BETWEEN 0 AND 100",
            name="ck_professional_porcentaje_liquidacion",
        ),
    )
    op.create_index("ix_professional_tenant_id", "professional", ["tenant_id"])
    op.create_index("ix_professional_especialidad_id", "professional", ["especialidad_id"])

    op.create_table(
        "availability_rule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chair_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dia_semana", sa.SmallInteger(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fin", sa.Time(), nullable=False),
        sa.Column("slot_min", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("buffer_previo_min", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "buffer_posterior_min", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("fecha_desde", sa.Date(), nullable=False),
        sa.Column("fecha_hasta", sa.Date(), nullable=True),
        sa.Column("tipo_practica", sa.String(40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_availability_rule"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_availability_rule_tenant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["professional_id"],
            ["professional.id"],
            name="fk_availability_rule_professional",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chair_id"], ["chair.id"], name="fk_availability_rule_chair", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "professional_id",
            "chair_id",
            "dia_semana",
            "fecha_desde",
            name="uq_availability_rule_scope",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint("dia_semana BETWEEN 0 AND 6", name="ck_availability_rule_dia_semana"),
        sa.CheckConstraint("hora_fin > hora_inicio", name="ck_availability_rule_ventana"),
        sa.CheckConstraint("slot_min > 0", name="ck_availability_rule_slot_min"),
        sa.CheckConstraint("buffer_previo_min >= 0", name="ck_availability_rule_buffer_previo"),
        sa.CheckConstraint(
            "buffer_posterior_min >= 0", name="ck_availability_rule_buffer_posterior"
        ),
        sa.CheckConstraint(
            "fecha_hasta IS NULL OR fecha_hasta >= fecha_desde",
            name="ck_availability_rule_fechas",
        ),
    )
    op.create_index("ix_availability_rule_tenant_id", "availability_rule", ["tenant_id"])
    op.create_index(
        "ix_availability_rule_professional_id", "availability_rule", ["professional_id"]
    )

    # El vínculo rol ↔ profesional ya existía como columna; la FK llega ahora que
    # la tabla existe. Sigue nullable (el flujo "mi agenda" la completa).
    op.execute(
        """
        ALTER TABLE membership
          ADD CONSTRAINT fk_membership_professional
          FOREIGN KEY (professional_id) REFERENCES professional(id) ON DELETE SET NULL
        """
    )

    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(CLINIC_TABLES)} TO {APP_ROLE}"
    )

    for table in CLINIC_TABLES:
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
    op.execute("ALTER TABLE membership DROP CONSTRAINT fk_membership_professional")
    op.drop_table("availability_rule")
    op.drop_table("professional")
    op.drop_table("chair")
    op.execute("DROP TYPE chair_tipo")
