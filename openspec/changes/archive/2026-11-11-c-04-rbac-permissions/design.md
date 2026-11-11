# Design — c-04-rbac-permissions

## Context

C-03 dejó la cadena `require_auth` → `require_tenant` (`backend/app/api/v1/deps.py`) resolviendo
`AuthContext` con `user`, `session`, `tenant_id` y `roles: list[Role]` (unión de memberships activas
del tenant, leídas bajo RLS). No existe ninguna guarda de autorización, ni catálogo de permisos, ni
endpoint de negocio protegido por otro criterio que "tener membership".

El sustrato que este change consume y no redefine:

- `Role` (9 valores, `backend/app/models/tenancy.py`) y `Membership` con `tenant_id NOT NULL`,
  `user_id`, `rol`, `professional_id` nullable, `activo`, más `uq_membership_tenant_user_rol` y el
  índice único parcial `uq_membership_owner_activo` (`tenant_id WHERE rol = 'owner' AND activo`).
- RLS `FORCE` en `membership` con `NULLIF(current_setting('app.current_tenant', true), '')::uuid`
  y `set_tenant_context` (`set_config(..., true)`, transaction-local), aplicado por `require_auth`.
- `odontologia_app` tiene `SELECT, INSERT, UPDATE, DELETE` sobre las tablas de C-02 (incluido
  `user`, que es global y sin RLS), así que dar de alta usuarios y memberships no requiere grants
  nuevos; la migración nueva sí otorga solo `INSERT` sobre `membership_event`.
- `SessionOut` (`schemas/auth.py`) con `user`, `tenant`, `roles`, `mfa_enrolled`, serializado por
  `service.session_out` en login, refresh, MFA y switch-tenant.
- El catálogo de `code` de C-03 en `docs/auth.md` § 3.1 y `AuthError`/`AuthErrorCode`; el frontend
  conmuta por `code` (`ApiError.code`).
- El SPA: `AuthProvider` restaura la sesión con `/auth/me`, `RequireAuth` protege rutas y
  `src/api/http.ts` reintenta una vez tras `401`. No hay ningún guard por permiso.

Restricciones que mandan: governance ALTO; RN-TEN-02 (test cross-tenant es gate), RN-TEN-03
(`tenant_id` del token), RN-TEN-04 (exactamente un owner, transferencia atómica), RN-TEN-05
(permisos por tenant activo), RN-CMP-04 (frontera clínica), RN-CMP-03 (auditoría append-only,
mismo patrón de RN-CMP-02), RN-EX-03 (soft
delete), Strict TDD con Postgres real (sin mocks de DB) y vertical slice.

Ver `proposal.md` § Why para la motivación y `specs/platform-rbac/spec.md` /
`specs/platform-team/spec.md` para el contrato. Este documento explica cómo se cumple.

## Goals / Non-Goals

**Goals**

- Una sola fuente de verdad de autorización: matriz declarativa + resolución pura + guarda HTTP, sin
  chequeos de rol dispersos en endpoints ni en el SPA.
- Demostrar el criterio 3 del TPI con UI: acceso autorizado (pantalla de Equipo) y rechazo visible
  (`403 forbidden` y pantalla de acceso denegado).
- Cerrar la invariante que C-02 delegó: nunca cero owners, con transferencia atómica y concurrencia
  verificada.
- Dejar `membership_event` append-only con el mismo patrón probado de `auth_event`, para que C-14 lo
  absorba o lo complemente sin rediseñar.

**Non-Goals**

- Enforcement de los permisos de recursos que aún no existen (sillones, profesionales, clínica,
  facturación, caja): se declaran en la matriz, se testean como tabla y los aplica el change dueño
  del recurso.
- Invitaciones con email y aceptación (PQ-08), flags por tenant (`billing.can_read_clinical`),
  scopes por fila (un profesional solo ve sus turnos) y roles fuera de los 4 del flujo ejercitados
  por HTTP.
- `audit_log` definitivo (C-14), MFA distinto del que ya exige C-03 y rate limiting de los endpoints
  de equipo.

## Decisions

### D1 — Permisos atómicos `recurso.accion` derivados 1:1 de la matriz de la KB

Se declara `backend/app/domain/rbac/matrix.py` con tres piezas:

1. `class Permission(StrEnum)` con todos los permisos atómicos.
2. `ROLE_PERMISSIONS: dict[Role, frozenset[Permission]]` — una entrada por cada uno de los 9 roles.
3. `RESOURCE_ACTIONS: dict[str, frozenset[str]]` — la transcripción independiente de la tabla de
   `knowledge-base/03_actores_y_roles.md` líneas 33-48 (rol × recurso → letras `C R U D`).

