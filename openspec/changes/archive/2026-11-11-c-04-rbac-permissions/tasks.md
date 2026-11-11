# Tasks

> **Prerrequisitos (no son tasks de este change)**: C-01, C-02 y C-03 archivados — `Role` con 9
> valores, `Membership` con RLS `FORCE`, `set_tenant_context`, `AuthContext` con `roles`,
> `SessionOut` y catálogo de `AuthErrorCode`. Este change no implementa dominio clínico,
> administrativo ni de facturación: solo declara sus permisos.
>
> **Regla de trabajo**: Strict TDD. Cada tarea `RED` escribe primero el test que falla y lo confirma
> en rojo antes de la `GREEN`. Los tests de todo lo que toca tablas con `tenant_id` corren con
> Postgres real (Testcontainers) y `SET ROLE odontologia_app` (el superusuario ignora RLS).

## 1. Matriz de permisos y resolución (puro, sin base de datos)

- [x] 1.1 RED: escribir en `backend/tests/unit/rbac/test_matrix.py` el test de fidelidad que
  parametriza los 9 roles × 18 recursos contra una transcripción literal de
  `knowledge-base/03_actores_y_roles.md` líneas 33-48 (letras `C R U D` y `—`), más los casos de los
  accesos propios (`_own`: 8 del paciente + `settlement.read_own` del odontólogo) y de las 7
  restricciones horizontales. Verificar que falla
  (no existe el módulo).
- [x] 1.2 GREEN: crear `backend/app/domain/rbac/matrix.py` con `Permission` (StrEnum),
  `ROLE_PERMISSIONS: dict[Role, frozenset[Permission]]` y `RESOURCE_ACTIONS` (18 recursos, con
  "Usuarios y roles" desdoblado en `team` + `ownership` y el recurso `membership_event` sin
  titulares), aplicando las excepciones horizontales documentadas en design D1. Verificación:
  `cd backend && uv run pytest tests/unit/rbac -q` en verde y `uv run mypy app` sin errores.
- [x] 1.3 RED→GREEN: escribir los unitarios de `resolve_permissions(roles)` — unión de dos
  memberships (`professional` + `clinical_admin`), lista vacía → conjunto vacío, rol repetido sin
  duplicados, orden estable; implementar la función pura. Verificación: los 4 casos pasan y
  `front_desk` no obtiene `clinical_record.read`.
- [x] 1.4 RED→GREEN: escribir el unitario de fail-closed para un rol o permiso fuera del catálogo
  (string inventado) y para una clave ausente en la matriz; la resolución debe devolver conjunto
  vacío o error de dominio, nunca "todo permitido". Verificación: el test falla si se agrega un
  `default allow` y pasa con el comportamiento cerrado.

## 2. Catálogo de errores, guard HTTP y proyección en la sesión

- [x] 2.1 RED: escribir en `backend/tests/unit/rbac/test_errors.py` el contrato de
  `RbacErrorCode`/`RBAC_ERROR_STATUS` (`forbidden` 403, `membership_not_found` 404,
  `capability_pending` 501, `last_owner`/`ownership_changed`/`member_inactive`/`member_is_actor`/
  `member_already_owner`/`owner_must_be_transferred`/`membership_exists`/`role_conflict` 409,
  `role_not_assignable`/`invalid_request` 422) y que el payload nunca incluya datos del recurso.
  Verificar que falla.
- [x] 2.2 GREEN: crear `backend/app/domain/rbac/errors.py` con el catálogo y los mensajes en
  español rioplatense, y en `app/main.py` dos handlers que serialicen `{"code", "message"}`:
  `RbacError` para los `code` del catálogo y `RequestValidationError` → `422 invalid_request` (campos
  extra por `extra="forbid"`, `password_temporal` corta, tipos inválidos), de modo que un `422` nunca
  salga con el shape `detail` de FastAPI. Verificación: los unitarios de 2.1 pasan por HTTP, no solo
  por construcción del objeto.
- [x] 2.3 RED: escribir en `backend/tests/unit/rbac/test_guard.py` los casos del guard
  parametrizados por `(rol, permiso)`: permiso presente → endpoint de prueba `200`; permiso ausente →
  `403 forbidden`; varios permisos exigen todos (AND); `403` antes de ejecutar el handler (un contador
  de invocaciones queda en 0); la guarda corre después de `require_tenant`; y la fila explícita
  `billing` + `clinical_record.update` y `assistant` + `chart.finalize` → `403`. Verificar que falla.
