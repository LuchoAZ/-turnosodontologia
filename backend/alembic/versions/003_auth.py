"""Autenticación de plataforma: sesiones, refresh rotativo y MFA (C-03).

Orden deliberado: tipos → columnas de ``user`` → tablas → índices y checks →
rol ``auth_resolver`` y funciones ``SECURITY DEFINER`` → grants → trigger
append-only → RLS + políticas.

``session`` y ``refresh_token`` llevan ``tenant_id NOT NULL`` y RLS ``FORCE``;
el endpoint de refresh las lee **antes** de conocer el tenant mediante las dos
funciones acotadas que pertenecen a ``auth_resolver`` (``BYPASSRLS``,
``NOLOGIN``). El bypass queda confinado a esas funciones: la app no puede hacer
un ``SELECT`` directo sin contexto (devuelve 0 filas).
"""

from __future__ import annotations

from alembic import op

revision = "003_auth"
down_revision = "002_core_tenancy"
branch_labels = None
depends_on = None

APP_ROLE = "odontologia_app"
RESOLVER_ROLE = "auth_resolver"

TENANT_PREDICATE = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"

NEW_USER_COLUMNS: tuple[str, ...] = (
    "failed_login_count",
    "lockout_strikes",
    "locked_until",
    "last_lockout_at",
    "mfa_enrolled_at",
    "mfa_secret_key_version",
    "credentials_version",
    "last_totp_step",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE refresh_estado AS ENUM ('activo', 'rotado', 'revocado')
        """
    )
    op.execute(
        """
        CREATE TYPE auth_event_tipo AS ENUM (
            'login_success', 'login_fail', 'lockout', 'logout',
            'refresh_rotated', 'refresh_reuse',
            'mfa_success', 'mfa_fail', 'mfa_enroll', 'mfa_step_up_issued',
            'password_reset_request', 'password_reset', 'switch_tenant'
        )
        """
    )

    op.execute(
        """
        ALTER TABLE "user"
          ADD COLUMN failed_login_count smallint NOT NULL DEFAULT 0
            CONSTRAINT ck_user_failed_login_count
            CHECK (failed_login_count BETWEEN 0 AND 5),
          ADD COLUMN lockout_strikes smallint NOT NULL DEFAULT 0
            CONSTRAINT ck_user_lockout_strikes CHECK (lockout_strikes >= 0),
          ADD COLUMN locked_until timestamptz NULL,
          ADD COLUMN last_lockout_at timestamptz NULL,
          ADD COLUMN mfa_enrolled_at timestamptz NULL,
          ADD COLUMN mfa_secret_key_version smallint NULL,
          ADD COLUMN credentials_version integer NOT NULL DEFAULT 0
            CONSTRAINT ck_user_credentials_version CHECK (credentials_version >= 0),
          ADD COLUMN last_totp_step bigint NULL
        """
    )

    op.execute(
        """
        CREATE TABLE session (
          id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id             uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
          tenant_id           uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
          credentials_version integer NOT NULL,
          mfa_satisfied       boolean NOT NULL DEFAULT false,
          last_used_step      bigint NULL,
          expires_at          timestamptz NOT NULL,
          revoked_at          timestamptz NULL,
          created_at          timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_session_expires_at CHECK (expires_at > created_at)
        )
        """
    )
    op.execute("CREATE INDEX session_tenant_user_idx ON session (tenant_id, user_id)")
    op.execute("CREATE INDEX session_expires_at_idx ON session (expires_at)")

    op.execute(
        """
        CREATE TABLE refresh_token (
          id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          session_id  uuid NOT NULL REFERENCES session(id) ON DELETE CASCADE,
          tenant_id   uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
          family_id   uuid NOT NULL,
          token_hash  text NOT NULL UNIQUE,
          estado      refresh_estado NOT NULL DEFAULT 'activo',
          expires_at  timestamptz NOT NULL,
          used_at     timestamptz NULL,
          replaced_by uuid NULL REFERENCES refresh_token(id) ON DELETE SET NULL,
          created_at  timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_refresh_token_not_self_replaced
            CHECK (replaced_by IS NULL OR replaced_by <> id),
          CONSTRAINT ck_refresh_token_rotated_fields
            CHECK (estado <> 'rotado' OR (used_at IS NOT NULL AND replaced_by IS NOT NULL))
        )
        """
    )
    op.execute("CREATE INDEX refresh_token_family_idx ON refresh_token (family_id)")
    op.execute(
        "CREATE INDEX refresh_token_tenant_session_idx ON refresh_token (tenant_id, session_id)"
    )
    op.execute("CREATE INDEX refresh_token_expires_at_idx ON refresh_token (expires_at)")

    op.execute(
        """
        CREATE TABLE auth_event (
          id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          tipo       auth_event_tipo NOT NULL,
          user_id    uuid NULL REFERENCES "user"(id) ON DELETE SET NULL,
          tenant_id  uuid NULL REFERENCES tenant(id) ON DELETE SET NULL,
          detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX auth_event_tenant_created_idx ON auth_event (tenant_id, created_at)")
    op.execute("CREATE INDEX auth_event_user_created_idx ON auth_event (user_id, created_at)")

    op.execute(
        """
        CREATE TABLE password_reset_token (
          id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id    uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
          token_hash text NOT NULL UNIQUE,
          expires_at timestamptz NOT NULL,
          used_at    timestamptz NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX password_reset_token_user_idx ON password_reset_token (user_id)"
    )
    op.execute(
        "CREATE INDEX password_reset_token_expires_at_idx ON password_reset_token (expires_at)"
    )

    op.execute(
        """
        CREATE FUNCTION auth_event_forbid_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          -- ``pg_trigger_depth() > 1`` es el UPDATE interno que dispara una
          -- acción referencial (``ON DELETE SET NULL`` de user/tenant). Ningún
          -- rol de aplicación puede anidar triggers sobre auth_event: el rol
          -- de app solo tiene INSERT, así que no hay vía externa para esto.
          IF pg_trigger_depth() > 1 THEN
            IF TG_OP = 'DELETE' THEN
              RETURN OLD;
            END IF;
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'auth_event is append-only' USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION auth_event_forbid_mutation() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER auth_event_append_only
          BEFORE UPDATE OR DELETE ON auth_event
          FOR EACH ROW EXECUTE FUNCTION auth_event_forbid_mutation()
        """
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RESOLVER_ROLE}') THEN
                CREATE ROLE {RESOLVER_ROLE}
                    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {RESOLVER_ROLE}")
    op.execute(
        f"""
        GRANT SELECT (id, tenant_id, user_id, expires_at, revoked_at, credentials_version)
          ON session TO {RESOLVER_ROLE}
        """
    )
    op.execute(
        f"GRANT SELECT (session_id, tenant_id, token_hash) ON refresh_token TO {RESOLVER_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION auth_resolve_session_by_sid(p_sid uuid)
        RETURNS TABLE (
          session_id uuid, tenant_id uuid, user_id uuid,
          expires_at timestamptz, revoked_at timestamptz, credentials_version integer
        )
        LANGUAGE sql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
          SELECT s.id, s.tenant_id, s.user_id, s.expires_at, s.revoked_at,
                 s.credentials_version
          FROM public.session s
          WHERE s.id = p_sid;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION auth_resolve_session_by_refresh(p_token_hash text)
        RETURNS TABLE (
          session_id uuid, tenant_id uuid, user_id uuid,
          expires_at timestamptz, revoked_at timestamptz, credentials_version integer
        )
        LANGUAGE sql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
          SELECT s.id, s.tenant_id, s.user_id, s.expires_at, s.revoked_at,
                 s.credentials_version
          FROM public.refresh_token rt
          JOIN public.session s ON s.id = rt.session_id
          WHERE rt.token_hash = p_token_hash;
        $$
        """
    )
    op.execute(
        f"ALTER FUNCTION auth_resolve_session_by_sid(uuid) OWNER TO {RESOLVER_ROLE}"
    )
    op.execute(
        f"ALTER FUNCTION auth_resolve_session_by_refresh(text) OWNER TO {RESOLVER_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION auth_resolve_session_by_sid(uuid) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION auth_resolve_session_by_refresh(text) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION auth_resolve_session_by_sid(uuid) TO {APP_ROLE}"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION auth_resolve_session_by_refresh(text) TO {APP_ROLE}"
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON session, refresh_token TO {APP_ROLE}")
    op.execute(f"GRANT INSERT ON auth_event TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON SEQUENCE auth_event_id_seq TO {APP_ROLE}")

    op.execute(
        f"""
        GRANT SELECT (id, user_id, token_hash, expires_at, used_at)
          ON password_reset_token TO {APP_ROLE}
        """
    )
    op.execute(
        f"""
        GRANT INSERT (id, user_id, token_hash, expires_at, used_at, created_at)
          ON password_reset_token TO {APP_ROLE}
        """
    )
    op.execute(f"GRANT UPDATE (used_at) ON password_reset_token TO {APP_ROLE}")

    op.execute("ALTER TABLE session ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE session FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY session_tenant_isolation ON session
        FOR ALL
        USING (tenant_id = {TENANT_PREDICATE})
        WITH CHECK (tenant_id = {TENANT_PREDICATE})
        """
    )

    op.execute("ALTER TABLE refresh_token ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE refresh_token FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY refresh_token_tenant_isolation ON refresh_token
        FOR ALL
        USING (tenant_id = {TENANT_PREDICATE})
        WITH CHECK (tenant_id = {TENANT_PREDICATE})
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS auth_event_append_only ON auth_event")
    op.execute("DROP FUNCTION IF EXISTS auth_event_forbid_mutation()")
    op.execute("DROP FUNCTION IF EXISTS auth_resolve_session_by_sid(uuid)")
    op.execute("DROP FUNCTION IF EXISTS auth_resolve_session_by_refresh(text)")
    op.execute(f"DROP OWNED BY {RESOLVER_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {RESOLVER_ROLE}")

    op.execute("DROP TABLE IF EXISTS password_reset_token")
    op.execute("DROP TABLE IF EXISTS auth_event")
    op.execute("DROP TABLE IF EXISTS refresh_token")
    op.execute("DROP TABLE IF EXISTS session")

    for column in NEW_USER_COLUMNS:
        op.execute(f'ALTER TABLE "user" DROP COLUMN IF EXISTS {column}')

    op.execute("DROP TYPE IF EXISTS auth_event_tipo")
    op.execute("DROP TYPE IF EXISTS refresh_estado")
