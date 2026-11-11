# platform-team Specification

## Purpose
Define la administración de las memberships de un tenant (quién pertenece a la clínica y con qué
rol) y la transferencia atómica de ownership: lectura de miembros, alta con rol, cambio de rol, baja
lógica, transferencia de ownership que nunca deja al tenant con cero owners (RN-TEN-04) y auditoría
append-only de cada cambio sensible (RN-CMP-03). Todo opera bajo RLS con el `tenant_id` resuelto del
token (RN-TEN-02, RN-TEN-03).

## Requirements

### Requirement: Lectura de los miembros del tenant

`GET /api/v1/team/members` MUST exigir `team.read` y devolver las memberships del tenant de la
sesión con `membership_id`, `user_id`, `email`, `nombre`, `apellido`, `rol`, `activo` y
`professional_id` (nullable hasta C-05). MUST incluir las memberships inactivas con `activo: false`
para que el owner vea el historial, y MUST NOT exponer `password_hash`, `mfa_secret`, tokens ni
datos de otros tenants. El orden MUST ser estable (por `rol` y luego por apellido y nombre).

#### Scenario: S1.1 — El owner ve los miembros activos e inactivos de su tenant

- **WHEN** una sesión `owner` invoca `GET /api/v1/team/members` en un tenant con cuatro memberships
  activas y una dada de baja
- **THEN** responde `200` con las cinco filas, la dada de baja incluida con `activo: false`
- **AND** el JSON no contiene `password_hash`, `mfa_secret` ni `tenant_id` de otro tenant, y el
  orden es estable entre dos llamadas consecutivas

#### Scenario: S1.2 — Sin team.read la pantalla no existe para el backend

- **WHEN** una sesión con membership activa `professional` o `front_desk` invoca
  `GET /api/v1/team/members`
- **THEN** responde `403 forbidden` sin devolver la lista ni un conteo de miembros
- **AND** la respuesta no distingue si el tenant tiene cero, uno o veinte miembros

#### Scenario: S1.3 — Un miembro desactivado no cuenta para la invariante de owner

- **WHEN** el tenant tiene un `owner` con `activo: false` y otro `owner` activo, y se lee la lista
- **THEN** ambas filas aparecen y solo la activa se considera owner vigente
- **AND** ninguna operación de la lista informa dos owners activos

### Requirement: Alta de miembro con rol (sin invitaciones por email)

`POST /api/v1/team/members` MUST exigir `team.create` y crear una `membership` en el tenant de la
sesión a partir de un `email` y un `rol`. Si el `user` existe, MUST reutilizarlo sin tocar su
`password_hash`; si no existe, MUST crearlo con `password_temporal` elegida por el owner en el
payload (mínimo 12 caracteres) y MUST NOT devolverla en la respuesta. Los roles asignables por este
endpoint MUST ser `clinical_admin`, `professional`, `assistant`, `front_desk`, `billing` y
`accountant`; `owner` MUST rechazarse porque solo se obtiene por transferencia (RN-TEN-04) y
`patient`/`external_lab` MUST rechazarse porque no son roles de equipo interno. Si el `user` ya
tiene una membership **inactiva** con ese mismo `rol` en el tenant, MUST reactivarla
(`activo = true`) en lugar de insertar una fila nueva —el único `(tenant_id, user_id, rol)` no es
parcial— y MUST registrar `member_reactivated`. La operación MUST ser atómica: usuario, membership y
evento de auditoría se confirman o se revierten juntos.

#### Scenario: S2.1 — Alta de un usuario existente crea la membership y audita

- **WHEN** el owner envía `{email, rol: "professional"}` de un `user` que ya existe y no tiene
  membership en el tenant
- **THEN** responde `201` con la membership creada (`activo: true`), sin `password_hash` ni
  `password_temporal`
- **AND** existe exactamente un `membership_event` de tipo `member_created` con el `actor_user_id`
  del owner, el `target_user_id` y `detail.rol = "professional"`

#### Scenario: S2.2 — Alta de un usuario inexistente crea el user con contraseña temporal

- **WHEN** el owner envía `{email, rol: "front_desk", password_temporal}` de un email que no existe
- **THEN** responde `201`, se crea el `user` con la contraseña hasheada (Argon2id) y la membership,
  y la respuesta no incluye la contraseña ni su hash
- **AND** la contraseña temporal no aparece en `membership_event.detail`, en logs ni en la auditoría

#### Scenario: S2.3 — El rol owner no se asigna por esta vía