- [x] 2.4 GREEN: crear `backend/app/domain/rbac/guard.py` con `require_permission(*permissions)`
  (dependencia sobre `Depends(require_tenant)`, resolución pura sin DB). Verificación: 2.3 en verde.
- [x] 2.5 RED→GREEN: extender `SessionOut` con `permissions: list[str]` y `service.session_out`
  para calcularlo con `resolve_permissions`; escribir antes los tests de login, `/auth/me`,
  `switch-tenant` y refresh que comparan `permissions` con la matriz del rol activo (incluido el
  caso de memberships en A y B con permisos distintos). Verificación:
  `uv run pytest tests/integration/test_auth_sessions.py tests/integration/test_auth_switch_tenant.py -q`
  en verde y el JSON sin `password_hash`, `mfa_secret` ni tokens.
- [x] 2.6 RED→GREEN: escribir el caso de recálculo sin re-login (cambiar el rol por SQL y verificar
  que el siguiente `/auth/me` devuelve los permisos nuevos) y el de campo `permissions`/`roles`
  enviado en el body del login (se ignora o se rechaza por DTO). Verificación: ambos pasan por HTTP.
- [x] 2.7 Documentar en `docs/auth.md` § 3.1 el `code` `forbidden` y el campo `permissions` del
  `SessionOut`, con referencia a `docs/rbac.md`. Verificación: el catálogo del documento coincide con
  `RbacErrorCode` (test de barrido que compara las tablas del doc con el enum).

## 3. Fronteras duras clínicas (RN-CMP-04)

- [x] 3.1 RED: escribir `backend/tests/integration/test_rbac_clinical_boundary.py`: `front_desk`,
  `billing`, `accountant` y `external_lab` reciben `403 forbidden` en
  `GET /api/v1/clinical/patients`; `professional` y `clinical_admin` y `owner` reciben `501
  capability_pending`; `assistant` recibe `403` en una operación que exige `chart.finalize` y
  `billing` recibe `403` en otra que exige `clinical_record.update` (S3.5). Sembrar un tenant con los
  roles y verificar que falla (no existe el endpoint).
- [x] 3.2 GREEN: crear el router `backend/app/api/v1/clinical/router.py` con la sonda
  `GET /api/v1/clinical/patients` (`Depends(require_permission(Permission.clinical_record_read))`)
  que responde `501 capability_pending` sin tocar tablas, y registrarlo en la app. Verificación:
  3.1 en verde con Postgres real.
- [x] 3.3 RED→GREEN: escribir el test de unión de roles que acumula `front_desk` + `billing` +
  `accountant` + `external_lab` y confirma que la unión sigue sin `clinical_record.read` ni
  `chart.read`, y el caso inverso con `professional` incluido (la lectura viene de esa membership).
  Verificación: ambos casos pasan y documentan en el test por qué la frontera es por permiso y no por
  rol.
- [x] 3.4 Anotar la deuda en `docs/rbac.md` § Fronteras duras: la sonda se reemplaza por el endpoint
  real en C-06 con el mismo permiso y los mismos tests negativos. Verificación: el documento menciona
  C-06 y el permiso exacto.

## 4. Migración `004_rbac` — auditoría append-only

- [x] 4.1 RED: escribir `backend/tests/integration/test_membership_event_migration.py` que exige:
  tipo `membership_event_tipo` con 5 valores (`member_created`, `member_reactivated`,
  `member_role_changed`, `member_deactivated`, `ownership_transferred`), tabla `membership_event` con
  `tenant_id NOT NULL`,
  `actor_user_id`/`target_user_id` nullable con FK `ON DELETE SET NULL`, `detail jsonb`, índice
  `(tenant_id, created_at)`, RLS `ENABLE` + `FORCE`, política con `NULLIF(current_setting(...))`,
  `INSERT` para `odontologia_app` y **sin** `SELECT`, trigger append-only. Verificar que falla.
- [x] 4.2 GREEN: crear `backend/alembic/versions/004_rbac.py` (`down_revision = "003_auth"`) con el
  DDL de design D5 en el orden tipo → tabla → índice → función → trigger → grants → RLS, y
  `downgrade` inverso. Verificación: 4.1 en verde con `alembic upgrade head` sobre Postgres real.