Los 18 recursos y su correspondencia:

| Recurso de la KB (03 § RBAC) | Namespace de permisos |
|---|---|
| Configuración del tenant | `tenant_settings.create/read/update` |
| Sillones | `chair.create/read/update/delete` |
| Profesionales | `professional.create/read/update` |
| Usuarios y roles (se desdobla) | `team.create/read/update/delete` + `ownership.transfer` |
| Historias clínicas | `clinical_record.create/read/update` + `clinical_record.read_own` (paciente) |
| Odontograma / periodontograma | `chart.create/read/update` + `chart.read_own` + `chart.finalize` |
| Consentimientos | `consent.create/read` + `consent.read_own` |
| Turnos (agenda) | `appointment.create/read/update/delete` + `appointment.create_own` + `appointment.read_own` |
| Caja / movimientos | `cash.create/read/update` + `cash.read_own` |
| Comprobantes fiscales | `invoice.create/read/update` + `invoice.read_own` |
| Liquidaciones a profesionales | `settlement.create/read/update` + `settlement.read_own` |
| Reportes financieros | `report_financial.read` |
| Reportes de utilización | `report_usage.read` |
| Migraciones | `migration.create/read/update` |
| Solicitudes AAIP | `aaip_request.create/read` + `aaip_request.create_own` |
| Configuración de WhatsApp | `whatsapp_config.create/read/update` |
| Auditoría de RBAC (nuevo) | `membership_event.read` (sin titulares) |

Total: **18 recursos** = 16 filas de la KB − 1 ("Usuarios y roles") + 2 (`team` y `ownership`) +
1 (`membership_event`). La fila "Usuarios y roles" se desdobla porque RN-TEN-04 exige que la
transferencia de ownership sea una operación distinta del CRUD de roles (el owner **no** puede
asignar `owner` por el endpoint de miembros; D7). `membership_event` se declara como recurso para
que la matriz sea explícita sobre la auditoría: **ningún rol** tiene `membership_event.read`, y el
test lo verifica (fail-closed, coherente con RN-CMP-03).

Reglas de derivación, aplicadas mecánicamente y testeadas:

- `C` → `create`, `R` → `read`, `U` → `update`, `D` → `delete`, `—` → sin permiso.
- "R (propia/propio/propios)" y "C (propia)" se traducen a `read_own`/`create_own` del rol que la
  KB marca, nunca a `read`/`create` pleno: el paciente recibe `clinical_record.read_own`,
  `chart.read_own`, `consent.read_own`, `appointment.create_own`, `appointment.read_own`,
  `cash.read_own`, `invoice.read_own` y `aaip_request.create_own`; el odontólogo recibe
  `settlement.read_own` para sus liquidaciones (KB líneas 37-43). En total 9 permisos `_own` y
  **ningún rol interno hereda los del paciente** (los internos no tienen `_own`).
- Las 7 restricciones horizontales se aplican como excepciones **explícitas** sobre la matriz base,
  en un solo bloque documentado: (1) `front_desk` nunca recibe `clinical_record.read` ni
  `chart.read`; (2) `chart.finalize` solo para `professional` (el `U` del odontograma del
  higienista no lo habilita); (3) `billing` no recibe `clinical_record.read/update` (el flag por
  tenant queda como deuda); (4) nadie tiene `clinical_record.delete` ni `chart.delete`; (5) el
  paciente solo `_own`; (6) `external_lab` sin permisos clínicos; (7) no existe el rol SuperAdmin en
  el enum, así que no se modela.

El test de fidelidad compara `RESOURCE_ACTIONS` contra `ROLE_PERMISSIONS` y falla si divergen; es una
tabla parametrizada de 9 roles × 18 recursos sin base de datos.

- Alternativas: (a) `require_role("owner")` y comparaciones de rol → se descarta porque la UI y los
  endpoints acabarían replicando la matriz y las excepciones horizontales; (b) permisos agregados
  (`team.manage`, `clinical.write`) → menos nombres pero pierde la distinción `C/U/D` que la KB sí
  tiene (`front_desk` puede `C R U D` de turnos, `clinical_admin` no puede `D`); (c) ABAC/scopes por
  fila → necesario para "un profesional solo sus turnos" (RN-CLI-07), pero es un eje distinto que se
  resuelve en el change dueño del recurso, no acá.

### D2 — Permisos efectivos en `SessionOut`, no en un endpoint aparte