- **WHEN** el owner envía `rol: "owner"` a `POST /api/v1/team/members`
- **THEN** responde `409` con `code = "owner_must_be_transferred"`
- **AND** no se crea ni se modifica ninguna membership y no se registra `membership_event`

#### Scenario: S2.4 — Rol no asignable y membership activa duplicada se rechazan

- **WHEN** el payload pide `rol: "patient"` o `rol: "external_lab"`, o el usuario ya tiene una
  membership **activa** con ese mismo rol en el tenant
- **THEN** el rol no asignable responde `422` con `code = "role_not_assignable"` y la duplicada
  responde `409` con `code = "membership_exists"`
- **AND** en ambos casos la transacción se revierte completa y no queda evento de auditoría

#### Scenario: S2.5 — Un usuario de otro tenant no filtra datos ni se da de baja

- **WHEN** el owner da de alta por email a un `user` que ya tiene membership activa en otro tenant
- **THEN** responde `201` con una membership nueva **solo** en el tenant de la sesión, sin modificar
  el rol que ese usuario tiene en el otro tenant
- **AND** la respuesta no revela el otro tenant, su rol ni ningún dato de esa clínica

#### Scenario: S2.6 — clinical_admin puede leer pero no dar de alta

- **WHEN** una sesión `clinical_admin` (con `team.read` y sin `team.create`) envía
  `POST /api/v1/team/members`
- **THEN** responde `403 forbidden` y no se crea usuario, membership ni evento
- **AND** la misma sesión sigue pudiendo leer la lista con `GET /api/v1/team/members`

#### Scenario: S2.7 — Readmisión de una membership inactiva con el mismo rol

- **WHEN** el owner da de alta un email cuyo `user` ya tiene una membership `activo: false` con el
  mismo `rol` que se está asignando en ese tenant
- **THEN** responde `201`, la fila existente vuelve a `activo: true` y no se inserta una segunda
  membership con la misma combinación `(tenant_id, user_id, rol)`
- **AND** se registra un único `membership_event` de tipo `member_reactivated` y no `member_created`

#### Scenario: S2.8 — La contraseña temporal se valida antes de crear el usuario

- **WHEN** el email no existe y el payload omite `password_temporal` o envía una de menos de 12
  caracteres
- **THEN** responde `422` con `code = "invalid_request"` y no se crea el `user` ni la membership
- **AND** cuando el email ya existe, `password_temporal` es opcional y su ausencia no modifica el
  `password_hash` del usuario

### Requirement: Cambio de rol de un miembro

`PATCH /api/v1/team/members/{membership_id}` MUST exigir `team.update` y cambiar el `rol` de una
membership del tenant de la sesión. El nuevo rol MUST pertenecer al conjunto asignable: `owner` MUST
rechazarse con `409 owner_must_be_transferred` (solo se llega por transferencia, RN-TEN-04) y
`patient`/`external_lab` con `422 role_not_assignable`. Cambiar el rol del **único owner activo**
—incluida la autodemoción del actor— MUST rechazarse con `409 last_owner` sin modificar nada, porque
dejaría al tenant sin owner (RN-TEN-04). Un `membership_id` de otro tenant MUST responder `404
membership_not_found`. La misma combinación usuario+rol en **otra** membership del tenant MUST
responder `409 membership_exists`; repetir el rol que la membership ya tiene MUST ser idempotente
(`200`) y no auditar.

#### Scenario: S3.1 — Cambio de rol efectivo y auditado

- **WHEN** el owner cambia una membership de `professional` a `clinical_admin`
- **THEN** responde `200` con la membership actualizada y `roles` coherentes con la matriz
- **AND** se registra un `membership_event` de tipo `member_role_changed` con
  `detail.rol_anterior = "professional"` y `detail.rol_nuevo = "clinical_admin"`

#### Scenario: S3.2 — El único owner no puede autodemoverse

- **WHEN** el owner envía un cambio de rol sobre su propia membership `owner` a `clinical_admin`, o
  sobre la membership del único owner activo del tenant
- **THEN** responde `409` con `code = "last_owner"` y la membership sigue `owner` y `activo: true`
- **AND** no se registra `membership_event` de cambio de rol

#### Scenario: S3.3 — Membership de otro tenant responde 404

- **WHEN** el owner de A envía `PATCH /api/v1/team/members/{membership_id}` con el id de una
  membership de B
- **THEN** responde `404` con `code = "membership_not_found"` y la membership de B queda intacta
- **AND** la respuesta es idéntica a la de un id inexistente: no revela existencia en otro tenant

#### Scenario: S3.4 — Repetir el mismo rol asignable es idempotente

