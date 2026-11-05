# Tasks

## 1. Contratos de dominio puros (sin base de datos)

- [x] 1.1 RED: escribir los tests unitarios de `validate_cuit` (RN-TEN-01) que fallan: CUIT válido `20-12345678-6` → `20123456786`; dígito verificador incorrecto `20-12345678-0` → `CuitError(motivo="digito_verificador")`; formato inválido (10 dígitos, 12 dígitos, letras) → `CuitError(motivo="formato")`. Verificación: `pytest tests/unit/test_cuit.py` falla por import inexistente.
- [x] 1.2 GREEN: implementar `backend/app/domain/tenancy/cuit.py` con el algoritmo módulo 11 y normalización. Verificación: 1.1 en verde.
- [x] 1.3 RED: escribir los tests unitarios de `tenant_id_from_claims` (RN-TEN-03) que fallan: claim `A` → `A`; sin claim → `TenantClaimError`; claim no-UUID → `TenantClaimError`; body con `tenant_id = B` y claims `A` → resuelve `A` (el body ni se pasa a la función). Verificación: `pytest tests/unit/test_tenant_guard.py` falla por import inexistente.
- [x] 1.4 GREEN: implementar `backend/app/core/tenant_guard.py` con firma que solo recibe `claims`. Verificación: 1.3 en verde.
- [x] 1.5 RED: escribir los tests de `set_tenant_context` que fallan: valor no-UUID → error de validación sin ejecutar SQL; el SQL generado usa `set_config(..., :tenant_id, true)` (parámetro bindeado, no interpolación); `str` UUID válido se normaliza. Verificación: `pytest tests/unit/test_tenant_context.py` falla.
- [x] 1.6 GREEN: implementar `backend/app/db/tenant_context.py` con `TENANT_SETTING_SQL` y `set_tenant_context`. Verificación: 1.5 en verde.

## 2. Modelos y migración `002_core_tenancy`

- [x] 2.1 RED: escribir el test de integración de la migración (Postgres 16 real) que falla: `alembic upgrade head` crea las 6 tablas, el enum `role` con 9 valores y los índices; `membership` sin `tenant_id` → SQLSTATE `23502`; `membership` con `user_id` inexistente → `23503`; dos `price_concept` globales con el mismo `codigo` → unicidad; global + mismo `codigo` en un tenant → permitido. Verificación: el test falla porque las tablas no existen.
- [x] 2.2 GREEN: implementar `app/models/{base,tenancy,catalog}.py`, apuntar `alembic/env.py` a `Base.metadata` y escribir `alembic/versions/002_core_tenancy.py` (DDL, enum, índices, `UNIQUE NULLS NOT DISTINCT`, rol `odontologia_app` + grants). Verificación: 2.1 en verde.
- [x] 2.3 RED: escribir el test del seed que falla: 2 monedas (`ARS`/`USD`), 9 especialidades, 80 `price_concept` globales, enum con 9 roles. Verificación: el test falla con 0 filas.
- [x] 2.4 GREEN: sembrar los catálogos en la migración **antes** de habilitar RLS (D5). Verificación: 2.3 en verde.
- [x] 2.5 RED: escribir el test de RN-TEN-04 que falla: un segundo `owner` activo en el mismo tenant → `23505`; un `owner` inactivo + un `owner` activo coexisten. Verificación: el test falla porque el índice parcial no existe.
- [x] 2.6 GREEN: agregar el índice único parcial `uq_membership_owner_activo` (`tenant_id WHERE rol = 'owner' AND activo`) en modelo y migración. Verificación: 2.5 en verde.

## 3. Row Level Security fail-closed

- [x] 3.1 RED: escribir la suite de aislamiento que falla: con `SET ROLE odontologia_app` y `app.current_tenant = A`, `SELECT` de `membership` devuelve solo A; sin contexto devuelve 0 filas; `UPDATE`/`DELETE` por id de B afecta 0 filas. Verificación: la suite falla porque RLS no está activa.
- [x] 3.2 GREEN: habilitar `ENABLE` + `FORCE ROW LEVEL SECURITY` y la política de `membership` con `NULLIF(current_setting('app.current_tenant', true), '')::uuid`. Verificación: 3.1 en verde.
- [x] 3.3 RED: escribir los tests de escritura que fallan: insertar/actualizar `membership` con `tenant_id = B` bajo contexto A → `42501`; insertar `price_concept` global bajo contexto A → `42501`; el catálogo global es visible para A y B, el override de B no es visible para A. Verificación: los tests fallan.
- [x] 3.4 GREEN: agregar las políticas `price_concept_read` y `price_concept_write` (D2). Verificación: 3.3 en verde.
- [x] 3.5 RED→GREEN: test de fuga por pool: fijar A, commit, reutilizar la conexión sin fijar tenant → 0 filas (el GUC quedó vacío); dos conexiones con tenants distintos no se pisan. Verificación: el test pasa y demuestra que `set_config(..., true)` es transaction-local.

## 4. Gate de aislamiento cross-tenant (RN-TEN-02)

- [x] 4.1 Escribir el test de aislamiento como gate de merge: tenant A no ve ni modifica `membership`/`price_concept` de B en ninguna operación; documentar y ejecutar la **prueba de mutación** (correr el mismo test como owner sin `SET ROLE`, o con la política eliminada, y comprobar que **falla**; restaurar y comprobar que pasa). Verificación: `cross-tenant leak = 0` y la mutación se documenta en `docs/core-tenancy.md`.

## 5. Verificación de integración y documentación

- [x] 5.1 Correr `uv run ruff check .`, `uv run mypy app` y `uv run pytest` (unit + integration con Docker) en verde. Verificación: los tres comandos terminan con código 0 y la salida muestra los tests de RLS ejecutados (no skippeados).
- [x] 5.2 Verificar reversibilidad: `alembic downgrade base` y `alembic upgrade head` sobre la base de test, sin errores. Verificación: el ciclo completo termina en verde y el seed vuelve a estar presente.
- [x] 5.3 Documentar en `docs/core-tenancy.md` el modelo, las políticas RLS, el rol de app, el seed y la prueba de mutación; enlazarlo desde `README.md`. Verificación: los comandos del documento corren tal como están escritos.
- [x] 5.4 Pasar `spec-scenario-review` sobre este change y dejar la evidencia en `docs/skills-mcp/evidencias/revision-c-02.md`. Verificación: veredicto `LISTO PARA APLICAR` (sin bloqueantes de tenancy) antes de archivar.