- [x] 4.3 RED→GREEN: escribir el test de reversibilidad en contenedor propio
  (`upgrade head` → `downgrade 003_auth` → `upgrade head`) y el test de que `odontologia_app` no
  puede hacer `SELECT` sobre `membership_event` con ni sin contexto. Verificación: ambos pasan y el
  `downgrade` no deja tipo, tabla, función ni política.
- [x] 4.4 RED→GREEN: escribir el test de append-only real: `UPDATE` y `DELETE` directos fallan con
  SQLSTATE `55000` incluso como superusuario; el `DELETE` de un `user` referenciado deja
  `target_user_id = NULL` sin error (cascada vía `pg_trigger_depth() > 1`). Verificación: los tres
  casos pasan con Postgres real.

## 5. Equipo — lectura de miembros

- [x] 5.1 RED: escribir `backend/tests/integration/test_team_members_read.py`: owner,
  `clinical_admin` y `billing` reciben `200` con las memberships del tenant (activas e inactivas,
  con `rol`, `activo`, email y nombre); `professional` y `front_desk` reciben `403 forbidden`; el
  JSON no incluye `password_hash`, `mfa_secret`, `tenant_id` ni `permissions`; el orden es estable
  entre llamadas. Verificar que falla.
- [x] 5.2 GREEN: crear `backend/app/schemas/team.py` (`MemberOut`, `MemberListOut`) y
  `backend/app/domain/team/service.py` + `api/v1/team/router.py` con `GET /api/v1/team/members`
  (`require_permission(Permission.team_read)`), leyendo `Membership` bajo el contexto de RLS. Sin
  `tenant_id` en el DTO. Verificación: 5.1 en verde.
- [x] 5.3 RED→GREEN: escribir el caso de una membership inactiva que aparece con `activo: false` y
  no cuenta para la invariante de owner (dos filas `owner`, una inactiva), y el caso de tenant sin
  miembros salvo el actor (`200` con un solo elemento). Verificación: ambos pasan.
- [x] 5.4 Documentar `GET /api/v1/team/members` en `docs/rbac.md` (contrato, permiso, ejemplo de
  respuesta sin PII sensible). Verificación: el ejemplo documentado coincide con el `MemberOut`
  real (test de contrato que compara las claves del OpenAPI con las del doc).

## 6. Equipo — alta de miembro con rol (sin email)

- [x] 6.1 RED: escribir `backend/tests/integration/test_team_members_create.py`: alta de usuario
  existente → `201` + `member_created`; usuario inexistente con `password_temporal` → `201`, `user`
  creado con Argon2id y contraseña ausente de la respuesta y del evento; `rol: "owner"` → `409
  owner_must_be_transferred`; `rol: "patient"`/`"external_lab"` → `422 role_not_assignable`;
  membership duplicada → `409 membership_exists`; actor sin `team.create` → `403 forbidden`. Ocho
  casos (los dos roles de portal cuentan por separado), todos fallando.
- [x] 6.2 GREEN: implementar `POST /api/v1/team/members` con `AssignMemberRequest` (`email`, `rol`,
  `password_temporal` opcional, `extra="forbid"`), normalización de email, `ASSIGNABLE_ROLES`,
  creación opcional del `user` con `hash_password` de C-03 y transacción única con el evento.
  Verificación: 6.1 en verde y `uv run mypy app` sin errores.
- [x] 6.3 RED→GREEN: escribir los casos de atomicidad y borde: si el evento o la membership falla,
  no queda `user` huérfano (rollback completo); un `user` con membership activa en otro tenant
  recibe una membership nueva solo en el tenant de la sesión, sin cambiar su rol ni su
  `password_hash` en el otro; `password_temporal` ausente con email inexistente o de menos de 12
  caracteres → `422` sin crear `user` (S2.8); readmisión de una membership `activo: false` con el
  mismo rol → reactiva la fila existente, `201` y un único `member_reactivated` sin `member_created`
  (S2.7). Verificación: los cuatro pasan con dos tenants sembrados.
- [x] 6.4 Documentar el alta y la semántica "sin invitación" (PQ-08) en `docs/rbac.md`, incluida la
  contraseña temporal y la deuda de `user.must_change_password`. Verificación: el documento explica
  quién puede crear y qué no devuelve la respuesta.