- **WHEN** el owner envía un cambio a un rol **asignable** que la membership ya tiene
- **THEN** responde `200` sin duplicar la membership ni el evento de auditoría
- **AND** el estado final de la membership es idéntico al inicial

#### Scenario: S3.5 — Sin team.update no hay cambio de rol

- **WHEN** una sesión `clinical_admin` o `billing` envía el `PATCH`
- **THEN** responde `403 forbidden` y el rol de la membership no cambia
- **AND** no se registra `membership_event`

#### Scenario: S3.6 — El rol destino ya existe en otra membership del usuario

- **WHEN** el owner cambia una membership de un usuario que ya tiene **otra** membership con el rol
  destino en el mismo tenant
- **THEN** responde `409` con `code = "membership_exists"`, sin modificar ninguna de las dos filas
- **AND** no se registra `membership_event` de cambio de rol

#### Scenario: S3.7 — El PATCH no es una vía para llegar a owner ni a roles de portal

- **WHEN** el owner envía `PATCH` con `rol: "owner"`, o con `rol: "patient"` / `rol: "external_lab"`
- **THEN** `owner` responde `409` con `code = "owner_must_be_transferred"` y los roles de portal
  responden `422` con `code = "role_not_assignable"`
- **AND** la membership queda con su rol anterior, el tenant conserva exactamente un owner activo y
  no se registra evento

### Requirement: Baja lógica de una membership

`DELETE /api/v1/team/members/{membership_id}` MUST exigir `team.delete` y desactivar la membership
(`activo = false`), sin borrar la fila (RN-EX-03). El efecto MUST ser inmediato: el siguiente request
del usuario dado de baja MUST fallar en `require_tenant` con `401 not_authenticated`. Dar de baja al
**único owner activo** —incluida la autobaja del actor— MUST rechazarse con `409 last_owner`. Repetir
la baja de una membership ya inactiva MUST ser idempotente: `204` sin evento nuevo.

#### Scenario: S4.1 — La baja desactiva y expulsa al usuario

- **WHEN** el owner da de baja una membership activa de rol `professional`
- **THEN** responde `204`, la fila queda con `activo: false` y se registra `membership_event` de
  tipo `member_deactivated`
- **AND** el siguiente request de ese usuario con su sesión vigente responde `401 not_authenticated`
  y no conserva sus permisos anteriores

#### Scenario: S4.2 — El único owner no puede darse de baja

- **WHEN** el owner intenta `DELETE` sobre su propia membership `owner` o sobre la del único owner
  activo del tenant
- **THEN** responde `409` con `code = "last_owner"` y la membership sigue activa
- **AND** el tenant conserva exactamente un owner activo y no se registra evento de baja

#### Scenario: S4.3 — Reintentar la baja es idempotente

- **WHEN** se repite el `DELETE` de una membership que ya está `activo: false`
- **THEN** responde `204` y no se agrega un segundo `membership_event`
- **AND** el resto de las memberships del tenant no se modifica

#### Scenario: S4.4 — Sin team.delete no hay baja

- **WHEN** una sesión con `team.read` pero sin `team.delete` envía el `DELETE`
- **THEN** responde `403 forbidden` y la membership sigue activa
- **AND** no se registra evento de baja

### Requirement: Transferencia atómica de ownership (RN-TEN-04)

`POST /api/v1/team/ownership-transfer` MUST exigir `ownership.transfer` y ejecutar en **una sola
transacción**: validar que el actor sigue siendo el owner activo, desactivar su membership `owner`
y asignarle el `previous_owner_role` indicado (obligatorio, del conjunto asignable y distinto de
`owner`), y promover a `owner` activo la membership `target_membership_id` del tenant. Al terminar,
el tenant MUST tener exactamente un owner activo, y en ningún instante observable MUST haber cero o
dos. El endpoint MUST serializar las transferencias concurrentes del mismo tenant (lock de la fila
`tenant` con `SELECT … FOR UPDATE` más índice único parcial `uq_membership_owner_activo`) y MUST
responder `409 ownership_changed` a la transferencia que perdió la carrera. El destino MUST ser una
membership activa del tenant y distinta del actor; un destino inexistente o de otro tenant MUST
responder `404 membership_not_found`, indistinguible entre ambos casos. Si el actor ya tiene **otra**
membership en el tenant con el rol `previous_owner_role`, la operación MUST responder `409
role_conflict` y revertirse completa —el único `(tenant_id, user_id, rol)` no es parcial y el actor no
puede quedar con dos memberships del mismo rol—; el actor MUST seguir siendo owner. El mismo chequeo
MUST aplicarse del lado del **destino**: si el target ya tiene otra membership `owner` inactiva en el
tenant, promoverlo violaría el mismo único y MUST responder `409 role_conflict` con `rollback`. La
respuesta MUST reflejar los roles nuevos y el SPA MUST resincronizar los permisos del actor.

