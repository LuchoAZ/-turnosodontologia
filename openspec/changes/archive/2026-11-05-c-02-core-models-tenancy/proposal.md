# Proposal — c-02-core-models-tenancy

## Why

El sistema odontológico es multi-tenant por diseño (una PyME = un `tenant`), y hoy el repositorio
solo tiene el sustrato de C-01: no existe ninguna tabla de negocio, ni aislamiento por tenant, ni
catálogos base. Sin este change no se puede implementar ningún flujo de la "ruta del turno"
(C-03 auth, C-05 profesionales/sillones, C-06 pacientes, `agendar-turno`): todos necesitan un
`tenant_id`, una sesión de base con el tenant activo y las tablas de identidad.

El riesgo dominante no es funcional sino de seguridad: un solo leak cross-tenant destruye la
confianza de todas las clínicas (RN-TEN-02). Por eso este change implementa el aislamiento en
cuatro capas (defense in depth) desde el primer modelo, y deja el test cross-tenant como gate de
merge, no como una tarea opcional.

## What Changes

- **Modelos SQLAlchemy 2.0 tipados** (`Mapped`/`mapped_column`, sin `Any`): `tenant`, `user`,
  `membership`, `specialty`, `price_concept`, `currency` + enum `role` con los 9 roles de la KB.
- **Migración Alembic `002_core_tenancy`**: DDL de las 6 tablas, tipos enum, índices, constraint
  de unicidad global/tenant en `price_concept`, rol de aplicación no-superusuario y semilla de
  catálogos.
- **Row Level Security fail-closed** en las tablas tenant-scoped (`membership`, `price_concept`):
  políticas con `current_setting('app.current_tenant', true)`, `FORCE ROW LEVEL SECURITY` y rol de
  app sin `BYPASSRLS`.
- **Contexto de tenant por transacción**: helper que ejecuta
  `SELECT set_config('app.current_tenant', :tenant_id, true)` (parameterizado, transaction-local)
  y garantiza que el valor no se filtre entre transacciones del pool.
- **`TenantGuard`** (RN-TEN-03): función pura que resuelve el `tenant_id` exclusivamente de los
  claims de la sesión e **ignora** cualquier `tenant_id` del body/query/header. La dependencia
  FastAPI se conecta en C-03; acá queda el seam testeable y el contrato de error (`401`).
- **Validación de CUIT (RN-TEN-01)**: función pura módulo 11 con tests (válido, dígito inválido,
  formato inválido).
- **Seed de catálogos**: 2 monedas (`ARS`, `USD`), 9 especialidades (las de la KB), 80 conceptos de
  precio globales de referencia (`tenant_id IS NULL`) y el enum de 9 roles.
- **Gate RN-TEN-02**: suite de integración con Postgres 16 real (Testcontainers) que demuestra
  `cross-tenant leak = 0` y falla si se quita el aislamiento (prueba de mutación).

## Impact

| Área | Impacto |
|------|---------|
| Backend (`app/models`, `app/domain/tenancy`, `app/core`) | Nuevo módulo de modelos y seams de tenancy |
| Base de datos | Migración `002_core_tenancy` (tablas, RLS, rol de app, seed) |
| Tests | Nuevos unitarios (CUIT, guard, contexto) e integración con Postgres real (RLS, seed, migración) |
| Documentación | `docs/core-tenancy.md` + sección en `README.md` |
| Cambios existentes | Desbloquea C-03, C-05, C-06 y `agendar-turno-sin-solapamiento` |

**Governance**: CRÍTICO (tenancy + seguridad). Sin test de aislamiento no se archiva.

## Dependencies

- C-01 `foundation-setup` (archivado): engine SQLAlchemy, Alembic baseline, Testcontainers, CI.
- KB: `04_modelo_de_datos.md` (§ Tenancy, § Catálogos, § Estrategia de aislamiento),
  `05_reglas_de_negocio.md` (§ Tenancy), `03_actores_y_roles.md` (§ roles).

## Out of Scope

- Autenticación, emisión y verificación de tokens (C-03). Acá solo el seam `TenantGuard`.
- `professional`, `chair`, `patient`, `appointment` y `availability_rule` (C-05, C-06, C-07).
- CRUD/endpoints de tenants, usuarios o catálogos: este change entrega modelo + aislamiento + seed.
- UI: C-02 es infraestructura de datos; el primer vertical slice con pantalla es C-03/C-07.