## 7. Equipo — cambio de rol y baja lógica

- [x] 7.1 RED: escribir `backend/tests/integration/test_team_members_update.py`: cambio
  `professional` → `clinical_admin` → `200` + `member_role_changed` con roles anterior y nuevo;
  autodemoción del único owner → `409 last_owner` sin cambios ni evento; membership de otro tenant →
  `404 membership_not_found`; mismo rol → `200` idempotente sin evento nuevo; rol destino que el
  usuario ya tiene en otra membership → `409 membership_exists` sin tocar ninguna fila (S3.6);
  `rol: "owner"` → `409 owner_must_be_transferred` y `patient`/`external_lab` →
  `422 role_not_assignable`, con el tenant conservando un solo owner activo (S3.7); actor sin
  `team.update` → `403 forbidden`. Verificar que falla.
- [x] 7.2 GREEN: implementar `PATCH /api/v1/team/members/{membership_id}` con
  `ChangeRoleRequest`, validación de rol asignable, chequeo de "único owner activo" antes de
  escribir y evento en la misma transacción. Verificación: 7.1 en verde.
- [x] 7.3 RED: escribir `backend/tests/integration/test_team_members_deactivate.py`: baja de una
  membership activa → `204`, `activo: false` y `member_deactivated`, y el siguiente request del
  usuario dado de baja responde `401 not_authenticated`; autobaja del único owner → `409 last_owner`;
  segunda baja → `204` sin segundo evento; actor sin `team.delete` → `403 forbidden`. Verificar que
  falla.
- [x] 7.4 GREEN: implementar `DELETE /api/v1/team/members/{membership_id}` con baja lógica
  idempotente, guardas de último owner y evento condicional. Verificación: 7.3 en verde.
- [x] 7.5 Documentar `PATCH` y `DELETE` (errores `last_owner`, `membership_not_found`,
  idempotencia) en `docs/rbac.md`. Verificación: las tablas del doc coinciden con los `code` del
  catálogo.

## 8. Transferencia atómica de ownership (RN-TEN-04)

- [x] 8.1 RED: escribir `backend/tests/integration/test_team_ownership_transfer.py`: transferencia
  exitosa → `200`, destino `owner` activo, actor con `previous_owner_role`, exactamente un owner
  activo y evento `ownership_transferred`; destino inactivo → `409 member_inactive`, al propio actor
  → `409 member_is_actor`, ya owner → `409 member_already_owner`; destino inexistente **y** destino
  de otro tenant → `404 membership_not_found` con el mismo body (S5.2b); `previous_owner_role` ausente
  o `= owner` → `422 role_not_assignable`; actor que ya tiene otra membership con el rol de destino →
  `409 role_conflict` con rollback, actor sigue owner y `count(*)` de owners activos = 1 (S5.6);
  destino que ya tiene otra membership `owner` inactiva → `409 role_conflict` con rollback y el target
  conserva su rol (S5.7); actor sin `ownership.transfer` → `403 forbidden`. Verificar que falla.
- [x] 8.2 GREEN: implementar `POST /api/v1/team/ownership-transfer` con el flujo de design D7
  (`SELECT … FROM tenant WHERE id = :tid FOR UPDATE`, revalidación del actor, `SELECT … FOR UPDATE`
  del target, los dos chequeos `role_conflict` —lado actor y lado destino—, demover al actor **sin
  darlo de baja** (`rol = previous_owner_role`, `activo` intacto), promover al target, evento) en una
  sola transacción. El DTO declara
  `previous_owner_role: str | None` (opcional) y la validación de pertenencia a `ASSIGNABLE_ROLES`
  vive en el servicio, para que falte o venga `owner` responda `422 role_not_assignable` y no el
  shape `detail` de Pydantic. Verificación: 8.1 en verde.
- [x] 8.3 RED→GREEN: escribir el test de concurrencia con dos conexiones y `threading.Barrier`: dos
  transferencias simultáneas del mismo tenant → exactamente una `200` y una `409
  ownership_changed`; después de ambas, `count(*)` de owners activos = 1; durante todo el test nunca
  se observa 0 owners (consulta posterior al commit de cada transacción); y en el camino de error de
  S5.6 (`role_conflict`) el `rollback` deja el conteo de owners activos en 1. Verificación: el test
  pasa repetidamente (correr 20 veces en el grupo) sin quedar flaky.