#### Scenario: S5.1 — Transferencia exitosa deja exactamente un owner

- **WHEN** el owner transfiere a un miembro activo `clinical_admin` con
  `previous_owner_role: "clinical_admin"`
- **THEN** responde `200`, el destino queda `owner` activo y el actor queda `clinical_admin` activo
- **AND** un `SELECT count(*)` de owners activos del tenant devuelve exactamente `1`, y se registra
  `membership_event` de tipo `ownership_transferred` con actor, target y ambos roles

#### Scenario: S5.2 — Destino inválido no altera el ownership

- **WHEN** el target es una membership inactiva, la del propio actor, o ya es `owner`, o
  `previous_owner_role` viene ausente o igual a `owner`
- **THEN** la membership inactiva responde `409 member_inactive`, el actor responde `409
  member_is_actor`, el que ya es owner responde `409 member_already_owner`, y `previous_owner_role`
  ausente o `owner` responde `422` con `code = "role_not_assignable"`
- **AND** el actor sigue siendo el único owner activo y no se registra evento de transferencia

#### Scenario: S5.2b — Destino inexistente y destino de otro tenant son indistinguibles

- **WHEN** el `target_membership_id` no existe o pertenece a otro tenant
- **THEN** ambos casos responden `404` con `code = "membership_not_found"` y el mismo mensaje
- **AND** no se modifica ninguna fila de ninguno de los dos tenants ni se registra evento

#### Scenario: S5.3 — Dos transferencias concurrentes: una gana y nunca hay cero owners

- **WHEN** dos transferencias simultáneas del mismo tenant, con actores que eran el mismo owner
  vigente, intentan promover destinos distintos
- **THEN** exactamente una responde `200` y la otra `409 ownership_changed` (el actor ya no es owner
  vigente al obtener el lock)
- **AND** después de ambas, `count(*)` de owners activos es `1` y no existió ninguna transacción
  confirmada con `0`

#### Scenario: S5.4 — Sin ownership.transfer no hay transferencia

- **WHEN** una sesión `clinical_admin` con `team.read` y `team.update` invoca el endpoint
- **THEN** responde `403 forbidden` y el ownership no cambia
- **AND** no se registra evento de transferencia

#### Scenario: S5.5 — El actor ve sus permisos nuevos sin re-loguearse

- **WHEN** la transferencia termina y el actor consulta `GET /api/v1/auth/me` (o fuerza la
  resincronización que dispara el SPA)
- **THEN** sus `roles` ya no incluyen `owner` y sus `permissions` tampoco incluyen
  `ownership.transfer` ni `team.update`
- **AND** una llamada posterior a `POST /api/v1/team/ownership-transfer` con su sesión vigente
  responde `403 forbidden`

#### Scenario: S5.6 — El actor ya tiene una membership con el rol de destino

- **WHEN** el owner transfiere el ownership pidiendo `previous_owner_role` igual a un rol que ya
  tiene en otra membership del mismo tenant (caso normal de un usuario multi-rol, RN-TEN-05)
- **THEN** responde `409` con `code = "role_conflict"` y la transacción se revierte completa
- **AND** el actor sigue `owner` activo, `count(*)` de owners activos es `1` y no se registra
  `membership_event` de transferencia

#### Scenario: S5.7 — El destino ya tiene otra membership owner inactiva

- **WHEN** el target de la transferencia tiene una membership `owner` **inactiva** en el mismo tenant
  (por ejemplo, porque fue owner en el pasado) además de la membership activa que se promueve
- **THEN** responde `409` con `code = "role_conflict"` y la transacción se revierte completa, sin
  violar `uq_membership_tenant_user_rol`
- **AND** el actor sigue `owner` activo, el target conserva su rol anterior y `count(*)` de owners
  activos es `1`

### Requirement: Auditoría append-only de los cambios de RBAC (RN-CMP-03)