`SessionOut` incorpora `permissions: list[str]`, calculado por `resolve_permissions(roles)` (unión de
las filas de `ROLE_PERMISSIONS` de las memberships activas del tenant) dentro de
`service.session_out`. Aplica a login, refresh, MFA, switch-tenant y `GET /auth/me` sin tocar el
token: el access JWT sigue llevando solo `sub`, `sid`, `tenant_id`, `mfa`, `iat`, `exp`.

Por qué esta opción y no `GET /api/v1/rbac/me`:

- El SPA ya tiene un único estado de sesión (`AuthProvider`) con un único `loading`; un endpoint
  aparte obliga a un segundo fetch, un segundo estado de carga y una ventana en la que hay sesión
  pero todavía no hay permisos (flicker de la pantalla de Equipo).
- Los permisos son **por tenant activo** (RN-TEN-05) y `SessionOut` ya es la respuesta tenant-scoped:
  `switch-tenant` los devuelve recalculados sin código extra.
- No duplica la lógica: `require_permission` y `SessionOut` usan la misma función pura y la misma
  matriz; no hay dos contratos que mantener sincronizados.

Trade-off aceptado: el SPA puede tener permisos "viejos" en memoria tras un cambio de rol hasta el
próximo `/auth/me`. La API **no** los usa (los recalcula por request desde `membership`), así que el
peor caso es un botón visible que devuelve `403`; el flujo de transferencia fuerza la
resincronización (D9).

- Alternativas: (a) permisos en el JWT → quedan obsoletos hasta 15 min y agrandan el token; (b)
  `GET /rbac/me` → descartado por el doble fetch y el flicker; (c) que el SPA derive permisos de
  `roles` con una copia de la matriz → prohibido por la regla dura (el SPA no replica la matriz) y
  sería una segunda fuente de verdad que se desincroniza en cada release.

### D3 — `require_permission` como dependencia y catálogo `RbacErrorCode`

`backend/app/domain/rbac/`:

- `errors.py`: `RbacErrorCode` con el catálogo y sus status, mismo shape `{"code", "message"}` que
  `AuthError`:

  | Status | `code` |
  |--------|--------|
  | `403` | `forbidden` |
  | `404` | `membership_not_found` |
  | `409` | `membership_exists`, `role_conflict`, `owner_must_be_transferred`, `last_owner`, `ownership_changed`, `member_inactive`, `member_is_actor`, `member_already_owner` |
  | `422` | `role_not_assignable`, `invalid_request` |
  | `501` | `capability_pending` |

  `role_conflict` es el choque del único `(tenant_id, user_id, rol)` en la transferencia (S5.6) y
  `invalid_request` unifica el rechazo del body que trae campos no declarados —incluido `tenant_id`—
  en los cinco endpoints (S7.4). Ninguno de los dos se inventa en runtime: el mapeo es una constante
  cubierta por `test_errors.py`.
- `guard.py`: `require_permission(*permissions)` devuelve una dependencia FastAPI que recibe
  `AuthContext = Depends(require_tenant)`, calcula `resolve_permissions(context.roles)` y, si falta
  alguno, lanza `RbacError(forbidden)`. Varios permisos se combinan con **AND** (todos), criterio
  explícito del endpoint; no hay OR implícito.

Reglas de uso: la cadena es siempre `require_auth` → `require_tenant` → `require_permission` (el
`Depends(require_tenant)` de la factory garantiza el orden), el `tenant_id` sale del contexto, y la
guarda corre **antes** de abrir cualquier escritura. No consulta la base: la matriz es pura y los
roles vienen del contexto ya validado bajo RLS.

El catálogo de C-03 no se toca: `AuthErrorCode` sigue manejando `401`/`403 mfa_required`/`423`. Se
agrega `forbidden` a `docs/auth.md` § 3.1 remitiendo a `docs/rbac.md`, y el `ApiError.code` del SPA
ya lo transporta sin cambios.

- Alternativas: (a) decorador con metadatos (`@Roles(...)`) → menos explícito en el OpenAPI y no
  corre como dependencia (no garantiza orden con `require_tenant`); (b) middleware global que
  mapee ruta→permiso → oculta la autorización del endpoint y complica los tests; (c) tabla de
  permisos en base de datos → permite customización por tenant que la KB no pide y agrega consulta
  por request.

### D4 — Fronteras duras: ausencia de permiso + endpoint sonda

La frontera no se implementa con un `if rol == front_desk`, sino con la **ausencia del permiso** en
la matriz, más tests negativos parametrizados por rol. Para probar la frontera por HTTP sin inventar
el dominio clínico:

