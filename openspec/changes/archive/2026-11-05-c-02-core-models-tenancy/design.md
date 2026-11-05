# Design — c-02-core-models-tenancy

## Context

C-01 (archivado) dejó el sustrato: FastAPI, SQLAlchemy 2.0 async, Alembic con baseline vacía,
Testcontainers con Postgres 16 + Redis 7, CI y configuración tipada. No existe ninguna tabla de
negocio. Este change es la base de datos del sistema: identidad, tenants y catálogos, con el
aislamiento por fila resuelto desde el primer día.

Restricciones dominantes: governance **CRÍTICO** (tenancy/seguridad), RN-TEN-02 como gate de
merge, Postgres real en tests (sin mocks de DB), `mypy --strict` sin `Any` en dominio, vertical
slices (acá la "rebanada" es modelo + migración + aislamiento + seed, sin endpoint todavía) y el
contrato de datos en SQLAlchemy 2.0 tipado.

Documentación del stack consultada con **Context7 MCP** (ver `docs/skills-mcp/investigacion.md`):
sinopsis de `CREATE POLICY` / `ENABLE ROW LEVEL SECURITY`, `set_config` vs `SET LOCAL` en
SQLAlchemy y `EXCLUDE USING gist` (este último se usa en C-06, queda documentado).

## Goals / Non-Goals

**Goals**
- 6 tablas tipadas: `tenant`, `user`, `membership`, `specialty`, `price_concept`, `currency`.
- Enum `role` con los 9 roles de la KB y `membership` como vínculo usuario↔tenant↔rol.
- RLS fail-closed en `membership` y `price_concept`, con rol de aplicación sin `BYPASSRLS`.
- Contexto de tenant parameterizado y transaction-local (`set_config(..., true)`).
- `TenantGuard` puro: tenant del token, nunca del body (RN-TEN-03).
- CUIT módulo 11 (RN-TEN-01) como función pura.
- Migración `002_core_tenancy` reversible + seed de catálogos.
- Suite de aislamiento cross-tenant con prueba de mutación (gate RN-TEN-02).

**Non-Goals**
- Auth/tokens (C-03), endpoints CRUD, UI, `professional`/`chair`/`patient`/`appointment`.

## Decisions

### D1 — Modelos declarativos tipados, un módulo por dominio

`app/models/base.py` (Base + mixin de timestamps), `app/models/tenancy.py` (`Tenant`, `User`,
`Membership`, `Role`) y `app/models/catalog.py` (`Specialty`, `PriceConcept`, `Currency`).
PK UUID con `server_default=text("gen_random_uuid()")` (nativo en PG 13+; no requiere extensión).
`alembic/env.py` pasa a usar `Base.metadata` como `target_metadata`.

- Alternativas: modelos por capa (viola DD-03) o dicts/SQL crudo (sin tipos ni migraciones).
- Por qué: el dominio se tipa una vez y los changes posteriores solo agregan módulos.

### D2 — RLS con `FORCE` y política única basada en `current_setting`

```sql
ALTER TABLE membership ENABLE ROW LEVEL SECURITY;
ALTER TABLE membership FORCE ROW LEVEL SECURITY;
CREATE POLICY membership_tenant_isolation ON membership
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
```

`price_concept` separa lectura y escritura porque el catálogo global es compartido:

```sql
CREATE POLICY price_concept_read ON price_concept FOR SELECT
  USING (tenant_id IS NULL
         OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
CREATE POLICY price_concept_write ON price_concept FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
```

Detalles que hacen la diferencia (verificados con la documentación de PostgreSQL):
- `current_setting('app.current_tenant', true)` devuelve **NULL** si nunca se seteó y **cadena
  vacía** si la transacción anterior usó `set_config(..., true)` y commiteó. Sin `NULLIF(...)`,
  el cast `''::uuid` lanzaría `invalid input syntax for type uuid` en vez de ser fail-closed.
- `FORCE ROW LEVEL SECURITY` hace que el **owner** también quede sujeto a las políticas.
- Un **superusuario** o un rol con `BYPASSRLS` ignora RLS incluso con `FORCE`; por eso la
  migración crea el rol `odontologia_app` (`NOLOGIN NOSUPERUSER NOBYPASSRLS`) con grants, y los
  tests hacen `SET ROLE odontologia_app` antes de consultar. Sin eso, el test daría verde falso.
- `tenant` queda sin RLS a propósito: el login (C-03) resuelve el tenant por `slug` **antes** de
  tener contexto. Su acceso lo controla la aplicación + `membership`.

- Alternativas: `SET LOCAL app.current_tenant = '...'` (no admite parámetros bindeados: obliga a
  interpolar el UUID en el SQL), o filtrar solo en la aplicación (un `WHERE` olvidado = leak).
- Por qué: la base es la garantía final; el test de mutación demuestra que el verde depende de
  la política y no de un filtro accidental.

### D3 — Contexto de tenant parameterizado

`app/db/tenant_context.py`:

```python
TENANT_SETTING_SQL = text("SELECT set_config('app.current_tenant', :tenant_id, true)")

def set_tenant_context(connection: Connection, tenant_id: UUID) -> None:
    connection.execute(TENANT_SETTING_SQL, {"tenant_id": str(tenant_id)})
```

Valida el UUID antes de ejecutar (un `UUID` ya lo garantiza en tipos; la función pública acepta
`UUID | str` y normaliza). El tercer argumento `true` = transaction-local: al commit/rollback la
conexión vuelve al pool sin contexto. Para el engine async se usa la misma sentencia con
`await session.execute(TENANT_SETTING_SQL, {...})` dentro de `session.begin()`.