Cada alta, cambio de rol, baja y transferencia de ownership confirmada MUST registrar exactamente un
`membership_event` con `tenant_id`, `actor_user_id`, `target_user_id`, `tipo`, `detail` (roles
anterior y nuevo cuando aplique) y `created_at`. La tabla MUST ser append-only por trigger de base de
datos: un `UPDATE` o `DELETE` directo MUST fallar con SQLSTATE `55000`, incluso para el
superusuario; el `UPDATE` interno que dispara una cascada de FK MUST permitirse. El rol de
aplicación MUST tener solo `INSERT` (sin `SELECT`): ningún endpoint ni rol interno MUST poder leer la
auditoría. Una operación de RBAC que falla MUST NOT dejar evento.

#### Scenario: S6.1 — Una mutación confirmada deja un evento con datos mínimos

- **WHEN** se confirma un cambio de rol
- **THEN** existe un `membership_event` con `tenant_id`, `actor_user_id`, `target_user_id`,
  `tipo = "member_role_changed"` y `detail` con `rol_anterior` y `rol_nuevo`
- **AND** `detail` no contiene `password_hash`, `password_temporal`, `mfa_secret` ni tokens

#### Scenario: S6.2 — La auditoría no se puede modificar ni borrar

- **WHEN** el rol de aplicación, o el superusuario de test, ejecuta `UPDATE` o `DELETE` sobre
  `membership_event`
- **THEN** PostgreSQL aborta con SQLSTATE `55000` y la fila permanece intacta
- **AND** el borrado de un `user` referenciado no falla y deja `actor_user_id`/`target_user_id` en
  `NULL`; el borrado de un `tenant` elimina sus eventos por `ON DELETE CASCADE` (la auditoría se va
  con el tenant y no bloquea el borrado)

#### Scenario: S6.3 — La aplicación no puede leer su propia auditoría

- **WHEN** `odontologia_app` ejecuta `SELECT` sobre `membership_event`, con o sin contexto de tenant
- **THEN** la respuesta es un error de permisos, nunca filas de auditoría
- **AND** ningún endpoint de la API expone `membership_event`

#### Scenario: S6.4 — Una operación rechazada no audita

- **WHEN** una operación de RBAC responde `403`, `404`, `409` o `422`
- **THEN** no se registra ningún `membership_event` para esa operación
- **AND** la cantidad de eventos del tenant queda igual que antes del intento

### Requirement: Aislamiento cross-tenant de la gestión de equipo (RN-TEN-02)

Todas las tablas y endpoints de este change MUST resolver el tenant del token/sesión (RN-TEN-03) y
operar con RLS habilitada y forzada. Un request de A MUST NOT leer, modificar ni recibir datos de B,
ni siquiera con un `membership_id`, `user_id` o `tenant_id` de B en ruta, body, query o header. Sin
contexto fijado, las consultas MUST devolver cero filas (fail-closed). El contrato para un `tenant_id`
ajeno es **único**: en el body de los cinco endpoints responde `422` (los DTO usan
`extra="forbid"`); en query o header se ignora porque ningún endpoint lo lee. Este requirement es
gate de merge: sin sus tests, el change no se aprueba.

#### Scenario: S7.1 — La lista de A nunca contiene miembros de B

- **WHEN** A y B tienen miembros y una sesión de A invoca `GET /api/v1/team/members`
- **THEN** la respuesta contiene solo memberships de A y ningún email, id o rol de B
- **AND** el `tenant_id` de B enviado en query o header no amplía el resultado

#### Scenario: S7.2 — Modificar o dar de baja un miembro de B afecta cero filas

- **WHEN** el owner de A envía `PATCH` o `DELETE` con el `membership_id` de B
- **THEN** responde `404 membership_not_found` (o `403 forbidden` si el permiso falta) y no se
  modifica ninguna fila de B
- **AND** no se registra `membership_event` en B

#### Scenario: S7.3 — Sin contexto de tenant no se filtra nada

- **WHEN** se ejecuta `SELECT` sobre `membership` sin `set_config('app.current_tenant', …)` y con
  `SET ROLE odontologia_app`
- **THEN** devuelve `0` filas (fail-closed) y cualquier `INSERT` con un `tenant_id` ajeno es rechazado
  por la política
- **AND** sobre `membership_event` el rol de aplicación recibe un error de permisos (no tiene
  `SELECT`), nunca filas y nunca `0` filas silencioso

#### Scenario: S7.4 — El tenant_id ajeno en el body se rechaza con un contrato único

- **WHEN** cualquiera de los cinco endpoints de equipo recibe `tenant_id` (o cualquier campo no
  declarado) en el body
- **THEN** responde `422` con `code = "invalid_request"` antes de tocar la base, en los cinco
  endpoints por igual
- **AND** un `tenant_id` de B en query o header no cambia el resultado: el tenant sale solo de la
  sesión
