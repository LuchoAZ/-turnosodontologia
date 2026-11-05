"""Core models, tenancy and catalogs (C-02).

Orden deliberado: extensión ``citext`` → tipos enum → tablas → índices y
constraints → rol de aplicación + grants → seed → RLS + políticas.

Sembrar **antes** de habilitar RLS evita necesitar ``BYPASSRLS`` para los 80
conceptos globales. El rol ``odontologia_app`` es ``NOLOGIN NOSUPERUSER
NOBYPASSRLS``: un superusuario ignora RLS incluso con ``FORCE``, así que los
tests hacen ``SET ROLE odontologia_app`` antes de consultar.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002_core_tenancy"
down_revision = "c01_baseline"
branch_labels = None
depends_on = None

ROLES: tuple[str, ...] = (
    "owner",
    "clinical_admin",
    "professional",
    "assistant",
    "front_desk",
    "billing",
    "patient",
    "external_lab",
    "accountant",
)

TENANT_ESTADOS: tuple[str, ...] = ("trial", "active", "suspended", "closed")

SPECIALTIES: tuple[tuple[str, int], ...] = (
    ("Odontología general", 30),
    ("Endodoncia", 60),
    ("Periodoncia", 45),
    ("Ortodoncia", 30),
    ("Cirugía oral", 60),
    ("Prótesis", 45),
    ("Odontopediatría", 30),
    ("Higiene", 30),
    ("Rehabilitación oral", 60),
)

CURRENCIES: tuple[tuple[str, str, str, int], ...] = (
    ("ARS", "Peso argentino", "$", 2),
    ("USD", "Dólar estadounidense", "US$", 2),
)

# 80 conceptos de referencia (precios ficticios en ARS, RN-EX-05).
PRICE_CONCEPTS: tuple[tuple[str, str, str], ...] = (
    ("CONSULTA", "Consulta odontológica general", "8000"),
    ("CONSULTA_URGENCIA", "Consulta de urgencia", "12000"),
    ("CONSULTA_SEGUIMIENTO", "Consulta de seguimiento", "6000"),
    ("LIMPIEZA", "Limpieza dental (destartraje)", "18000"),
    ("LIMPIEZA_PROF", "Limpieza profunda por cuadrante", "22000"),
    ("PROFILAXIS", "Profilaxis dental", "14000"),
    ("FLUOR", "Aplicación de flúor", "9000"),
    ("SELLADOR", "Sellador de fosas y fisuras", "11000"),
    ("EXTRACCION_SIMPLE", "Extracción simple", "25000"),
    ("EXTRACCION_COMPLEJA", "Extracción compleja", "40000"),
    ("EXTRACCION_TERCER_MOLAR", "Extracción de tercer molar", "65000"),
    ("EXTRACCION_RAIZ_RESIDUAL", "Extracción de raíz residual", "30000"),
    ("ENDO_UNIRRADICULAR", "Endodoncia unirradicular", "55000"),
    ("ENDO_BIRRADICULAR", "Endodoncia birradicular", "70000"),
    ("ENDO_MULTIRRADICULAR", "Endodoncia multirradicular", "85000"),
    ("ENDO_RETRATAMIENTO", "Retratamiento endodóntico", "95000"),
    ("ENDO_URGENCIA", "Apertura y medicación endodóntica", "28000"),
    ("OBTURACION_AMALGAMA", "Obturación con amalgama", "20000"),
    ("OBTURACION_COMPOSITE", "Obturación con composite", "26000"),
    ("OBTURACION_TEMPORARIA", "Obturación temporaria", "12000"),
    ("RECONSTRUCCION_CORONAL", "Reconstrucción coronal", "35000"),
    ("RECONSTRUCCION_PERNO", "Reconstrucción con perno de fibra", "48000"),
    ("CORONA_METAL", "Corona metal", "90000"),
    ("CORONA_METAL_CERAMICA", "Corona metal-cerámica", "120000"),
    ("CORONA_ZIRCONIA", "Corona de zirconia", "160000"),
    ("CORONA_TEMPORARIA", "Corona provisional", "30000"),
    ("INCRUSTACION_CERAMICA", "Incrustación cerámica", "110000"),
    ("CARILLA_CERAMICA", "Carilla cerámica", "140000"),
    ("PROTESIS_PARCIAL_REM", "Prótesis parcial removible", "180000"),
    ("PROTESIS_TOTAL_SUP", "Prótesis total superior", "220000"),
    ("PROTESIS_TOTAL_INF", "Prótesis total inferior", "220000"),
    ("REPARACION_PROTESIS", "Reparación de prótesis", "35000"),
    ("REBASADO_PROTESIS", "Rebasado de prótesis", "30000"),
    ("ORTODONCIA_CONSULTA", "Consulta de ortodoncia", "15000"),
    ("ORTODONCIA_ESTUDIO", "Estudio ortodóntico", "45000"),
    ("ORTODONCIA_METAL", "Ortodoncia brackets metálicos", "350000"),
    ("ORTODONCIA_ESTETICA", "Ortodoncia brackets estéticos", "450000"),
    ("ORTODONCIA_CONTROL", "Control mensual de ortodoncia", "25000"),
    ("ORTODONCIA_RETENEDOR", "Colocación de retenedor", "40000"),
    ("ALINEADORES", "Tratamiento con alineadores", "650000"),
    ("PERIO_DESTARTRAJE", "Destartraje y alisado radicular", "24000"),
    ("PERIO_CURETAJE", "Curetraje por cuadrante", "32000"),
    ("PERIO_CIRUGIA", "Cirugía periodontal por cuadrante", "85000"),
    ("PERIO_INJERTO", "Injerto gingival", "95000"),
    ("PERIO_FRENECTOMIA", "Frenectomía", "45000"),
    ("IMPLANTE_UNITARIO", "Implante unitario", "380000"),
    ("IMPLANTE_CORONA", "Corona sobre implante", "180000"),
    ("IMPLANTE_ELEVACION_SENO", "Elevación de seno maxilar", "250000"),
    ("IMPLANTE_INJERTO_OSE", "Injerto óseo", "150000"),
    ("IMPLANTE_BARRA", "Barra para prótesis implantoasistida", "320000"),
    ("ODONTOPEDIATRIA_CONSULTA", "Consulta odontopediátrica", "9000"),
    ("ODONTOPEDIATRIA_PULPECTOMIA", "Pulpectomía pediátrica", "38000"),
    ("ODONTOPEDIATRIA_CORONA", "Corona pediátrica", "42000"),
    ("ODONTOPEDIATRIA_APEXIFICACION", "Apexificación", "50000"),
    ("ODONTOPEDIATRIA_CONTROL", "Control odontopediátrico", "8000"),
    ("CIRUGIA_BIOPSIA", "Biopsia de tejido oral", "55000"),
    ("CIRUGIA_QUISTE", "Enucleación de quiste", "120000"),
    ("CIRUGIA_APICECTOMIA", "Apicectomía", "90000"),
    ("CIRUGIA_FRENILLO", "Resección de frenillo lingual", "48000"),
    ("CIRUGIA_ALVEOLOPLASTIA", "Alveoloplastia", "70000"),
    ("RAYOS_X_PERICAPICAL", "Radiografía periapical", "6000"),
    ("RAYOS_X_PANORAMICA", "Radiografía panorámica", "18000"),
    ("RAYOS_X_ALETEO", "Radiografía de aleta", "6000"),
    ("TOMOGRAFIA_CBCT", "Tomografía CBCT", "65000"),
    ("FOTOGRAFIA_CLINICA", "Fotografía clínica", "5000"),
    ("ESTUDIO_MODELOS", "Estudio de modelos", "22000"),
    ("BLANQUEAMIENTO_CONSULTORIO", "Blanqueamiento en consultorio", "85000"),
    ("BLANQUEAMIENTO_DOMICILIO", "Blanqueamiento domiciliario", "55000"),
    ("CARIOLOGIA_ICDAS", "Evaluación cariológica ICDAS", "10000"),
    ("DETARTRAJE_SUBGINGIVAL", "Detartraje subgingival", "26000"),
    ("TRATAMIENTO_BRUXISMO", "Placa de bruxismo", "65000"),
    ("PLACA_MIORREL", "Placa miorrelajante", "70000"),
    ("FERULIZACION", "Ferulización", "40000"),
    ("RESTAURACION_PROVISIONAL", "Restauración provisional", "15000"),
    ("AJUSTE_OCLUSAL", "Ajuste oclusal", "18000"),
    ("TRATAMIENTO_CARIES_TEMPRANA", "Tratamiento de caries temprana", "12000"),
    ("ANESTESIA_LOCAL", "Anestesia local", "5000"),
    ("SEDACION_CONSCIENTE", "Sedación consciente", "45000"),
    ("URGENCIA_DOLOR", "Atención de dolor agudo", "15000"),
    ("CERTIFICADO_MEDICO", "Certificado odontológico", "8000"),
)

APP_ROLE = "odontologia_app"

# ``current_setting(..., true)`` devuelve NULL si nunca se seteó y '' si la
# transacción anterior usó set_config(..., true). El NULLIF evita que el cast
# ''::uuid explote en vez de ser fail-closed.
TENANT_PREDICATE = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def _uuid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"odontologia/{kind}/{key}")


def _enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    role_enum = _enum("role", ROLES)
    tenant_estado_enum = _enum("tenant_estado", TENANT_ESTADOS)
    role_enum.create(op.get_bind(), checkfirst=True)
    tenant_estado_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "tenant",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", postgresql.CITEXT(), nullable=False),
        sa.Column("nombre_comercial", sa.String(160), nullable=False),
        sa.Column("cuit", sa.String(11), nullable=False),
        sa.Column(
            "timezone",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'America/Argentina/Buenos_Aires'"),
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("estado", tenant_estado_enum, nullable=False, server_default=sa.text("'trial'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant"),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
        sa.UniqueConstraint("cuit", name="uq_tenant_cuit"),
    )
    op.create_index("ix_tenant_estado", "tenant", ["estado"])

    op.create_table(
        "user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("telefono", sa.String(32), nullable=True),
        sa.Column("dni", sa.String(11), nullable=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("apellido", sa.String(80), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_secret", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user"),
    )
    op.create_index(
        "uq_user_email",
        "user",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index("ix_user_telefono", "user", ["telefono"])
    op.create_index("ix_user_dni", "user", ["dni"])

    op.create_table(
        "membership",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rol", role_enum, nullable=False),
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id", name="pk_membership"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_membership_tenant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name="fk_membership_user", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "rol", name="uq_membership_tenant_user_rol"
        ),
    )
    op.create_index("ix_membership_tenant_id", "membership", ["tenant_id"])
    op.create_index("ix_membership_user_id", "membership", ["user_id"])
    # RN-TEN-04: a lo sumo un owner activo por tenant. La invariante "cero owners"
    # la garantiza la transacción de transferencia de ownership (C-04).
    op.create_index(
        "uq_membership_owner_activo",
        "membership",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("rol = 'owner' AND activo"),
    )

    op.create_table(
        "specialty",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("duracion_default_min", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_specialty"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_specialty_tenant", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "uq_specialty_global_nombre",
        "specialty",
        ["nombre"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )

    op.create_table(
        "price_concept",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("codigo", sa.String(32), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("precio_default", sa.Numeric(14, 4), nullable=False),
        sa.Column("alicuota_impuesto", sa.Numeric(6, 3), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id", name="pk_price_concept"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_price_concept_tenant", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "codigo",
            name="uq_price_concept_tenant_codigo",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_price_concept_tenant_id", "price_concept", ["tenant_id"])

    op.create_table(
        "currency",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("codigo", sa.String(3), nullable=False),
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("simbolo", sa.String(5), nullable=False),
        sa.Column("decimales", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_currency"),
        sa.UniqueConstraint("codigo", name="uq_currency_codigo"),
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
    )

    _seed()

    op.execute("ALTER TABLE membership ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE membership FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY membership_tenant_isolation ON membership
        FOR ALL
        USING (tenant_id = {TENANT_PREDICATE})
        WITH CHECK (tenant_id = {TENANT_PREDICATE})
        """
    )

    op.execute("ALTER TABLE price_concept ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE price_concept FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY price_concept_read ON price_concept
        FOR SELECT
        USING (tenant_id IS NULL OR tenant_id = {TENANT_PREDICATE})
        """
    )
    op.execute(
        f"""
        CREATE POLICY price_concept_write ON price_concept
        FOR ALL
        USING (tenant_id = {TENANT_PREDICATE})
        WITH CHECK (tenant_id = {TENANT_PREDICATE})
        """
    )


def _seed() -> None:
    currency_table = sa.table(
        "currency",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("codigo", sa.String),
        sa.column("nombre", sa.String),
        sa.column("simbolo", sa.String),
        sa.column("decimales", sa.Integer),
    )
    op.bulk_insert(
        currency_table,
        [
            {
                "id": _uuid("currency", codigo),
                "codigo": codigo,
                "nombre": nombre,
                "simbolo": simbolo,
                "decimales": decimales,
            }
            for codigo, nombre, simbolo, decimales in CURRENCIES
        ],
    )

    specialty_table = sa.table(
        "specialty",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("nombre", sa.String),
        sa.column("duracion_default_min", sa.Integer),
    )
    op.bulk_insert(
        specialty_table,
        [
            {
                "id": _uuid("specialty", nombre),
                "tenant_id": None,
                "nombre": nombre,
                "duracion_default_min": duracion,
            }
            for nombre, duracion in SPECIALTIES
        ],
    )

    price_table = sa.table(
        "price_concept",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("codigo", sa.String),
        sa.column("descripcion", sa.String),
        sa.column("precio_default", sa.Numeric),
        sa.column("alicuota_impuesto", sa.Numeric),
        sa.column("activo", sa.Boolean),
    )
    op.bulk_insert(
        price_table,
        [
            {
                "id": _uuid("price_concept", codigo),
                "tenant_id": None,
                "codigo": codigo,
                "descripcion": descripcion,
                "precio_default": Decimal(precio),
                "alicuota_impuesto": Decimal("21.000"),
                "activo": True,
            }
            for codigo, descripcion, precio in PRICE_CONCEPTS
        ],
    )


def downgrade() -> None:
    op.drop_table("price_concept")
    op.drop_table("specialty")
    op.drop_table("membership")
    op.drop_table("currency")
    op.drop_table("user")
    op.drop_table("tenant")

    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")

    _enum("role", ROLES).drop(op.get_bind(), checkfirst=True)
    _enum("tenant_estado", TENANT_ESTADOS).drop(op.get_bind(), checkfirst=True)
