# RBAC y gestión de equipo — matriz de permisos, contrato y pantalla de Equipo

Este documento describe lo que entrega el change `c-04-rbac-permissions`: la matriz de permisos
atómicos derivada de la Knowledge Base, cómo viajan en la sesión, la guarda `require_permission`,
el contrato de los cinco endpoints de equipo, la transferencia atómica de ownership, la auditoría
en `membership_event` y la pantalla de Equipo del SPA.

> Regla que manda: **RN-TEN-02** — el aislamiento cross-tenant es un gate de merge, no una
> recomendación. Ninguna operación de este change recibe el `tenant_id` del cliente: sale de la
> sesión y se revalida bajo RLS. `cross-tenant leak = 0` o el change no cuenta.

---

## 1. Qué se entrega

| Pieza | Dónde |
|---|---|
| Matriz RBAC (18 recursos × 9 roles → 57 permisos) | `backend/app/domain/rbac/matrix.py` |
| Catálogo de errores con `code` estable | `backend/app/domain/rbac/errors.py` |
| Guarda `require_permission(*permissions)` | `backend/app/domain/rbac/guard.py` |
| Migración `004_rbac` (`membership_event` append-only) | `backend/alembic/versions/004_rbac.py` |
| Reglas de dominio (lista, alta, cambio de rol, baja, transferencia) | `backend/app/domain/team/service.py` |
| Router + DTOs | `backend/app/api/v1/team/router.py`, `backend/app/schemas/team.py` |
| `permissions[]` en la sesión | `backend/app/schemas/auth.py` (`SessionOut`) |
| Cliente API + roles asignables | `frontend/src/api/team.ts`, `frontend/src/features/team/roles.ts` |
| Guarda de UI y pantalla de Equipo | `frontend/src/features/auth/RequirePermission.tsx`, `frontend/src/features/team/TeamPage.tsx` |
| Tests (unitarios, integración Postgres real, RLS, e2e) | `backend/tests/**`, `frontend/src/**/*.test.tsx`, `frontend/tests/e2e/team.spec.ts` |

---

## 2. Matriz de permisos

Un permiso es **atómico** y se nombra `recurso.acción` (`design D1`). Se derivan 1:1 de la matriz de
`knowledge-base/03_actores_y_roles.md`: **18 recursos × 9 roles = 57 permisos**, sin alias ni
permisos "comodín".

| Recurso | Acciones declaradas |
|---|---|
| `tenant_settings` | `create`, `read`, `update` |
| `chair` | `create`, `read`, `update`, `delete` |
| `professional` | `create`, `read`, `update` |
| `team` | `create`, `read`, `update`, `delete` |
| `ownership` | `transfer` |
| `clinical_record` | `create`, `read`, `update`, `read_own` |
| `chart` | `create`, `read`, `update`, `finalize`, `read_own` |
| `consent` | `create`, `read`, `read_own` |
| `appointment` | `create`, `read`, `update`, `delete`, `create_own`, `read_own` |
| `cash` | `create`, `read`, `update`, `read_own` |
| `invoice` | `create`, `read`, `update`, `read_own` |
| `settlement` | `create`, `read`, `update`, `read_own` |
| `report_financial` | `read` |
| `report_usage` | `read` |
| `migration` | `create`, `read`, `update` |
| `aaip_request` | `create`, `read`, `create_own` |
| `whatsapp_config` | `create`, `read`, `update` |
| `membership_event` | `read` — declarado para que la matriz sea explícita; **ningún rol lo tiene** (RN-CMP-03) |

Permisos efectivos por rol:

| Rol | Permisos |
|---|---|
| `owner` | 41 |
| `clinical_admin` | 19 |
| `professional` | 15 |
| `assistant` | 12 |
| `front_desk` | 17 |
| `billing` | 16 |
| `patient` | 8 |
| `external_lab` | 1 |
| `accountant` | 3 |

Las filas que gobierna este change, tal como están en la matriz:

| Recurso | `owner` | `clinical_admin` | `professional` | `assistant` | `front_desk` | `billing` | `patient` | `external_lab` | `accountant` |
|---|---|---|---|---|---|---|---|---|---|
| `team` | `CRUD` | `R` | — | — | — | `R` | — | — | — |
| `ownership` | `T` | — | — | — | — | — | — | — | — |
| `membership_event` | — | — | — | — | — | — | — | — | — |