- `GET /api/v1/clinical/patients` (router `api/v1/clinical`, `Depends(require_permission(
  Permission.clinical_record_read))`) es una **sonda reservada**: no consulta ni crea tablas y
  responde `501 {"code": "capability_pending"}` a quien tiene el permiso.
- `front_desk`, `billing`, `accountant` y `external_lab` reciben `403 forbidden` (nunca `200`, `404`
  ni `501`), y eso se prueba por HTTP con Postgres real.
- `assistant` recibe `403 forbidden` en una operación que exige `chart.finalize` (sonda equivalente
  o test directo del guard), mientras `professional` la satisface.
- El endpoint queda documentado como deuda hacia C-06: cuando exista `patient`, la sonda se
  reemplaza por el endpoint real con el mismo permiso y los mismos tests negativos.

- Alternativa: probar la frontera solo a nivel unitario del guard → no demuestra el rechazo HTTP que
  pide el criterio 3 ni protege contra un endpoint futuro que olvide la guarda; la sonda es barata y
  verificable por e2e.

### D5 — Migración `004_rbac`: `membership_event` append-only

No se modifica `membership` ni `user`: la unicidad de owner ya está garantizada por
`uq_membership_owner_activo` y la transferencia usa las columnas existentes. Lo único que falta es
la auditoría (RN-CMP-03).

```sql
CREATE TYPE membership_event_tipo AS ENUM (
  'member_created', 'member_reactivated', 'member_role_changed', 'member_deactivated',
  'ownership_transferred'
);

CREATE TABLE membership_event (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id      uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_user_id  uuid NULL REFERENCES "user"(id) ON DELETE SET NULL,
  target_user_id uuid NULL REFERENCES "user"(id) ON DELETE SET NULL,
  tipo           membership_event_tipo NOT NULL,
  detail         jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX membership_event_tenant_created_idx ON membership_event (tenant_id, created_at);

CREATE FUNCTION membership_event_forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF pg_trigger_depth() > 1 THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'membership_event is append-only' USING ERRCODE = '55000';
END;
$$;
REVOKE ALL ON FUNCTION membership_event_forbid_mutation() FROM PUBLIC;
CREATE TRIGGER membership_event_append_only
  BEFORE UPDATE OR DELETE ON membership_event
  FOR EACH ROW EXECUTE FUNCTION membership_event_forbid_mutation();

GRANT INSERT ON membership_event TO odontologia_app;
GRANT USAGE ON SEQUENCE membership_event_id_seq TO odontologia_app;

ALTER TABLE membership_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE membership_event FORCE ROW LEVEL SECURITY;
CREATE POLICY membership_event_tenant_insert ON membership_event
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
```

Detalles deliberados:

- `tenant_id NOT NULL` (es dato de negocio, no como `auth_event` que se escribe antes de resolver
  tenant) y RLS `FORCE`, porque la regla dura del proyecto lo exige para toda tabla con `tenant_id`.
- El rol de app solo tiene `INSERT`: no puede leer la auditoría ni siquiera con contexto. La
  política existe igual para que el `INSERT` tenga `WITH CHECK` y para que un futuro lector
  privilegiado (C-14) herede el aislamiento.
- `pg_trigger_depth() > 1` deja pasar el `UPDATE`/`DELETE` interno de las cascadas de FK: `user`
  (`ON DELETE SET NULL`) deja `actor_user_id`/`target_user_id` en `NULL`, y `tenant`
  (`ON DELETE CASCADE`) elimina los eventos del tenant. El DML directo falla con `55000` incluso para
  el superusuario (test).
- `down_revision = "003_auth"`. `downgrade` invierte el orden: trigger → función → tabla → tipo.

- Alternativa: reutilizar `auth_event` → mezcla eventos de autenticación con autorización y obliga a
  un enum ajeno; C-14 puede absorber ambas tablas después. Alternativa: `audit_log` de RN-CMP-03 →
  no existe todavía y C-14 es su dueño.

### D6 — Gestión de equipo: endpoints, DTOs y alta sin email

Router `api/v1/team` con `service.py` y `schemas/team.py` (Pydantic v2, `extra="forbid"`):

| Método | Ruta | Permiso | Éxito |
|---|---|---|---|
| GET | `/api/v1/team/members` | `team.read` | `200 MemberListOut` |
| POST | `/api/v1/team/members` | `team.create` | `201 MemberOut` |
| PATCH | `/api/v1/team/members/{membership_id}` | `team.update` | `200 MemberOut` |
| DELETE | `/api/v1/team/members/{membership_id}` | `team.delete` | `204` |
| POST | `/api/v1/team/ownership-transfer` | `ownership.transfer` | `200 MemberListOut` |

