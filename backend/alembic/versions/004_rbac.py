"""Auditoría de RBAC: ``membership_event`` append-only (C-04, design D5).

Orden deliberado: tipo → tabla → índice → función y trigger → grants → RLS.
No se toca ``membership`` ni ``user``: la unicidad de owner ya está garantizada
por ``uq_membership_owner_activo`` (002) y la transferencia usa las columnas
existentes (D7). Lo único nuevo es la auditoría (RN-CMP-03).

La tabla es append-only **de verdad**: el rol de app solo tiene ``INSERT`` y el
trigger rechaza ``UPDATE``/``DELETE`` directos con SQLSTATE ``55000`` incluso
para el superusuario. Las acciones referenciales (``ON DELETE SET NULL`` de
``user`` y ``ON DELETE CASCADE`` de ``tenant``) se distinguen por
``pg_trigger_depth() > 1``, la misma receta que ``auth_event`` en 003.
"""

from __future__ import annotations

from alembic import op

revision = "004_rbac"
down_revision = "003_auth"
branch_labels = None
depends_on = None

APP_ROLE = "odontologia_app"

TENANT_PREDICATE = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE membership_event_tipo AS ENUM (
            'member_created', 'member_reactivated', 'member_role_changed',
            'member_deactivated', 'ownership_transferred'
        )
        """
    )

    op.execute(
        """
        CREATE TABLE membership_event (
          id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
          actor_user_id  uuid NULL REFERENCES "user"(id) ON DELETE SET NULL,
          target_user_id uuid NULL REFERENCES "user"(id) ON DELETE SET NULL,
          tipo           membership_event_tipo NOT NULL,
          detail         jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX membership_event_tenant_created_idx
          ON membership_event (tenant_id, created_at)
        """
    )

    op.execute(
        """
        CREATE FUNCTION membership_event_forbid_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          -- ``pg_trigger_depth() > 1`` es el UPDATE/DELETE interno que dispara una
          -- acción referencial (``ON DELETE SET NULL`` de user, ``ON DELETE
          -- CASCADE`` de tenant). Ningún rol de aplicación puede anidar triggers:
          -- sobre esta tabla solo tiene INSERT.
          IF pg_trigger_depth() > 1 THEN
            IF TG_OP = 'DELETE' THEN
              RETURN OLD;
            END IF;
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'membership_event is append-only' USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION membership_event_forbid_mutation() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER membership_event_append_only
          BEFORE UPDATE OR DELETE ON membership_event
          FOR EACH ROW EXECUTE FUNCTION membership_event_forbid_mutation()
        """
    )

    op.execute(f"GRANT INSERT ON membership_event TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON SEQUENCE membership_event_id_seq TO {APP_ROLE}")

    op.execute("ALTER TABLE membership_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE membership_event FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY membership_event_tenant_insert ON membership_event
        FOR ALL
        USING (tenant_id = {TENANT_PREDICATE})
        WITH CHECK (tenant_id = {TENANT_PREDICATE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS membership_event_tenant_insert ON membership_event")
    op.execute("DROP TRIGGER IF EXISTS membership_event_append_only ON membership_event")
    op.execute("DROP FUNCTION IF EXISTS membership_event_forbid_mutation()")
    op.execute("DROP TABLE IF EXISTS membership_event")
    op.execute("DROP TYPE IF EXISTS membership_event_tipo")