Lectura: solo `owner` escribe el equipo y solo `owner` transfiere la titularidad; `clinical_admin`
y `billing` pueden **leer** la lista. Un rol nuevo no obliga a tocar el frontend: la UI consulta
`hasPermission(...)`, nunca compara roles.

### 2.1 Reglas horizontales que no se deducen de la matriz

- `chart.finalize` es exclusivo de `professional`: cerrar una historia clínica es un acto del
  profesional interviniente (RN-CMP-04).
- Sin `delete` físico en `clinical_record` ni `chart`: la historia clínica es append-only
  (Ley 26.529, RN-CMP-02).
- Los roles de portal (`patient`, `external_lab`, `accountant`) nunca reciben permisos clínicos.

---

## 3. Permisos en la sesión

`SessionOut` (respuesta de `/auth/login`, `/auth/me` y `/auth/refresh`) incluye `permissions`:

```json
{
  "user": { "id": "…", "email": "admin@example.test", "nombre": "Clara", "apellido": "Admin" },
  "tenant": { "id": "…", "slug": "clinica-demo", "nombre_comercial": "Clínica Demo" },
  "roles": ["clinical_admin"],
  "permissions": ["aaip_request.read", "appointment.create", "…", "team.read"],
  "mfa_enrolled": false
}
```

- `permissions` es la **unión** de permisos de las memberships activas del usuario en el tenant de
  la sesión, resuelta por `resolve_permissions(roles)` y ordenada alfabéticamente (`sorted`): dos
  llamadas con el mismo estado devuelven exactamente el mismo array.
- El frontend expone `hasPermission(permission)` desde `AuthProvider` y `RequirePermission` como
  guarda de ruta. Es la **única** forma de decidir visibilidad: `frontend/src/features/auth/rolesSweep.test.ts`
  falla si alguien compara `session.roles` contra un literal (`'owner'`, `'front_desk'`, …).
- La autorización real es siempre del backend. Ocultar un botón es UX; el `403` es la garantía.

---

## 4. Guarda y catálogo de errores

Cadena de dependencias de todo endpoint protegido:

```
require_auth → require_tenant → require_permission(Permission.x[, …])
```

`require_permission` exige **todos** los permisos indicados (AND, sin OR implícito). El permiso que
falta se registra en el log de aplicación

```
rbac: acceso denegado tenant=… user=… roles=['front_desk'] faltan=['team.read']
```

y la respuesta es siempre el mismo `403` genérico: nunca incluye ids, emails, roles ajenos ni
`tenant_id`.

### 4.1 Catálogo `RbacErrorCode` (13 `code` estables)

| `code` | HTTP | Cuándo |
|---|---|---|
| `forbidden` | 403 | La sesión no tiene el permiso del endpoint |
| `membership_not_found` | 404 | La membership no existe **en este tenant** (indistinguible de un id ajeno) |
| `membership_exists` | 409 | El usuario ya tiene una membership activa con ese rol |
| `role_conflict` | 409 | El rol pedido choca con **otra** membership del mismo usuario (multi-rol) |
| `owner_must_be_transferred` | 409 | Se intentó asignar `owner` por `POST`/`PATCH` |
| `last_owner` | 409 | La operación dejaría la clínica sin owner activo |
| `ownership_changed` | 409 | El actor perdió la carrera de transferencia: ya no es owner activo |
| `member_inactive` | 409 | El target de la transferencia está dado de baja |
| `member_is_actor` | 409 | La transferencia apunta a la propia membership |
| `member_already_owner` | 409 | El target ya es owner |
| `role_not_assignable` | 422 | Rol fuera de `ASSIGNABLE_ROLES` (incluye roles de portal y `owner`) |
| `invalid_request` | 422 | El body tiene campos inválidos o **no declarados** (p. ej. `tenant_id`) |
| `capability_pending` | 501 | Endpoint sonda de una capacidad que llega en C-05/C-06 |

Shape único: `{"code": "<code>", "message": "<mensaje en español>"}`. El frontend conmuta por
`code`, nunca por status ni por el texto.

---

## 5. Contrato HTTP (5 endpoints)

Todos bajo `/api/v1/team`, todos con `require_auth` + `require_tenant`, ninguno recibe `tenant_id`.

| Método | Ruta | Permiso | Respuesta |
|---|---|---|---|
| `GET` | `/team/members` | `team.read` | `200 {"members": [MemberOut…]}` |
| `POST` | `/team/members` | `team.create` | `201 MemberOut` |
| `PATCH` | `/team/members/{membership_id}` | `team.update` | `200 MemberOut` |
| `DELETE` | `/team/members/{membership_id}` | `team.delete` | `204` |
| `POST` | `/team/ownership-transfer` | `ownership.transfer` | `200 {"members": […]}` |