`MemberOut` = `{id, user_id, email, nombre, apellido, rol, activo, professional_id}`; el email puede
ser `null` (el `user` global lo permite) y `professional_id` es `null` hasta C-05. `MemberListOut` =
`{members: MemberOut[]}` — un objeto y no un array pelado, para poder agregar metadatos sin romper el
contrato.

Alta (`POST`):

1. Normalizar el email (minúsculas, `strip`) y validar `rol` contra `ASSIGNABLE_ROLES =
   {clinical_admin, professional, assistant, front_desk, billing, accountant}`; `owner` →
   `409 owner_must_be_transferred`; `patient`/`external_lab` → `422 role_not_assignable`.
2. Buscar el `user` por email (`user` es global y sin RLS; se lee con `SELECT` normal, sin bypass).
3. Si no existe: exigir `password_temporal` (mínimo 12, máximo 1024), crear el `user` con
   `hash_password` (Argon2id, misma función y parámetros de C-03). La contraseña **nunca** se
   devuelve ni se registra.
4. Crear la `membership` en el tenant del contexto, o **reactivar** la `membership` inactiva con el
   mismo `rol` si ya existe (`member_reactivated`): el único `(tenant_id, user_id, rol)` no es parcial,
   así que insertar una segunda fila violaría el constraint. El `INSERT` pasa por el `WITH CHECK` de
   RLS; un `tenant_id` del body se rechaza con `422` (`extra="forbid"`), contrato único para los cinco
   endpoints.
5. `INSERT` del `membership_event` `member_created` (o `member_reactivated`) con `detail = {"rol": …}`.
6. Commit único. Cualquier fallo revierte usuario, membership y evento.

La semántica "sin invitación" es deliberada: el owner comunica la contraseña temporal por fuera del
sistema y el usuario la cambia con el flujo de `reset-password` de C-03. Forzar el cambio en el
primer login requiere una columna nueva (`user.must_change_password`) que se deja como deuda
explícita para no tocar el contrato de auth en este change.

- Alternativas: (a) invitación con token de 7 días → bloqueada por PQ-08 (no hay proveedor
  transaccional) y el link tendría que entregarse a mano; (b) generar la contraseña y devolverla en
  el `201` → pone un secreto en un log de red y en el historial del navegador; (c) crear el usuario
  sin contraseña y exigir `forgot-password` → el usuario no puede entrar hasta que exista el email.

### D7 — Transferencia de ownership atómica y concurrencia

`POST /api/v1/team/ownership-transfer` con `{target_membership_id, previous_owner_role}`:

1. Validar `previous_owner_role ∈ ASSIGNABLE_ROLES` (excluye `owner`): si falta, viene `owner` o un rol
   de portal, `422` con `code = "role_not_assignable"` (validación explícita del servicio, no un error
   genérico de Pydantic, para que el contrato tenga un `code` estable).
2. Abrir transacción y **serializar por tenant**:
   `SELECT id FROM tenant WHERE id = :tid FOR UPDATE`. `tenant` no tiene RLS y la app tiene
   `SELECT`; el lock no lee datos de negocio.
3. Bajo el lock, revalidar que el actor tiene una `membership` `rol='owner' AND activo` en el
   tenant. Si ya no la tiene (perdió una carrera anterior) → `409 ownership_changed` y `rollback`.
4. Cargar el target con `SELECT … FOR UPDATE`: debe existir en el tenant (lo garantiza RLS), estar
   `activo`, ser distinto del actor y no ser `owner`. Errores: `membership_not_found` (404,
   indistinguible entre inexistente y de otro tenant), `member_inactive`, `member_is_actor`,
   `member_already_owner` (409).
5. `UPDATE membership SET rol = :previous_owner_role WHERE id = :actor_membership` **sin** tocar
   `activo`: el actor sigue activo con su rol nuevo (S5.1/S5.5 exige `403`, no `401`, en su siguiente
   request). El slot de `uq_membership_owner_activo` —índice **parcial** `rol='owner' AND activo`— se
   libera porque la fila deja de cumplir el predicado. `flush()` intermedio: el índice es inmediato y
   el orden no puede depender del identity map.
6. `UPDATE membership SET rol = 'owner' WHERE id = :target` — el destino ya estaba activo; el índice
   único parcial se satisface porque el paso 5 liberó el slot. Segundo `flush()`.