- Alternativa descartada: interpolar `SET LOCAL app.current_tenant = '{uuid}'` (inyección y
  problemas de quoting). Context7 documenta que `SET` no acepta parámetros bindeados.
- Alternativa descartada: `SET` de sesión (no local): el valor sobrevive al commit y se filtra a
  la siguiente request que reutilice la conexión.

### D4 — `TenantGuard` como función pura + dependencia FastAPI

`app/core/tenant_guard.py`:

```python
class TenantClaimError(Exception): ...

def tenant_id_from_claims(claims: Mapping[str, object]) -> UUID:
    raw = claims.get("tenant_id")
    if raw is None:
        raise TenantClaimError("missing tenant claim")
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError) as exc:
        raise TenantClaimError("invalid tenant claim") from exc
```

La firma **no recibe** body/query/header, así que por construcción no puede leerlos (RN-TEN-03).
En C-03 se conecta como `Depends(require_tenant)` leyendo `request.state.claims`; acá se testea la
función pura y el contrato de error. El borde HTTP traducirá `TenantClaimError` a `401`.

- Alternativa descartada: `tenant_id` como parámetro opcional con fallback al body (rompe RN-TEN-03).

### D5 — Seed en la migración, antes de habilitar RLS

Orden de la migración: `CREATE TABLE` → `CREATE ROLE` + grants → **seed** → `ENABLE/FORCE RLS` +
políticas. Sembrar antes de activar RLS evita necesitar `BYPASSRLS` para los 80 conceptos
globales. Los precios son ficticios y de referencia (RN-EX-05): `tenant_id IS NULL` +
`precio_default` en ARS; el tenant debe crear su override para cobrar.

`price_concept` usa `UNIQUE NULLS NOT DISTINCT (tenant_id, codigo)` (PG 15+): sin eso, dos filas
globales con el mismo código convivirían porque `NULL != NULL` en un unique común.

### D6 — Enum nativo `role`

`sa.Enum(*ROLES, name="role")` con los 9 valores de la KB. Se prefiere enum nativo a varchar +
CHECK porque el dominio es cerrado y la KB lo define como enum; agregar un rol requiere migración
explícita (deseable: un rol nuevo es una decisión de dominio, no un string libre).

### D7 — CUIT como función pura de dominio

`app/domain/tenancy/cuit.py`: normaliza (quita guiones/espacios), exige 11 dígitos, aplica pesos
`[5,4,3,2,7,6,5,4,3,2]`, `check = 11 - (sum % 11)` con `11→0` y `10→9`. Devuelve el CUIT
normalizado o lanza `CuitError` con el motivo (`formato` | `digito_verificador`). No se agrega
CHECK en SQL: el algoritmo no es expresable de forma legible en un constraint y el punto de
escritura será el dominio/schema (C-03).

### D8 — Tests de integración con Postgres real y dos tenants

Cada suite siembra tenant A y tenant B. Los tests de RLS usan `SET ROLE odontologia_app` para que
las políticas apliquen. El test de aislamiento incluye **prueba de mutación**: se elimina
temporalmente la política (o se corre como owner sin `SET ROLE`) y se verifica que el test falla;
luego se restaura. Esto demuestra que el verde no es accidental (RN-TEN-02).

## Project Standards (auto-resolved)

- **tdd**: RED antes de cada implementación; los tests leen como contrato público; prohibido
  recomputar el valor con la misma función bajo test (CUIT se testea con valores calculados a mano).
- **supabase-postgres-best-practices**: RLS testeada con Postgres real; `SET ROLE` para rol de
  app; índices en `tenant_id`; `NULLS NOT DISTINCT` en el unique con NULL; migraciones reversibles.
- **SQLAlchemy 2.0**: `Mapped`/`mapped_column`, `select()` 2.0, `session.begin()`, sin `Any`.
- **FastAPI**: el guard se conectará como dependencia en C-03; el contrato de error es `401`.

## Risks / Trade-offs

- **[Superusuario en tests]** Si un test corre como superusuario, RLS no aplica y el verde es
  falso. → Mitigación: `SET ROLE odontologia_app` obligatorio en la suite de RLS + prueba de
  mutación.
- **[GUC vacío tras commit]** `current_setting` devuelve `''` y el cast a uuid fallaría. →
  Mitigación: `NULLIF(..., '')` en todas las políticas + test de reutilización de conexión.
- **[Enum nativo rígido]** Agregar roles requiere `ALTER TYPE`. → Trade-off aceptado: el dominio
  es cerrado; el cambio queda versionado en una migración.
- **[`tenant` sin RLS]** Un query olvidado podría listar tenants. → Mitigación: la tabla no tiene
  datos clínicos; el acceso se controla en la app y el `tenant_id` de negocio sale de `membership`.
- **[80 conceptos ficticios]** El nomenclador real es dominio del cliente. → Trade-off: son datos
  de referencia marcados como tales; RN-EX-05 impide cobrarlos sin override.

## Migration Plan

1. `002_core_tenancy` (upgrade): extensiones/tipos → tablas → índices/constraints → rol de app y
   grants → seed → RLS + políticas.
2. Downgrade: drop policies → drop tablas (en orden de FK) → drop tipo enum → drop rol.
3. Rollback de código: `git revert` del commit del change (no hay datos productivos).

## Open Questions

- **Roles de base en producción**: el change crea `odontologia_app`; el nombre/password reales se
  resuelven en el deploy (C-01 no tiene entorno productivo). No cambia spec ni tasks.
- **`membership.professional_id`**: FK a `professional` se agrega en C-05; acá queda la columna
  UUID nullable sin FK, documentada como deuda explícita.