`MemberOut` es una lista blanca: `id`, `user_id`, `email`, `nombre`, `apellido`, `rol`, `activo`,
`professional_id`. Nunca `password_hash`, `mfa_secret`, `tenant_id` ni `permissions`.
`professional_id` es `null` hasta C-05, igual que en el contrato del change.

La lista incluye memberships **activas e inactivas** (baja lógica, RN-EX-03) y se ordena por
`rol, apellido, nombre, id`: `membership` no tiene `created_at` en el DDL de `002`, así que el orden
se fija con esas cuatro columnas para ser determinista entre llamadas.

### 5.1 `tenant_id` y campos no declarados

Los tres DTOs de entrada usan `extra="forbid"`. Por lo tanto:

- `tenant_id` (o cualquier campo desconocido) en el **body** → `422 invalid_request`.
- `tenant_id` en **query** o en un header (p. ej. `X-Tenant-Id`) → se ignora: la request se resuelve
  con el tenant de la sesión y responde `200`.
- El `422` es siempre el del catálogo: un handler global de `RequestValidationError` traduce el
  `detail` de Pydantic a `{"code": "invalid_request", "message": …}`, de modo que nunca se filtra el
  nombre del campo inválido ni la estructura interna.
- La guarda de permisos corre **antes** de validar el body: un `front_desk` que manda `tenant_id`
  recibe `403 forbidden`, no `422`. Es deliberado: el `403` no confirma ni niega nada del body.

### 5.2 Alta de miembro (`POST /team/members`)

```json
{ "email": "nuevo@example.test", "rol": "assistant", "password_temporal": "al-menos-12-caracteres" }
```

- **Sin invitaciones por email** (PQ-08): el sistema no manda correos. La `password_temporal` la
  elige el owner y se comunica por fuera; se guarda como Argon2id, **nunca** se devuelve ni se
  registra en la auditoría ni en los logs.
- Si el email corresponde a un usuario global existente, se le crea la membership sin pedir
  contraseña. Si no existe, `password_temporal` es obligatoria → sin ella, `422 invalid_request`
  **antes** de escribir cualquier fila.
- Un usuario creado por esta vía queda con `nombre = <parte local del email>` y `apellido = ""`
  (deuda documentada: el owner completa el perfil en C-05).
- Readmisión: si existía una membership **inactiva** con ese `(tenant, usuario, rol)`, se reactiva
  (evento `member_reactivated`) en lugar de insertar otra fila. Si ya estaba activa →
  `409 membership_exists`.
- El rol se valida contra `ASSIGNABLE_ROLES = {clinical_admin, professional, assistant, front_desk,
  billing, accountant}`; `owner` responde `409 owner_must_be_transferred` y un rol de portal
  `422 role_not_assignable`.

### 5.3 Cambio de rol (`PATCH /team/members/{id}`)

- `{"rol": "<asignable>"}`. Mismo rol que el actual → `200` **sin** evento nuevo (idempotente).
- `owner` nunca se asigna por acá (`409 owner_must_be_transferred`); se transfiere.
- Si el usuario ya tiene **otra** membership con el rol pedido → `409 membership_exists` (el único
  `(tenant_id, user_id, rol)` no es parcial).
- Cambiar el rol del **único** owner activo → `409 last_owner`: el único camino legítimo para dejar
  de ser owner es la transferencia.

### 5.4 Baja lógica (`DELETE /team/members/{id}`)

- Baja **lógica**: `activo = false`, la fila queda (RN-EX-03) con evento `member_deactivated`.
- Idempotente: la segunda baja responde `204` sin un segundo evento.
- Último owner activo → `409 last_owner`.
- Un id de otro tenant responde exactamente igual que uno inexistente (`404 membership_not_found`):
  RLS lo filtra antes de que el servicio lo vea, así que la respuesta no distingue "no existe" de
  "no es tuyo".

### 5.5 Transferencia de ownership (`POST /team/ownership-transfer`)

```json
{ "target_membership_id": "…", "previous_owner_role": "clinical_admin" }
```

Flujo (`design D7`), en **una** transacción:

1. `previous_owner_role` debe ser asignable y distinto de `owner` → si no, `422 role_not_assignable`.
2. `SELECT id FROM tenant WHERE id = :tid FOR UPDATE` — serializa las transferencias del tenant. El
   lock no lee datos de negocio.
