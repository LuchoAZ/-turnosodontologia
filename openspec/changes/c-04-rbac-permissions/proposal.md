# Proposal

## Why

C-03 autenticó usuarios y resolvió el tenant activo, pero **no autoriza nada**: los roles viajan en
la sesión y ningún endpoint decide si el usuario puede ejecutar la operación. Sin RBAC no se puede
demostrar el criterio 3 del TPI ("autenticación y permisos: login, acceso autorizado y **rechazo de
accesos inválidos**) ni cerrar la invariante pendiente de RN-TEN-04 que C-02 delegó explícitamente a
este change (nunca cero owners).

Vale la pena ahora porque todo change posterior (C-05 agenda, C-06 pacientes, C-07 turnos, C-14
facturación) necesita una única tabla de permisos y un guard reutilizable; si cada slice inventa su
chequeo, las fronteras duras de `knowledge-base/03_actores_y_roles.md` § Restricciones horizontales
quedan a criterio de la UI.

## What Changes

- **Matriz de permisos centralizada** (`backend/app/domain/rbac/matrix.py`): 18 recursos × 9 roles
  declarados como constantes, derivados de `03_actores_y_roles.md` § RBAC — Matriz de permisos y de
  las 7 restricciones horizontales. Permisos atómicos con namespace `recurso.accion`
  (`team.read`, `clinical_record.read`, `chart.finalize`, `ownership.transfer`, …). Ningún endpoint
  ni pantalla compara roles a mano.
- **Guard HTTP `require_permission`** en la cadena `require_auth` → `require_tenant` →
  `require_permission`, con `403 forbidden` y `code` estable en el catálogo de errores de
  autorización.
- **Permisos efectivos en el contrato de sesión**: `SessionOut` incorpora `permissions[]` calculado
  desde las memberships activas del tenant de la sesión (unión de roles, RN-TEN-05). El SPA conmuta
  por permiso y no replica la matriz.
- **Gestión de equipo tenant-scoped** (`/api/v1/team/**`, bajo RLS): listar miembros
  (`team.read`), alta de miembro con rol (`team.create`), cambio de rol (`team.update`) y baja
  lógica (`team.delete`). El alta resuelve el `user` por email y lo crea con contraseña temporal si
  no existe; **no hay invitaciones por email** (bloqueadas por PQ-08, sin proveedor transaccional).
- **Transferencia atómica de ownership** (`POST /api/v1/team/ownership-transfer`,
  `ownership.transfer`): en una sola transacción se desactiva el owner actual y se promueve el
  destino. Nunca hay cero owners ni dos owners; dos transferencias concurrentes no pueden ganar
  ambas (RN-TEN-04).
- **Migración `004_rbac`**: tabla `membership_event` append-only para auditoría de cambios sensibles
  de RBAC (RN-CMP-03), con el patrón ya probado en `auth_event` (sin `SELECT` para el rol de app,
  trigger que rechaza `UPDATE`/`DELETE` directo con SQLSTATE `55000` y deja pasar el `UPDATE` interno
  de cascadas de FK vía `pg_trigger_depth() > 1`).
- **UI mínima de Equipo** en el SPA (vertical slice): listar miembros, cambiar rol, desactivar y
  transferir ownership, con guarda por permiso. Un rol sin `team.read` no ve la pantalla y recibe
  `403 forbidden` si fuerza la llamada.
- **Endpoint sonda de frontera clínica** `GET /api/v1/clinical/patients`: reservado por
  `clinical_record.read`, sin tablas ni datos clínicos, responde `403 forbidden` a los roles sin
  permiso y `501 capability_pending` a los que sí lo tienen. Es la prueba HTTP de que la
  recepcionista no lee historia clínica (RN-CMP-04) y queda como deuda explícita hasta C-06.

**Fuera de alcance (explícito)**: invitaciones con expiración de 7 días y aceptación por email
(PQ-08), los 5 roles que no participan del flujo (`assistant`, `billing`, `patient`, `external_lab`,
`accountant`) ejercitados por HTTP, enforcement de los permisos de recursos que todavía no existen
(clínica, facturación, caja), flags por tenant (`billing.can_read_clinical`), `audit_log` definitivo
(C-14), portal del paciente y MFA de los endpoints de equipo más allá de lo que ya exige C-03.

## Capabilities

### New Capabilities

- `platform-rbac`: catálogo de permisos atómicos y matriz rol→permiso, cadena de guardas con
  `403 forbidden`, fronteras duras (RN-CMP-04) y proyección de permisos efectivos del tenant activo.
- `platform-team`: administración de memberships del tenant (lectura, alta, cambio de rol y baja) y
  transferencia atómica de ownership (RN-TEN-04) con auditoría append-only en `membership_event`.

### Modified Capabilities

- `platform-auth`: el contrato de `GET /api/v1/auth/me` (y de todo `SessionOut`) incorpora
  `permissions[]` como permisos efectivos del tenant activo. La sesión, el refresh y el tenant del
  token no cambian.

## Impact

- **Backend** (`backend/app`): nuevo paquete `domain/rbac/` (matriz, resolución de permisos, errores)
  y `domain/team/` (servicio de memberships y ownership); dependencia `require_permission` en
  `api/v1/deps.py`; routers `/api/v1/team` y `/api/v1/clinical`; `SessionOut.permissions` en
  `schemas/auth.py` y `domain/auth/service.py`.
- **Base de datos**: migración `004_rbac` (`membership_event`, RLS `FORCE`, trigger append-only,
  grants mínimos). No altera `membership` ni `user`.
- **Frontend** (`frontend/src`): `api/rbac.ts` y `api/team.ts`; `RequirePermission` y `Forbidden`;
  ruta `/equipo` con tabla de miembros y acciones por permiso; navegación condicionada.
- **Tests**: unitarios parametrizados de la matriz completa (9 × 18, sin DB), integración con
  Postgres real (Testcontainers) de guards, equipo, ownership y aislamiento cross-tenant (gate
  RN-TEN-02), y e2e Playwright del acceso autorizado y del rechazo.
- **Dependencias**: C-01, C-02 y C-03 (archivados). **Habilitá** a C-05…C-14: cada uno solo declara
  qué permiso exige su endpoint.
- **Deuda declarada**: US-005 se cubre parcialmente (sin email, sin aceptación de invitación);
  `GET /api/v1/clinical/patients` es una sonda sin dominio hasta C-06; `membership.professional_id`
  sigue nullable hasta C-05; `user.must_change_password` no se agrega.