7. `INSERT membership_event` `ownership_transferred` con `detail = {rol_anterior, rol_nuevo,
   target_rol_anterior}`.
8. Leer la lista de miembros **dentro** de la transacción (después del commit el GUC
   `app.current_tenant` transaction-local se limpia y RLS devolvería cero filas), commit y devolver
   `MemberListOut`. Cualquier error → `rollback`: el owner original sigue activo y con su rol
   original (nunca cero owners).

Dos casos borde que el orden anterior no cubre, simétricos:

- **Lado actor (S5.6):** si el actor ya tiene **otra** membership activa con `previous_owner_role` en
  el tenant, el paso 5 viola `uq_membership_tenant_user_rol` (único no parcial). Antes del paso 5 se
  verifica `SELECT 1 FROM membership WHERE tenant_id = :tid AND user_id = :actor AND rol =
  :previous_owner_role AND id <> :actor_membership`; si existe → `409 role_conflict` y `rollback`, con
  el actor todavía owner.
- **Lado destino (S5.7):** si el target ya tiene **otra** membership (`owner`, típicamente inactiva)
  en el tenant, el paso 6 viola el mismo único. Antes del paso 5 se verifica
  `SELECT 1 FROM membership WHERE tenant_id = :tid AND user_id = :target_user AND rol = 'owner' AND
  id <> :target`; si existe → `409 role_conflict` y `rollback`.

Es el caso normal de un usuario multi-rol (RN-TEN-05), no un error del cliente.

Por qué funciona:

- El índice único parcial impide **dos** owners activos; la transacción impide **cero** porque la
  democión del actor y la promoción del destino son atómicas y el orden es "demover → promover". Un
  lector bajo `READ COMMITTED` no ve el estado intermedio.
- El lock de `tenant` serializa transferencias: la segunda espera, y al revalidar el actor ya no es
  owner → `409 ownership_changed`. Sin el lock, dos transacciones podrían pasar la validación y
  terminar con el "perdedor" desactivando al ganador (doble transferencia en cadena) o con un
  deadlock por orden de filas.
- `SELECT … FOR UPDATE` sobre target evita que un `DELETE`/`PATCH` concurrente lo desactive entre la
  validación y la promoción.

Self-demotion y último owner (RN-TEN-04): `PATCH` y `DELETE` sobre la propia membership `owner`
responden `409 last_owner` **antes** de escribir, porque el único camino legítimo para dejar de ser
owner es la transferencia (que promueve a otro en la misma transacción). El chequeo es "es el único
owner activo del tenant", no "es el actor": cubre también a un futuro segundo owner.

- Alternativas: (a) `SET CONSTRAINTS … DEFERRED` → el índice único **parcial** no es deferrable en
  PostgreSQL; (b) borrar el owner y crear otro → viola el soft delete y deja una ventana sin owner;
  (c) `advisory lock` por tenant → funciona, pero el lock de fila es más simple y no requiere
  manejar la liberación ante error.

### D8 — Auditoría: qué se registra y quién lee

| Operación | `tipo` | `detail` |
|---|---|---|
| Alta de miembro | `member_created` | `{rol}` |
| Readmisión de una membership inactiva | `member_reactivated` | `{rol}` |
| Cambio de rol | `member_role_changed` | `{rol_anterior, rol_nuevo}` |
| Baja lógica | `member_deactivated` | `{rol}` |
| Transferencia | `ownership_transferred` | `{rol_anterior, rol_nuevo, target_rol_anterior}` |

Nunca se registran contraseñas, hashes, secretos MFA ni datos clínicos. `actor_user_id` es el usuario
de la sesión; `target_user_id` el miembro afectado; `created_at` lo pone la base. No se registran los
intentos rechazados (los `401`/`403`/`404`/`409` no son mutaciones de RBAC; el rate limit y los logs
de acceso no son parte de RN-CMP-03 en este alcance).

Lectores: ninguno desde la aplicación (`odontologia_app` no tiene `SELECT`). Solo el superusuario de
migración y los tests. C-14 decidirá si `membership_event` se proyecta al `audit_log` definitivo o si
conviven, igual que se resolvió con `auth_event` en C-03 § 7.1.

Pruebas del append-only (Postgres real, `SET ROLE odontologia_app` para lo que corresponde): `UPDATE`
y `DELETE` directos fallan con `55000` incluso como superusuario; `odontologia_app` no puede hacer
`SELECT`; el `DELETE` de un `user` referenciado deja el evento con `target_user_id = NULL` y no falla.

### D9 — Frontend: guarda por permiso, pantalla de Equipo y rechazo visible