3. Bajo el lock, revalidar que el actor sigue siendo owner activo. Si perdió una carrera anterior →
   `409 ownership_changed`.
4. Cargar el target con `FOR UPDATE`: debe existir en el tenant, estar activo, no ser el actor y no
   ser owner (`membership_not_found`, `member_inactive`, `member_is_actor`, `member_already_owner`).
5. Dos chequeos simétricos de `role_conflict` (lado actor y lado destino) antes de escribir.
6. **Demover al actor sin darlo de baja**: `rol = previous_owner_role`, `activo` intacto, `flush()`
   intermedio. El slot del índice parcial `uq_membership_owner_activo` se libera porque la fila deja
   de ser `owner`.
7. **Promover al target**: `rol = 'owner'`, segundo `flush()`.
8. Insertar `ownership_transferred` con
   `{rol_anterior: "owner", rol_nuevo: <previous_owner_role>, target_rol_anterior: <rol previo>}`,
   leer la lista dentro de la transacción y commitear.

Consecuencias observables:

- El owner saliente **conserva el acceso** con su rol nuevo: su siguiente request recibe `403` (le
  falta el permiso), nunca `401` (sesión inválida). Se verifica en el escenario S5.5.
- Nunca hay cero ni dos owners activos: la transacción es atómica y el orden es "demover → promover".
- Si dos transferencias del mismo tenant corren a la vez, la segunda espera el lock y al revalidar
  ya no encuentra al actor como owner → `409 ownership_changed` (probado con `threading.Barrier`).

---

## 6. Aislamiento y auditoría

- **RLS**: `membership` tiene `ENABLE` + `FORCE ROW LEVEL SECURITY` con política
  `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid` para `USING` y
  `WITH CHECK`. Sin contexto el predicado es `NULL` → **cero filas** (fail-closed), nunca todas.
- **Rol de aplicación**: la app se conecta como `odontologia_app` (`NOLOGIN NOSUPERUSER NOBYPASSRLS`)
  y abre cada conexión con `SET ROLE`. Un superusuario ignoraría RLS incluso con `FORCE` y el
  aislamiento sería ficticio; por eso el test verifica `current_user = odontologia_app` después de
  un `rollback`, de un `commit` y de reutilizar la conexión desde el pool.
- **Auditoría**: `membership_event` es **append-only** — `odontologia_app` tiene `INSERT` y `USAGE`
  de la secuencia, pero **no** `SELECT`: leerla es error de permisos (no 0 filas silencioso). Un
  trigger rechaza `UPDATE`/`DELETE`. Eventos: `member_created`, `member_reactivated`,
  `member_role_changed`, `member_deactivated`, `ownership_transferred`.

El gate completo está en `backend/tests/integration/test_team_rls.py` (11 tests): nivel SQL (A nunca
ve memberships ni emails de B; `UPDATE`/`DELETE` sobre un id ajeno afecta 0 filas; fail-closed sin
contexto; `INSERT` cross-tenant rechazado; `membership_event` sin `SELECT`), nivel HTTP (el engine de
la app es `odontologia_app`; sin datos de B; `PATCH`/`DELETE` ajenos → `404` idéntico a inexistente;
`tenant_id` en body → `422` en los cinco endpoints; query/header ignorados; `403` gana al `422`) y la
prueba de mutación de gate (`DISABLE ROW LEVEL SECURITY` → el gate se pone rojo; `ENABLE`/`FORCE` →
verde otra vez).

---

## 7. Pantalla de Equipo

`/equipo` (`frontend/src/features/team/TeamPage.tsx`), protegida por
`<RequirePermission permission="team.read">`:

- Tabla con nombre, email, rol y estado de cada miembro (incluye inactivos).
- `<select>` + **Guardar rol** solo con `team.update`; **Dar de baja** solo con `team.delete`;
  **Transferir titularidad** solo con `ownership.transfer` y nunca sobre el owner actual.
- Un `403` de la API se mapea a `Forbidden` con su `code` visible; un error de negocio se muestra
  con su `code` (por ejemplo `last_owner`) para que la demo sea diagnóstica sin filtrar detalles.
- El enlace **Equipo** de la Home aparece solo con `team.read`.
- `ASSIGNABLE_ROLES` y `ROLE_LABELS` viven en `features/team/roles.ts`, fuera del módulo mockeado
  por los tests (`@/api/team`).

---

## 8. Demo (guion de 3 minutos para el video)

