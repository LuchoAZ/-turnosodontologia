# Core models y tenancy — modelo base, RLS y catálogos

Este documento describe lo que entrega el change `c-02-core-models-tenancy`: las seis tablas
base del sistema, el aislamiento multi-tenant por Row Level Security, el rol de aplicación y
el seed de catálogos. Es la base de datos sobre la que se apoyan C-03 (auth), C-05 (clínica),
C-06 (pacientes) y el entregable `agendar-turno-sin-solapamiento`.

> Regla que manda: **RN-TEN-02**. Toda tabla de negocio tiene `tenant_id NOT NULL` y RLS
> activa; un endpoint que toque una tabla con `tenant_id` sin test cross-tenant no se mergea.
> `cross-tenant leak = 0` es gate de merge, no una métrica aspiracional.

---

## 1. Modelo

| Tabla | `tenant_id` | RLS | Rol en el dominio |
|-------|-------------|-----|-------------------|
| `tenant` | — | No | La clínica (PyME). El login la resuelve por `slug` **antes** de tener contexto. |
| `user` | — (global) | No | Persona. El mismo humano puede operar en varias clínicas. |
| `membership` | `NOT NULL` | **Sí, forzada** | Vínculo usuario ↔ tenant ↔ rol. Es la fuente del tenant activo. |
| `specialty` | nullable (`NULL` = global) | No | Catálogo de especialidades y duración por defecto. |
| `price_concept` | nullable (`NULL` = global) | **Sí, forzada** | Nomenclador: base global + override por tenant. |
| `currency` | — | No | Monedas (`ARS`, `USD`). |

Decisiones de esquema relevantes:

- **PK UUID** con `server_default = gen_random_uuid()` (nativo en PostgreSQL 13+).
- `tenant.slug` y `tenant.cuit` son `UNIQUE`; `tenant.cuit` se valida con módulo 11 en el
  dominio (`app/domain/tenancy/cuit.py`, RN-TEN-01).
- `membership` tiene `UNIQUE (tenant_id, user_id, rol)` y un índice único **parcial**
  `uq_membership_owner_activo` sobre `tenant_id WHERE rol = 'owner' AND activo` (RN-TEN-04:
  a lo sumo un owner activo por tenant). La invariante complementaria —cero owners— la
  garantiza la transacción atómica de transferencia de ownership (C-04), no un constraint.
  `membership.professional_id` queda como UUID nullable **sin FK** hasta C-05 (deuda
  explícita del design).
- `price_concept` usa `UNIQUE NULLS NOT DISTINCT (tenant_id, codigo)`: sin `NULLS NOT
  DISTINCT`, dos conceptos globales con el mismo código convivirían porque `NULL != NULL`.
- `specialty` tiene un índice único parcial `UNIQUE (nombre) WHERE tenant_id IS NULL` para el
  catálogo base.

Los modelos viven en `backend/app/models/` (`base.py`, `tenancy.py`, `catalog.py`) y son
SQLAlchemy 2.0 tipado (`Mapped`/`mapped_column`, sin `Any`). `alembic/env.py` usa
`Base.metadata` como `target_metadata`, así que `alembic revision --autogenerate` ya detecta
cambios.

---