- `frontend/src/api/team.ts` y tipos derivados del OpenAPI (`MemberOut`, `MemberListOut`,
  `AssignMemberRequest`, `ChangeRoleRequest`, `TransferOwnershipRequest`), consumidos con
  `apiFetch` (ya maneja `401`/refresh y `ApiError.code`).
- `SessionOut` en `frontend/src/api/auth.ts` gana `permissions: string[]`; `AuthProvider` expone
  `hasPermission(permission)` y `reloadSession()` (GET `/auth/me`).
- `RequirePermission` (hijo de `RequireAuth`) recibe `permission`; si `status === 'authenticated'` y
  falta, renderiza `<Forbidden />` con el mensaje "No tenés permiso para ver esta sección" y el
  `code` cuando vino de la API. No redirige a `/login` (el usuario sí está autenticado: es un
  rechazo de autorización, no de sesión).
- Ruta `/equipo` protegida por `RequirePermission permission="team.read"`. La tabla muestra los
  miembros con `rol`, `activo` y acciones: cambiar rol (`team.update`), desactivar (`team.delete`) y
  transferir ownership (`ownership.transfer`), cada botón condicionado por su permiso.
- Home muestra el enlace "Equipo" solo si `hasPermission('team.read')`: es la evidencia visual del
  "acceso autorizado" vs. "rechazo" para el video.
- Tras una transferencia exitosa se llama `reloadSession()` para resincronizar roles y permisos del
  actor (D2) y se refresca la lista.
- **Prohibido** comparar `session.roles` contra literales para decidir visibilidad; un test de
  frontend lo verifica por barrido.

- Alternativa: guard por rol en el router → descartado por la regla dura y porque una ruta nueva
  repetiría el mapeo; alternativa: ocultar la ruta y dejar que el `403` del backend sea la única
  defensa → peor UX y no demuestra el rechazo en pantalla.

### D10 — e2e con backend real: seed de 4 roles y TOTP del owner

`npm run test:e2e` ya levanta Postgres + Redis con Testcontainers y uvicorn con el seed de C-03. Este
change extiende `backend/tests/fixtures/seed_auth_e2e.py` (o agrega `seed_team_e2e.py`):

- Tenant A `clinica-demo`: `owner@example.test` (owner, TOTP pre-enrolado con un secreto ficticio
  fijo), `admin@example.test` (clinical_admin), `profe@example.test` (professional) y
  `recepcion@example.test` (front_desk), todos con la misma contraseña ficticia del e2e.
- Tenant B `clinica-demo-b`: un miembro con email distinto, para el caso cross-tenant.
- El owner nace con `mfa_enrolled_at` y `mfa_secret` cifrado con la misma clave ficticia del
  entorno de test; el spec calcula el TOTP con un helper de ~20 líneas sobre `node:crypto` (HMAC-
  SHA1, paso de 30 s) — sin agregar dependencia de producción.

Casos e2e (Playwright): (1) `front_desk` inicia sesión, no ve el enlace Equipo y al navegar a
`/equipo` ve la pantalla de acceso denegado; (2) `front_desk` fuerza
`GET /api/v1/team/members` por `request` y obtiene `403 forbidden`; (3) `owner` con TOTP ve la lista,
cambia un rol y la UI refleja el cambio; (4) `clinical_admin` ve la lista pero no los botones de
gestión. La transferencia de ownership se prueba en integración (no en e2e) para no dejar el seed
mutado entre tests.

- Alternativa: usar solo `professional` como hoy → no se puede demostrar la pantalla de Equipo ni el
  botón de gestión, que es el objetivo del criterio 3.

### D11 — Estrategia de tests (Strict TDD, Postgres real)

- **Unitarios sin DB**: matriz parametrizada 9 × 18, unión de roles, fail-closed de valores
  desconocidos, `resolve_permissions` y el guard (con `AuthContext` construido a mano y un endpoint
  de prueba en la app de test).
- **Integración con Testcontainers** (`SET ROLE odontologia_app` para todo lo que prueba RLS): CRUD
  de equipo, errores `403/404/409/422`, auditoría, transferencia y concurrencia (dos conexiones con
  `threading.Barrier`), aislamiento cross-tenant con prueba de mutación (desactivar la política y
  ver el test fallar).
- **Frontend**: Vitest para `hasPermission`, `RequirePermission`, `Forbidden` y el mapeo de
  `ApiError.code`; barrido que prohíbe comparaciones de rol.
- **e2e**: D10.

## Risks / Trade-offs