Credenciales ficticias del seed de e2e (`backend/tests/fixtures/seed_auth_e2e.py`), tenant
`clinica-demo`. Todas las cuentas comparten la contraseña `demo-password-123`.

| Cuenta | Rol | Para qué |
|---|---|---|
| `owner@example.test` | `owner` | MFA obligatorio; secreto TOTP `JBSWY3DPEHPK3PXP` |
| `admin@example.test` | `clinical_admin` | Ve la lista, no gestiona |
| `desk@example.test` | `front_desk` | Rechazo: sin enlace y `403` |
| `profe@example.test` | `professional` | Destino del cambio de rol |
| `demo@example.test` | `professional` | Flujo de auth de C-03 |

El código TOTP de 6 dígitos se calcula con cualquier app autenticadora (Google Authenticator,
Aegis, 1Password) cargando el secreto `JBSWY3DPEHPK3PXP`. Para el e2e automatizado, el helper
`totp()` de `frontend/tests/e2e/team.spec.ts` reproduce el mismo algoritmo (HMAC-SHA1 sobre el
contador de 30 s con truncado dinámico) y tiene un test que lo compara con el vector de RFC 6238.

Guion, paso a paso con resultado observable:

1. **Login owner con MFA** (`00:00`–`00:40`). `http://localhost:5173/login`, clínica `clinica-demo`,
   email `owner@example.test`, contraseña `demo-password-123`, **Ingresar**.
   → Aparece *Verificación en dos pasos*. Se ingresa el código de 6 dígitos.
   → Resultado: Home con “Clínica Demo · Olivia Owner” y el enlace **Equipo** visible.
2. **Pantalla de Equipo** (`00:40`–`01:20`). Clic en **Equipo**.
   → Resultado: tabla con las 5 memberships de `clinica-demo`; ningún `ajeno@example.test` (tenant B)
   en la lista. Fila de `profe@example.test` con rol `professional`.
3. **Cambio de rol** (`01:20`–`02:00`). En la fila de `profe@example.test`, elegir
   *Asistente* en el `<select>` y **Guardar rol**.
   → Resultado: aviso *Rol actualizado.* y la celda de rol pasa de `professional` a `assistant`
   (persistido: recargar la página lo mantiene).
4. **Login recepcionista y rechazo** (`02:00`–`02:50`). **Salir**; login con `desk@example.test`
   y la misma contraseña (sin MFA).
   → Resultado: la Home **no** muestra el enlace Equipo. Navegar a mano a `/equipo` →
   *No tenés permiso para ver esta sección.*
   → En la pestaña Network (o `curl`), `GET /api/v1/team/members` devuelve
   `403 {"code":"forbidden","message":"No tenés permiso para realizar esta operación."}`.
   → En el log del backend: `rbac: acceso denegado … roles=['front_desk'] faltan=['team.read']`.
5. **Cierre** (`02:50`–`03:00`). Volver al login y mostrar que el cambio de rol del paso 3 sigue
   vigente (misma fila, `assistant`).

Evidencia de que no hay fuga cross-tenant: en el paso 2 la lista **solo** trae los 5 emails del
tenant A, y `backend/tests/integration/test_team_rls.py` congela ese invariante.

---

## 9. Orquestación del e2e

El e2e corre contra el **backend real** (Postgres 16 + Redis 7 en Testcontainers, cadena completa de
Alembic y seed) y el Vite real, igual que `docs/auth.md` § 10.

```bash
cd frontend && npm run test:e2e
```

- `frontend/tests/e2e/team.spec.ts` declara `test.describe.configure({ mode: 'serial' })` para los
  tests que mutan roles (la config habilita `fullyParallel`).
- Si `5173` está ocupado: `E2E_WEB_PORT=5180 npm run test:e2e`.
- El seed **borra y reinserta** las memberships de `clinica-demo` y `clinica-demo-b` en cada
  arranque, así que un run que cambió roles no contamina el siguiente
  (`backend/tests/integration/test_seed_e2e.py` verifica la idempotencia).
- Puerto del backend: `E2E_BACKEND_PORT` (8000 por defecto).

---

## 10. Verificación (salida real)

Todo lo de abajo se corrió el **2026-11-10** sobre `main` con Docker Desktop activo (Postgres 16 +
Redis 7 en Testcontainers).

### 10.1 Backend

```console
$ cd backend
$ uv run ruff check app tests alembic
All checks passed!

$ uv run mypy app
Success: no issues found in 52 source files

$ uv run pytest -q
334 passed, 1 warning in 51.31s
```