## 2. Row Level Security (fail-closed)

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
CREATE POLICY price_concept_read ON price_concept
  FOR SELECT
  USING (tenant_id IS NULL
         OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

CREATE POLICY price_concept_write ON price_concept
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
```

Detalles que hacen la diferencia:

- **`FORCE ROW LEVEL SECURITY`** sujeta también al *owner* de la tabla a las políticas.
- **`NULLIF(..., '')`** es obligatorio: `current_setting('app.current_tenant', true)` devuelve
  `NULL` si nunca se seteó, pero devuelve la **cadena vacía** si la transacción anterior usó
  `set_config(..., true)` y commiteó. Sin el `NULLIF`, `''::uuid` lanza
  `invalid input syntax for type uuid` en vez de ser fail-closed.
- **Un superusuario ignora RLS** aunque la política exista y esté forzada. Por eso la
  migración crea el rol `odontologia_app` y los tests hacen `SET ROLE odontologia_app` antes
  de consultar. Sin eso, el verde sería falso.
- `tenant` no tiene RLS a propósito: el login resuelve el tenant por `slug` antes de que
  exista contexto. Su acceso lo controla la aplicación + `membership`.
- Sin contexto de tenant, una consulta a una tabla con RLS devuelve **0 filas** (no falla y
  no filtra datos).

### Rol de aplicación

```sql
CREATE ROLE odontologia_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO odontologia_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO odontologia_app;
```

El rol es `NOLOGIN`: la aplicación se conecta con su propio usuario y, en el deploy, se le
otorga membresía en `odontologia_app` (o se usa directamente ese rol). Lo que importa para
RLS es que **no sea superusuario ni tenga `BYPASSRLS`**.

---

## 3. Contexto de tenant por transacción

`backend/app/db/tenant_context.py`:

```python
TENANT_SETTING_SQL = text("SELECT set_config('app.current_tenant', :tenant_id, true)")

def set_tenant_context(connection: Connection, tenant_id: UUID | str) -> None:
    valor = _normalizar_tenant_id(tenant_id)
    connection.execute(TENANT_SETTING_SQL, {"tenant_id": valor})
```

- El UUID se pasa **bindeado**, nunca interpolado en el SQL.
- El tercer argumento `true` es transaction-local: al commit o rollback la conexión vuelve al
  pool sin contexto. `SET LOCAL app.current_tenant = '...'` no admite parámetros bindeados y
  obligaría a interpolar el valor (la corrección vino de la documentación de SQLAlchemy
  consultada con Context7; ver `docs/skills-mcp/investigacion.md`).
- Un identificador inválido se rechaza **antes** de tocar la base.

Uso típico (C-03 lo conectará a la dependencia FastAPI):

```python
async with session.begin():
    await set_tenant_context(session, tenant_id)  # o connection.execute(TENANT_SETTING_SQL, ...)
    ...
```

---

## 4. TenantGuard: el tenant sale del token

`backend/app/core/tenant_guard.py` expone una función pura:

```python
def tenant_id_from_claims(claims: Mapping[str, object]) -> UUID: ...
```

La firma **no recibe** body, query ni headers: por construcción no puede leer un `tenant_id`
enviado por el cliente (RN-TEN-03). Si falta el claim, no es UUID o la sesión no tiene
membership activa, lanza `TenantClaimError`, que el borde HTTP de C-03 traduce a `401`.

---

## 5. Seed de catálogos

La migración siembra, **antes** de habilitar RLS (así no hace falta `BYPASSRLS`):

| Tabla | Contenido |
|-------|-----------|
| `currency` | `ARS` (`$`, 2 decimales) y `USD` (`US$`, 2 decimales) |
| `specialty` | 9 especialidades de la KB con `duracion_default_min` |
| `price_concept` | 80 conceptos globales de referencia (`tenant_id IS NULL`), precios ficticios en ARS |
| enum `role` | Los 9 roles de `03_actores_y_roles.md` |

Los precios son **de referencia** (RN-EX-05): un tenant no puede cobrar un concepto global sin
crear su propio override. La política `price_concept_write` impide que un tenant escriba en el
catálogo global (SQLSTATE `42501`).

Los UUID del seed son determinísticos (`uuid5` sobre `odontologia/<tabla>/<clave>`), así el
mismo catálogo se reproduce en cualquier entorno.

---

## 6. Gate RN-TEN-02 y prueba de mutación

`backend/tests/integration/test_core_tenancy_migration.py` cubre:

- migración: 6 tablas, enum de 9 roles, `NOT NULL` (`23502`), FK (`23503`), unicidad del
  código global y coexistencia global + override;
- RN-TEN-04: un segundo `owner` activo → `23505`; un `owner` inactivo no bloquea al nuevo
  owner activo (el índice parcial solo cubre filas activas);
- seed: 2 monedas, 9 especialidades, 80 conceptos globales;
- RLS: un tenant solo ve sus filas; sin contexto → 0 filas; `UPDATE`/`DELETE` cross-tenant
  afectan 0 filas; escritura cross-tenant → `42501`; el tenant no escribe el catálogo global;
  el catálogo global es visible para todos y el override solo para su tenant;
- contexto: no se filtra entre transacciones del pool (`set_config(..., true)`);
- **prueba de mutación** (`test_mutacion_sin_rls_el_mismo_query_filtraria`): el mismo `SELECT`
  como owner/superusuario ve filas de A **y** de B; con `SET ROLE odontologia_app` ve solo A.
  Esto demuestra que el verde depende de la política y no de un `WHERE` accidental.

`backend/tests/integration/test_migration_reversibility.py` verifica el ciclo
`upgrade head → downgrade base → upgrade head` en un contenedor propio (el `DROP ROLE` de la
migración es un objeto de clúster y fallaría si otra base del mismo contenedor tuviera grants).

### Comandos

```powershell
cd backend

# Calidad (los mismos comandos del CI)
uv run ruff check .
uv run mypy app
uv run pytest                     # unit + integración (Docker requerido)

# Solo el gate de tenancy
uv run pytest tests/integration/test_core_tenancy_migration.py -q

# Reversibilidad de la migración
uv run pytest tests/integration/test_migration_reversibility.py -q
```

Resultado verificado el 2026-11-05: `ruff` 0, `mypy app` 0, `pytest` **56 passed** (17 de
integración, ninguna skippeada con Docker arriba).

---

## 7. Migración y rollback

- **Upgrade** (`002_core_tenancy`): extensión `citext` → tipos enum → tablas → índices y
  constraints → rol de aplicación + grants → seed → RLS + políticas.
- **Downgrade**: drop de tablas en orden de FK → revoke de grants → drop del rol → drop de
  los tipos enum. La base queda como después de la baseline de C-01.
- **Rollback de código**: `git revert` del commit del change (no hay datos productivos).

---

## 8. Deuda explícita

| Deuda | Se resuelve en |
|-------|----------------|
| `membership.professional_id` sin FK | C-05 (`professional`) |
| `set_tenant_context` como dependencia FastAPI | C-03 (sesión + scopes) |
| Nombre/credenciales reales del rol en producción | Deploy (C-01 no tiene entorno productivo) |
| `tenant.estado` sin transición modelada | C-04 (onboarding/suspensión) |