- **[Deriva entre la matriz y la KB]** Si la KB cambia y la matriz no, el producto autoriza de más o
  de menos. → Mitigación: `RESOURCE_ACTIONS` es una transcripción independiente y el test de
  fidelidad falla ante cualquier divergencia; el change que agregue un recurso debe actualizar ambas.
- **[Permisos viejos en el SPA]** Tras un cambio de rol o una transferencia, el SPA puede mostrar
  acciones que la API rechaza. → Mitigación: la API siempre recalcula; `reloadSession()` tras
  transferencia; el `403` se muestra como error de catálogo, no como pantalla rota.
- **[`403` vs `404` y enumeración]** Un `403` no revela si el recurso existe, pero un `404` de
  membership sí insinúa. → Mitigación: el `404` se devuelve solo para ids del propio tenant (RLS ya
  oculta los ajenos) y es idéntico para un id inexistente; el `403` de permiso se evalúa antes de
  cualquier lectura.
- **[Owner con MFA en el e2e]** El flujo de gestión exige owner, y owner exige TOTP (RN-AU-04). →
  Mitigación: secreto ficticio fijo en el seed de test y helper TOTP en el spec; el secret nunca
  sale del entorno de test y no hay secretos reales en el repo.
- **[Contraseña temporal sin cambio forzado]** El usuario creado puede quedarse con la temporal. →
  Trade-off aceptado y declarado: agregar `must_change_password` toca el contrato de C-03; se
  documenta la deuda y el owner puede forzar el cambio con `reset-password`.
- **[`membership_event` sin lector]** Hasta C-14 la auditoría no es consultable por la app. →
  Trade-off aceptado: RN-CMP-03 pide registrar, no exponer; la tabla queda lista para que C-14 la
  proyecte.
- **[Alta de usuarios en tabla global]** `odontologia_app` puede insertar en `user`, que no tiene
  RLS. → Mitigación: el endpoint solo escribe un `user` nuevo cuando el email no existe, valida el
  rol asignable y nunca modifica el `password_hash` de un usuario existente; el test de cross-tenant
  verifica que un usuario de B no se da de baja ni cambia de rol en B.
- **[Listar memberships inactivas]** La lista incluye emails de usuarios dados de baja. → Mitigación:
  solo `team.read` (owner, clinical_admin, billing) accede; no se expone el motivo de la baja ni
  datos de otro tenant; el requisito de privacidad fina por campo queda para C-14.
- **[`professional_id` nullable]** Asignar `professional` sin vínculo al profesional. → Deuda
  explícita de C-05: la FK y la validación llegan con el modelo `professional`; hoy la membership
  queda con `professional_id = NULL`.
- **[Lock de `tenant` bajo carga]** La transferencia serializa por tenant; con muchas transferencias
  simultáneas hay contención. → Aceptable: es una operación rarísima (una por cambio de dueño) y la
  contención es por tenant, no global.

## Migration Plan

1. `alembic upgrade head` aplica `004_rbac` sobre `003_auth`: crea el tipo, la tabla, el índice, la
   función y el trigger, los grants y la política RLS. Test de migración verifica cada objeto.
2. Ciclo `downgrade 003_auth` → `upgrade head` en un contenedor propio (el `DROP TYPE`/función no
   debe chocar con otras bases del clúster).
3. Deploy: migración → backend → frontend. Sin backfill: `membership_event` nace vacía y las
   memberships existentes no cambian.
4. Rollback: `alembic downgrade 003_auth` y `git revert` del change. Los permisos dejan de
   proyectarse en `SessionOut`; las sesiones siguen siendo válidas porque el token no guarda
   permisos.
5. Seed de e2e (D10) se re-ejecuta de forma idempotente antes de Playwright.

## Open Questions

- **PQ-08 (proveedor de email)**: mientras no se resuelva, no hay invitaciones con expiración ni
  entrega automática de credenciales. El alta actual es funcional y suficiente para el TPI; cuando
  PQ-08 se cierre, el endpoint de alta puede pasar a emitir una invitación sin cambiar la matriz ni
  el guard.
- **`user.must_change_password`**: se evalúa en C-08/C-14 junto con el flujo de cambio de contraseña
  obligatorio. No altera los requisitos de este change.
- **Flag por tenant `billing.can_read_clinical`**: la restricción horizontal 3 lo menciona; este
  change lo deja en `false` fijo y lo modela cuando exista configuración de tenant (C-09).
- **Absorción de `membership_event` por `audit_log` (C-14)**: se decide allí; el formato de
  `detail` ya es compatible con una proyección.