El gate de aislamiento se corre solo para ver su detalle:

```console
$ uv run pytest tests/integration/test_team_rls.py -q
11 passed, 1 warning in 19.30s

$ uv run pytest "tests/integration/test_team_rls.py::test_mutar_rls_desactivada_rompe_el_gate_y_restaurarla_lo_deja_verde" -q -s
[9.2] RLS ON  -> la app ve 2 memberships de A, 0 de B
[9.2] RLS OFF -> la app ve 4 memberships: 2 de B se filtrarian (9.1a ROJO)
[9.2] RLS ON  -> gate VERDE otra vez: cross-tenant leak = 0
1 passed
```

### 10.2 Frontend

```console
$ cd frontend
$ npx eslint .
C:\…\frontend\src\components\ui\button.tsx
  57:18  warning  Fast refresh only works when a file only exports components. …
✖ 1 problem (0 errors, 1 warning)

$ npx tsc -b
(sin salida: sin errores)

$ npx vitest run
 Test Files  8 passed (8)
      Tests  43 passed (43)

$ E2E_WEB_PORT=5180 npx playwright test
Running 11 tests using 7 workers
  ok 1  smoke.spec.ts  › sin sesión, la raíz muestra el login
  ok 2  auth.spec.ts   › credenciales inválidas muestran el error del catálogo
  ok 3  auth.spec.ts   › login válido llega a la home con el tenant de la sesión
  ok 4  auth.spec.ts   › logout vuelve a /login y una recarga no restaura la sesión
  ok 5  auth.spec.ts   › sin sesión, la raíz redirige a /login
  ok 6  team.spec.ts   › el helper TOTP reproduce el vector de RFC 6238
  ok 7  smoke.spec.ts  › con sesión, la raíz muestra la home
  ok 8  team.spec.ts   › recepción no ve el enlace Equipo y /equipo muestra acceso denegado
  ok 9  team.spec.ts   › recepción forzando GET /team/members recibe 403 forbidden
  ok 10 team.spec.ts   › administrativo clínico ve la lista pero no los botones de gestión
  ok 11 team.spec.ts   › owner con TOTP ve la lista y cambia el rol de un miembro
11 passed (12.6s)
```

El warning de `button.tsx` es **preexistente** (componente shadcn que exporta `buttonVariants`);
este change no agrega warnings de lint.

### 10.3 Detalle por capa

| Capa | Archivo | Tests |
|---|---|---|
| Matriz RBAC | `backend/tests/unit/test_rbac_matrix.py` | 13 |
| Errores, guard y `permissions[]` | `backend/tests/unit/test_rbac_errors.py`, `…/test_rbac_guard.py` | — |
| Fronteras clínicas (sondas `501`) | `backend/tests/integration/test_clinical_permissions.py` | 10 |
| Migración `004_rbac` | `backend/tests/integration/test_membership_event_migration.py` | 15 |
| Lista / alta / cambio / baja | `backend/tests/integration/test_team_members_*.py` | 13 + 12 + 10 + 5 |
| Transferencia de ownership | `backend/tests/integration/test_team_ownership_transfer.py` | 15 |
| Aislamiento cross-tenant (gate) | `backend/tests/integration/test_team_rls.py` | 11 |
| Seed e2e idempotente | `backend/tests/integration/test_seed_e2e.py` | 1 |
| UI de permisos y Equipo | `frontend/src/features/auth/permissions.test.tsx`, `…/team/TeamPage.test.tsx`, `…/routes/Home.test.tsx`, `…/auth/rolesSweep.test.ts` | 7 + 8 + 2 + 2 |
| e2e | `frontend/tests/e2e/team.spec.ts` | 5 |

---

## 11. Deudas y desviaciones registradas

| Deuda | Motivo |
|---|---|
| Sin invitaciones por email (PQ-08) | Recorte acordado: el alta usa `password_temporal` fuera de banda |
| `nombre`/`apellido` derivados del email en altas nuevas | El DTO del alta no los pide; se completan en C-05 |
| `professional_id` siempre `null` | La entidad `professional` llega en C-05 |
| Endpoints sonda `GET /clinical/patients` y `POST /clinical/charts/finalize` → `501 capability_pending` | Fijan la frontera de permisos antes de que exista la capacidad |
| `mypy app tests` falla por módulos duplicados (`tests/conftest.py` vs `tests/integration/conftest.py`) | Preexistente; el gate real es `mypy app` |