- [x] 8.4 RED→GREEN: escribir el test de permisos post-transferencia: el actor consulta
  `/auth/me`, ya no tiene `ownership.transfer` ni `team.update`, y un nuevo intento de transferencia
  responde `403 forbidden`; el destino sí tiene `ownership.transfer` y puede revertir la
  transferencia en un segundo movimiento. Verificación: ambos pasan por HTTP.
- [x] 8.5 Documentar en `docs/rbac.md` § Ownership la invariante, el lock, los `code` de error y el
  ejemplo de transferencia exitosa. Verificación: el documento cita RN-TEN-04 y el flujo del design.

## 9. Gate de aislamiento cross-tenant (RN-TEN-02) — bloqueante de merge

- [x] 9.1a Escribir `backend/tests/integration/test_team_rls.py` (nivel SQL) como gate obligatorio, con
  dos tenants sembrados y `SET ROLE odontologia_app`: (a) A nunca ve memberships ni emails de B; (b)
  `PATCH`/`DELETE` con `membership_id` de B no modifica filas de B; (c) sin contexto, `SELECT` de
  `membership` devuelve 0 filas (fail-closed) y un `INSERT` con `tenant_id` ajeno es rechazado por la
  política; (d) sobre `membership_event`, `odontologia_app` recibe **error de permisos** (no tiene
  `SELECT`), nunca filas ni 0 filas silencioso. Verificación: los cuatro casos pasan.
- [x] 9.1b Escribir el gate a nivel HTTP con la **app conectada como `odontologia_app`** (listener de
  SQLAlchemy que hace `SET ROLE`, o engine propio del rol, no el superusuario del contenedor): A
  pidiendo `GET /team/members` no recibe datos de B; `PATCH`/`DELETE` con id de B → `404`; y
  `tenant_id` (o cualquier campo no declarado) en el **body** de los cinco endpoints → `422` con
  `code = "invalid_request"` antes de tocar la base, mientras que en query/header se ignora
  (S7.4); y con un actor **sin permiso** que además manda un body inválido, la respuesta es `403`
  (la guarda corre antes de la validación del body). Verificación: los cuatro pasan y el test falla si
  el engine del test corre como superusuario (chequeo explícito de `current_user` =
  `odontologia_app`).
- [x] 9.2 Prueba de mutación con receta explícita: `ALTER TABLE membership DISABLE ROW LEVEL
  SECURITY` (y luego `ENABLE`/`FORCE` en el `finally`) o comparación superusuario vs.
  `SET ROLE odontologia_app`; nunca `DROP POLICY`. Comprobar que 9.1a **falla** con RLS desactivada y
  vuelve a verde al restaurarla. Verificación: el rojo de la mutación queda registrado en la salida del
  comando y el verde final también; `cross-tenant leak = 0`.

## 10. Frontend — permisos, guarda y pantalla de Equipo

- [x] 10.1 RED: escribir en `frontend/src/features/auth/*.test.tsx` los casos de `hasPermission`
  (permiso presente/ausente, sesión anulada) y de `RequirePermission` (con permiso renderiza,
  sin permiso renderiza `Forbidden`, sin sesión delega en `RequireAuth`). Verificar que `npm run
  test` falla.
- [x] 10.2 GREEN: extender `frontend/src/api/auth.ts` con `permissions: string[]`, `AuthProvider`
  con `hasPermission` y `reloadSession`, y crear `RequirePermission.tsx` + `Forbidden.tsx`
  (muestra el `code` cuando viene de la API). Verificación: 10.1 en verde y `npm run typecheck`.
- [x] 10.3 RED→GREEN: escribir los tests de `frontend/src/features/team` con `apiFetch` mockeado:
  lista de miembros, botón de cambio de rol visible solo con `team.update`, desactivar solo con
  `team.delete`, transferir solo con `ownership.transfer`, y `403 forbidden` de la API mapeado a la
  pantalla de acceso denegado. Implementar `api/team.ts`, la ruta `/equipo` en `App.tsx` y la página
  con shadcn/ui. Verificación: `npm run test` en verde y `npm run lint` sin errores nuevos.
- [x] 10.4 RED→GREEN: escribir el barrido que falla si aparece una comparación de `session.roles`
  contra literales (`owner`, `clinical_admin`, `professional`, `front_desk`) para decidir
  visibilidad, y el test de que Home solo muestra el enlace Equipo con `team.read`. Verificación: el
  barrido pasa y el enlace se oculta al simular un rol sin permiso.

## 11. e2e con backend real

- [x] 11.1 Extender el seed de e2e (`backend/tests/fixtures/seed_auth_e2e.py` o
  `seed_team_e2e.py`) con los 4 usuarios del flujo en `clinica-demo`, un miembro en
  `clinica-demo-b` y el owner con TOTP pre-enrolado y secreto ficticio fijo; idempotente. Verificación:
  correr el seed dos veces deja los mismos ids y no duplica memberships.
- [x] 11.2 RED→GREEN: escribir `frontend/tests/e2e/team.spec.ts` con el helper TOTP (`node:crypto`):
  `front_desk` inicia sesión, no ve el enlace Equipo y en `/equipo` ve "No tenés permiso para ver
  esta sección"; `front_desk` fuerza `GET /api/v1/team/members` y recibe `403 forbidden`; `owner`
  con TOTP ve la lista y cambia un rol con la UI reflejando el cambio; `clinical_admin` ve la lista
  pero no los botones de gestión. Verificación: `cd frontend && npm run test:e2e` en verde
  (`E2E_WEB_PORT=5180` si 5173 está ocupado, ver `docs/auth.md` § 10.1).
- [x] 11.3 Documentar en `docs/rbac.md` § Demo el guion de 3 minutos para el video (login owner con
  MFA, pantalla de Equipo, cambio de rol, login recepcionista, rechazo). Verificación: el guion usa
  credenciales ficticias del seed y cada paso tiene el resultado observable escrito.

## 12. Verificación de integración

- [x] 12.1 Correr el pipeline completo (`cd backend && uv run ruff check . && uv run mypy app && uv
  run pytest -q`; `cd frontend && npm run lint && npm run typecheck && npm run test`; `npm run
  test:e2e`) y anotar la salida real en `docs/rbac.md` § Verificación. Verificación: todo en verde y
  el documento reproduce comandos ejecutables tal como están escritos.
- [x] 12.2 Verificar que `docs/auth.md` y `docs/rbac.md` no se contradicen con `docs/team` ni con el
  OpenAPI (mismos `code`, mismos permisos, mismos endpoints) y que ningún documento contiene
  secretos, tokens ni datos reales. Verificación: barrido de las tablas de `code` contra
  `RbacErrorCode`/`AuthErrorCode` y revisión de que no hay PII real en los ejemplos.

## Matriz escenario → tarea

| Spec | Escenarios | Tasks |
|---|---|---|
| `platform-rbac` S1.1–S1.4 (matriz) | 4 | 1.1, 1.2, 1.3, 1.4 |
| `platform-rbac` S2.1–S2.4 (guard y catálogo) | 4 | 2.1–2.6, 10.4 |
| `platform-rbac` S3.1–S3.5 (fronteras duras) | 5 | 3.1, 3.2, 3.3, 3.4 |
| `platform-rbac` S4.1–S4.5 (permisos en sesión) | 5 | 2.5, 2.6, 7.3, 10.2 |
| `platform-auth` S7.1–S7.5 (delta de sesión) | 5 | 2.5, 2.6, 2.7 |
| `platform-team` S1.1–S1.3 (lectura) | 3 | 5.1, 5.2, 5.3, 5.4 |
| `platform-team` S2.1–S2.8 (alta) | 8 | 6.1, 6.2, 6.3, 6.4 |
| `platform-team` S3.1–S3.7 (cambio de rol) | 7 | 7.1, 7.2, 7.5 |
| `platform-team` S4.1–S4.4 (baja) | 4 | 7.3, 7.4, 7.5 |
| `platform-team` S5.1–S5.7 + S5.2b (ownership) | 8 | 8.1–8.5 |
| `platform-team` S6.1–S6.4 (auditoría) | 4 | 4.1–4.4, 6.1, 7.1 |
| `platform-team` S7.1–S7.4 (cross-tenant) | 4 | 9.1a, 9.1b, 9.2 |
| Criterio 3 del TPI (acceso autorizado y rechazo visibles) | — | 10.1–10.4, 11.2, 11.3 |
