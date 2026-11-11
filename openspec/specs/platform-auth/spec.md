# platform-auth Specification

## Purpose
Define la identidad y el ciclo de vida de la sesión de los usuarios internos de la plataforma:
credenciales Argon2id, emisión y rotación de sesión en cookies `httpOnly`, detección de reuso de
refresh, lockout progresivo, MFA TOTP obligatorio para `owner`/`billing`, recuperación de
contraseña con token de un solo uso y cambio de tenant activo con re-emisión de sesión.

## Requirements

### Requirement: Login con credenciales y emisión de sesión

El sistema MUST autenticar `email` + `password` (hash Argon2id, RN-AU-01) dentro del `tenant_slug`
solicitado y, si existe `membership` activa, emitir una sesión en cookies `httpOnly` +
`SameSite=Lax` + `Secure` (RN-AU-02, DD-10), con el `tenant_id` resuelto desde la `membership` y
nunca desde el body (RN-TEN-03, RN-TEN-05). Todo fallo de credenciales —password incorrecto,
usuario inexistente o inactivo, membership inactiva— MUST responder `401 invalid_credentials`
uniforme sin emitir cookies. Un tenant existente en estado `suspended` MUST responder
`403 tenant_not_available` sin sesión (RN-TEN-06).

#### Scenario: S1.1 — Login válido emite cookies httpOnly y sesión ligada al tenant

- **WHEN** se hace `POST /api/v1/auth/login` con email y password válidos y el `tenant_slug` de una
  clínica donde el usuario tiene `membership` activa con rol `professional`
- **THEN** responde `200` con dos `Set-Cookie` (`odontologia_access` y `odontologia_refresh`) que
  llevan `HttpOnly`, `SameSite=Lax`, `Path` (`/` para access, `/api/v1/auth` para refresh) y
  `Secure` salvo en `local`/`test`
- **AND** el body devuelve el usuario, el tenant y `roles: ["professional"]` sin `password_hash`
  ni `mfa_secret`, y existe una `session` nueva con el `tenant_id` del tenant solicitado

#### Scenario: S1.2 — Credenciales inválidas se rechazan sin emitir sesión

- **WHEN** el password es incorrecto, o el email no existe, o el usuario tiene `activo = false`
- **THEN** los tres casos responden `401` con el mismo código `invalid_credentials` y el mismo
  mensaje, sin `Set-Cookie`, sin fila nueva en `session` y con un `auth_event` por intento

#### Scenario: S1.3 — Membership inactiva o tenant inexistente no revelan la cuenta

- **WHEN** las credenciales son válidas pero la `membership` del tenant está `activa = false`, o
  el `tenant_slug` no existe
- **THEN** responde `401 invalid_credentials` (nunca `403` ni `404`), sin cookies y sin sesión

#### Scenario: S1.4 — Con memberships en A y B, el login queda en el tenant solicitado

- **WHEN** el usuario tiene memberships activas en A y B con roles distintos y hace login con
  `tenant_slug = B`
- **THEN** la sesión nueva queda con `tenant_id = B`, el body devuelve únicamente los roles de B y
  `/auth/me` con esa cookie no expone ningún dato de A
- **AND** no se crea ninguna fila en `session` con `tenant_id = A` para ese login

#### Scenario: S1.5 — Un tenant suspendido no permite iniciar sesión

- **WHEN** las credenciales y la membership son válidas pero el `tenant.estado = 'suspended'`
- **THEN** responde `403 tenant_not_available` sin `Set-Cookie` y sin crear `session`
- **AND** el `auth_event` registra el intento con `tenant_id` y `detail.reason = "tenant_suspended"`

### Requirement: Ciclo de vida de la sesión con refresh rotativo y detección de reuso

Cada uso válido de `POST /api/v1/auth/refresh` MUST rotar el refresh token de forma atómica: el
anterior queda `rotado`, se emite uno nuevo de la misma familia y la sesión sigue vigente
(RN-AU-03). Reutilizar un token ya rotado MUST revocar toda su familia y la sesión. Como el token
de refresh es opaco y la RLS de `session`/`refresh_token` es `FORCE`, el endpoint MUST resolver
`tenant_id`/`session_id` con la función acotada `auth_resolve_session_by_refresh(token_hash)`
antes de fijar `app.current_tenant`; sin fila resuelta MUST responder `401 not_authenticated` sin
distinguir si la sesión existe en otro tenant. Una sesión emitida con una
`credentials_version` anterior a la del `user` MUST rechazarse con `401 credentials_changed` sin
rotar el refresh. `POST /api/v1/auth/logout` MUST revocar la sesión y su familia, limpiar las
cookies y ser idempotente.

#### Scenario: S2.1 — Refresh válido rota el token y conserva la sesión

- **WHEN** se hace `POST /api/v1/auth/refresh` con un refresh `activo` y vigente
- **THEN** responde `200` con un `Set-Cookie` de refresh distinto del anterior
- **AND** la fila usada queda `estado = 'rotado'` con `used_at`, la nueva fila queda `activo` con
  el mismo `family_id`, y la `session` asociada sigue sin `revoked_at`

#### Scenario: S2.2 — Reutilización de un refresh rotado revoca la familia completa

- **WHEN** se presenta por segunda vez un refresh que ya fue rotado
- **THEN** responde `401 refresh_reuse`
- **AND** todas las filas de esa familia quedan `revocado` y la `session` queda con `revoked_at`
- **AND** el refresh que estaba vigente en esa familia deja de refrescar (`401 not_authenticated`)

#### Scenario: S2.3 — Refresh expirado o de sesión cerrada no afecta otras familias

- **WHEN** se presenta un refresh expirado, o el de una sesión ya revocada por logout
- **THEN** responde `401 not_authenticated` sin revocar las demás familias activas del mismo
  usuario, que siguen refrescando con `200`

#### Scenario: S2.4 — Dos refresh concurrentes con el mismo token no emiten dos familias

- **WHEN** dos requests simultáneos presentan el mismo refresh `activo`
- **THEN** exactamente uno rota (una sola fila nueva `activo` con ese token origen) y el otro
  recibe `401`
- **AND** el resultado es fail-closed: la familia queda revocada y ambos clientes deben
  reautenticarse (el cliente web evita el caso con refresh *single-flight*)

#### Scenario: S2.5 — Logout idempotente revoca y limpia cookies

- **WHEN** se hace `POST /api/v1/auth/logout` con cookie válida
- **THEN** responde `204`, envía ambas cookies con `Max-Age=0` y la sesión y su familia quedan
  revocadas
- **AND** repetir el logout con la misma cookie responde `204` sin error y sin tocar otras
  sesiones del usuario

#### Scenario: S2.6 — Un reset de contraseña invalida el refresh sin escribir cross-tenant

- **WHEN** se consumió un reset de contraseña (que incrementó `user.credentials_version`) y se
  presenta el refresh de una sesión emitida con la versión anterior
- **THEN** responde `401 credentials_changed`, no rota el refresh y la sesión de ese tenant queda
  `revocada` bajo su propio `app.current_tenant`
- **AND** no se actualiza ninguna fila `session` de otro tenant y las sesiones nuevas del usuario
  (emitidas con la versión nueva) siguen funcionando

### Requirement: Lockout progresivo y registro de eventos de autenticación

Tras 5 intentos fallidos consecutivos el `user` MUST quedar bloqueado: `POST /api/v1/auth/login`
responde `423` con `Retry-After` durante 15 minutos, y cada bloqueo consecutivo duplica la ventana
(tope 24 h). Un login correcto durante el bloqueo MUST NOT emitir sesión. Cada intento MUST
registrarse en `auth_event`, que es append-only (RN-AU-05). En este change `auth_event`
**reemplaza** al `audit_log` nombrado por RN-AU-05; la proyección al `audit_log` definitivo es
C-14 (ver `proposal.md` § Out of Scope).

#### Scenario: S3.1 — Cuatro fallos no bloquean y el quinto bloquea

- **WHEN** se encadenan intentos con password incorrecto
- **THEN** los intentos 1 a 4 responden `401` con `failed_login_count` de 1 a 4
- **AND** el quinto responde `423` con `Retry-After: 900`, `locked_until` a 15 minutos y
  `auth_event` con 4 `login_fail` y 1 `lockout`

#### Scenario: S3.2 — Credenciales correctas durante el bloqueo no entran

- **WHEN** la cuenta está bloqueada y se envía el password correcto
- **THEN** responde `423 locked` sin `Set-Cookie`, sin `session` nueva y con `last_login_at` sin
  cambios

#### Scenario: S3.3 — El bloqueo expira y el login correcto resetea contadores

- **WHEN** `locked_until` ya pasó (forzado en el test) y se envía el password correcto
- **THEN** responde `200`, `failed_login_count` vuelve a 0 y el siguiente fallo cuenta desde 1

#### Scenario: S3.4 — Bloqueos consecutivos duplican la ventana y el lockout es por cuenta

- **WHEN** tras expirar un bloqueo se repiten 5 fallos en la misma cuenta
- **THEN** la segunda ventana es de 30 minutos, y un login exitoso posterior vuelve
  `lockout_strikes` a 0
- **AND** mientras el usuario A está bloqueado, el usuario B del mismo tenant loguea `200`, y A
  sigue bloqueado (`423`) aunque intente en otro tenant donde también tiene membership

### Requirement: MFA TOTP obligatorio para owner y billing

Los roles `owner` y `billing` **en el tenant de la sesión** MUST presentar un segundo factor TOTP
válido para obtener sesión (RN-AU-04). Con password válido y sin segundo factor, el login MUST
responder `403 mfa_required` (o `403 mfa_enrollment_required` si no hay secreto) con un desafío
efímero de un solo uso y sin cookies de sesión. El desafío MUST vivir en Redis con TTL de 5
minutos, consumirse con `GETDEL` atómico y viajar en una cookie `HttpOnly`
`Path=/api/v1/auth/mfa`; si Redis no está disponible MUST responder `503 mfa_unavailable` sin
sesión. El código TOTP MUST validarse contra `user.last_totp_step` con un `UPDATE ... WHERE
last_totp_step IS NULL OR last_totp_step < :step` atómico, y la sesión MUST registrar el paso
aceptado en `session.last_used_step`. `mfa_satisfied` es por sesión y por tenant. El secreto TOTP
MUST cifrarse en reposo y MUST NOT aparecer en `/api/v1/auth/me`, logs ni eventos.

#### Scenario: S4.1 — Owner enrolado completa el step-up y obtiene sesión

- **WHEN** un `owner` con secreto enrolado envía password válido
- **THEN** responde `403 mfa_required` con una cookie de desafío `HttpOnly`, `Path=/api/v1/auth/mfa`
  y `Max-Age=300`, sin cookie de sesión y con una `session` en estado `pendiente_mfa`
- **AND** `POST /api/v1/auth/mfa/verify` con el código TOTP de la ventana actual responde `200`,
  consume el desafío, emite las cookies de sesión y deja `session.mfa_satisfied = true` y
  `session.last_used_step = <paso aceptado>`

#### Scenario: S4.2 — Código TOTP inválido o reusado no emite sesión y cuenta para el lockout

- **WHEN** se envía un código incorrecto, o se repite un código cuyo paso ya está registrado en
  `user.last_totp_step`
- **THEN** responde `401 invalid_mfa_code` sin cookies de sesión, incrementa
  `failed_login_count` y registra `mfa_fail` en `auth_event`
- **AND** dos requests concurrentes con el mismo código no pueden actualizar `last_totp_step` dos
  veces (solo uno obtiene la fila del `UPDATE` atómico) y al quinto fallo de MFA la cuenta
  responde `423` como cualquier lockout

#### Scenario: S4.3 — Owner o billing sin secreto debe enrolar antes de entrar

- **WHEN** un `owner` con `mfa_secret IS NULL` envía password válido
- **THEN** responde `403 mfa_enrollment_required` y `POST /api/v1/auth/mfa/enroll/start` devuelve
  una única vez el `otpauth://` y el secreto
- **AND** `POST /api/v1/auth/mfa/enroll/confirm` con un código válido persiste el secreto cifrado,
  setea `mfa_satisfied` y emite sesión; sin confirmación no hay cookies de sesión

#### Scenario: S4.4 — Roles sin MFA entran directo y el secreto nunca se expone

- **WHEN** un `front_desk` envía credenciales válidas, o un `owner` con sesión consulta
  `GET /api/v1/auth/me`, o un `owner` envía `skip_mfa: true` en el body del login
- **THEN** el `front_desk` recibe `200` sin desafío y con `mfa_satisfied = true` (no requiere
  factor); el `/api/v1/auth/me` responde `200` sin `mfa_secret` ni `password_hash`; el `owner` con
  `skip_mfa` recibe `403 mfa_required` igual
- **AND** el valor almacenado en `user.mfa_secret` no es el secreto en claro y tiene
  `mfa_secret_key_version` seteado

#### Scenario: S4.5 — El desafío MFA es de un solo uso y expira

- **WHEN** se presenta dos veces el mismo desafío, o se usa uno pasados los 5 minutos, o un código
  incorrecto consume el desafío
- **THEN** la segunda presentación y el desafío expirado responden `401 mfa_step_up_expired` sin
  emitir cookies; tras un código incorrecto el cliente debe reiniciar el login
- **AND** la cuenta sigue sujeta al lockout por los fallos de MFA registrados

#### Scenario: S4.6 — Sin Redis el step-up falla cerrado

- **WHEN** el login de un `owner` requiere step-up y Redis no responde
- **THEN** responde `503 mfa_unavailable` sin cookie de desafío, sin cookie de sesión y sin
  `session` `vigente`
- **AND** no se emite un desafío en memoria del proceso ni se persiste el código TOTP

### Requirement: Recuperación de contraseña con token opaco de un solo uso

`POST /api/v1/auth/forgot-password` MUST responder `202` siempre y persistir un token opaco de un
solo uso con TTL de 30 minutos, almacenado como hash (`03_actores_y_roles.md:90`; no existe RN
específica de reset). `POST /api/v1/auth/reset-password` MUST consumirlo exactamente una vez,
fijar la nueva contraseña con Argon2id e **invalidar todas las sesiones previas por credencial**:
incrementa `user.credentials_version` en la misma transacción, sin enumerar tenants ni escribir
`session` de otros tenants. El token MAY exponerse en la respuesta solo en
`local`/`development`/`test`.

#### Scenario: S5.1 — Solicitud y reset consumen el token una sola vez e invalidan sesiones

- **WHEN** se pide `forgot-password` para un email existente en `test`
- **THEN** responde `202` con el token en la respuesta, y en BD hay una fila con `expires_at` a 30
  minutos y el token guardado como hash, no en claro
- **AND** `reset-password` con ese token y una password nueva válida responde `200`, deja el nuevo
  `password_hash` verificable con Argon2id, marca `used_at`, incrementa `credentials_version` y
  las cookies de sesiones previas pasan a responder `401 credentials_changed`

#### Scenario: S5.2 — Token expirado, ya usado o manipulado no cambia la contraseña

- **WHEN** el token expiró hace 1 segundo, o ya fue consumido, o no corresponde a ningún hash
- **THEN** responde `400 invalid_or_expired_token` y el `password_hash` del usuario queda intacto

#### Scenario: S5.3 — Email inexistente responde igual y no crea token

- **WHEN** se pide `forgot-password` para un email que no existe
- **THEN** responde `202` con el mismo body que el caso existente y no se crea ninguna fila en
  `password_reset_token`

#### Scenario: S5.4 — El token no se expone fuera del entorno de desarrollo

- **WHEN** `ENVIRONMENT=production` y se pide `forgot-password`
- **THEN** responde `202` sin el campo `token` y el token no aparece en los logs capturados
- **AND** con `ENVIRONMENT=development` el mismo request sí devuelve el token, marcado como
  exclusivo de desarrollo

#### Scenario: S5.5 — Dos resets concurrentes con el mismo token: solo uno gana

- **WHEN** dos requests simultáneos consumen el mismo `token_hash` con passwords nuevas distintas
- **THEN** exactamente uno responde `200` y el otro `400 invalid_or_expired_token`
- **AND** el `password_hash` final corresponde a la password del request ganador y
  `credentials_version` se incrementa una sola vez

### Requirement: Tenant activo y cambio de tenant con re-emisión de sesión

El `tenant_id` de toda operación autenticada MUST salir de la sesión (RN-TEN-03), con una **única
excepción explícita**: `POST /api/v1/auth/switch-tenant`, que lee el tenant destino del body y lo
valida contra una `membership` activa. El switch MUST revocar la sesión vigente y emitir una
sesión nueva con su propia familia de refresh (RN-AU-07). Un destino sin membership MUST responder
`403 tenant_not_available` sin tocar la sesión actual. Si el destino tiene al usuario con rol
`owner` o `billing`, el switch MUST NOT emitir sesión: responde `403 mfa_required` si ya enroló o
`403 mfa_enrollment_required` si no, y la sesión nueva se emite **solo después** del step-up
(RN-AU-04). `mfa_satisfied` es por sesión y por tenant: un factor satisfecho en A no habilita B.

#### Scenario: S6.1 — Switch a un tenant con membership activa re-emite sesión

- **WHEN** un usuario con memberships activas en A y B, con sesión en A y rol `professional` en B,
  pide switch a B
- **THEN** responde `200`, la sesión de A queda revocada, se crea una `session` nueva con
  `tenant_id = B`, `mfa_satisfied = true` y un `family_id` nuevo, y las cookies se renuevan
- **AND** `GET /api/v1/auth/me` devuelve el tenant B y únicamente los roles que tiene en B

#### Scenario: S6.2 — Switch a un tenant sin membership no rompe la sesión actual

- **WHEN** se pide switch a un tenant donde el usuario no tiene `membership` activa, o la tiene
  con `activa = false`
- **THEN** responde `403 tenant_not_available` y el `/api/v1/auth/me` con la sesión de A sigue `200`
- **AND** no se crea ninguna fila en `session`/`refresh_token` con el `tenant_id` destino

#### Scenario: S6.3 — El tenant del body o query se ignora, salvo en switch-tenant

- **WHEN** la sesión tiene `tenant_id = A` y el request a cualquier endpoint **distinto de
  `switch-tenant`** envía `tenant_id = B` en body o query
- **THEN** la operación se resuelve con A, el `set_config('app.current_tenant', …)` usa A y no se
  lee ni escribe ninguna fila de B
- **AND** en `switch-tenant` el tenant destino del body sí se lee, pero solo se acepta si existe
  `membership` activa; esa es la excepción declarada, no una nota al pie

#### Scenario: S6.4 — Operar en A no lee ni escribe datos de B

- **WHEN** `/api/v1/auth/me` y cualquier endpoint tenant-scoped se invocan con la sesión de A de un
  usuario que también tiene membership en B, o se intenta `switch-tenant(B)` sin membership
- **THEN** la respuesta solo contiene el tenant A y los roles de A, sin ningún campo de B; el
  switch fallido responde `403` y no crea ninguna fila con `tenant_id = B`
- **AND** ninguna escritura derivada de la sesión de A puede llevar `tenant_id = B` (ni `session`,
  ni `refresh_token`, ni `auth_event` con tenant B)

#### Scenario: S6.5 — Switch a un tenant con owner o billing exige step-up

- **WHEN** un usuario `professional` en A que también es `owner` (o `billing`) en B pide
  `switch-tenant(B)`
- **THEN** responde `403 mfa_required` si ya enroló MFA, o `403 mfa_enrollment_required` si no,
  con un desafío efímero y **sin** cookie de sesión de B
- **AND** la sesión de A sigue vigente hasta que `mfa/verify` (o `enroll/confirm`) complete el
  step-up; recién ahí se revoca A, se emite la sesión de B con `mfa_satisfied = true` y se
  devuelve `200`
- **AND** el `mfa_satisfied` de A no se reutiliza: la sesión de B nace `pendiente_mfa` hasta su
  propio step-up

#### Scenario: S6.6 — Un step-up de switch expirado no emite la sesión destino

- **WHEN** el desafío del switch a B (owner/billing) expira o se consume sin código válido
- **THEN** responde `401 mfa_step_up_expired`, la sesión de A sigue `200` y no existe una
  `session` `vigente` con `tenant_id = B`
- **AND** no se revocó ninguna familia de A por el intento fallido

### Requirement: Guarda de sesión y contrato de GET /api/v1/auth/me

Todo endpoint autenticado MUST exigir una sesión vigente y no revocada. Sin cookie, con cookie
inválida o manipulada, o con sesión revocada, MUST responder `401 not_authenticated` sin datos.
Si el access JWT tiene firma válida pero `exp` vencido, MUST responder `401 session_expired` para
que el cliente intente el refresh. Si la `credentials_version` de la sesión quedó atrás de la del
`user`, MUST responder `401 credentials_changed` y revocar esa sesión. `GET /api/v1/auth/me` MUST
devolver usuario, tenant activo, roles, estado de MFA y `permissions` —los permisos efectivos del
tenant activo calculados en el servidor según `platform-rbac`—, sin `password_hash`, `mfa_secret` ni
tokens. `permissions` MUST NOT aceptarse del cliente ni persistirse en el token: se recalcula en cada
respuesta de sesión (`login`, `refresh`, `switch-tenant`, MFA y `me`). El orden obligatorio es:
resolver acotado → `set_config('app.current_tenant', :tid, true)` → consulta de
`session`/`membership` bajo RLS → permisos.

#### Scenario: S7.1 — Sesión válida devuelve el perfil sin secretos

- **WHEN** se consulta `GET /api/v1/auth/me` con cookies de sesión válidas
- **THEN** responde `200` con `user` (id, email, nombre, apellido), `tenant` (id, slug,
  nombre_comercial), `roles`, `mfa_enrolled` y `permissions`
- **AND** el JSON serializado no contiene las claves `password_hash`, `mfa_secret`,
  `refresh_token` ni `access_token`

#### Scenario: S7.2 — Sin sesión o con sesión revocada no hay acceso

- **WHEN** se consulta `/api/v1/auth/me` sin cookie, o con la cookie de una sesión cerrada por
  logout
- **THEN** responde `401 not_authenticated` sin datos del usuario y sin emitir una sesión nueva

#### Scenario: S7.3 — Cookie manipulada, expirada o membership desactivada son fail-closed

- **WHEN** se altera un byte de la cookie de access, o el access JWT expiró, o la `membership` se
  desactiva después del login
- **THEN** la cookie manipulada responde `401 not_authenticated` sin error `500`; el access
  expirado responde `401 session_expired` y se resuelve con un refresh válido; y con la membership
  desactivada `/api/v1/auth/me` responde `401 not_authenticated` y la sesión queda revocada (no
  sigue operando con roles viejos)

#### Scenario: S7.4 — Una sesión con credencial vieja no accede a ningún endpoint

- **WHEN** el `user` cambió o reseteó su contraseña y una cookie de sesión emitida antes presenta
  una `session.credentials_version` menor que `user.credentials_version`
- **THEN** `require_auth` responde `401 credentials_changed`, marca `session.revoked_at` bajo el
  tenant de esa sesión y no ejecuta el endpoint
- **AND** el refresh de esa misma sesión responde `401 credentials_changed` y no rota el token

#### Scenario: S7.5 — Los permisos son de solo lectura y del tenant de la sesión

- **WHEN** un cliente envía un campo `permissions` o `roles` en el body de `login`, `refresh` o
  `switch-tenant`, o manipula la cookie de access
- **THEN** el campo enviado se ignora (o se rechaza por el DTO) y `permissions` se calcula
  exclusivamente desde las memberships activas del tenant resuelto
- **AND** ningún permiso del token ni de la respuesta pertenece a otro tenant del mismo usuario

### Requirement: Aislamiento RLS de las tablas de sesión (RN-TEN-02)

`session` y `refresh_token` MUST tener `tenant_id NOT NULL` con FK a `tenant`, RLS habilitada y
forzada, y política con `NULLIF(current_setting('app.current_tenant', true), '')::uuid`. Con
contexto A no se MUST leer ni modificar filas de B; sin contexto el resultado MUST ser 0 filas. La
lectura pre-contexto de `require_auth`/`refresh` MUST hacerse **solo** con las funciones
`SECURITY DEFINER` de `auth_resolver` (rol `NOLOGIN` con `BYPASSRLS`, funciones con
`SET search_path = pg_catalog, public`, `REVOKE ALL ... FROM PUBLIC` y `GRANT EXECUTE` solo a
`odontologia_app`, sin SQL dinámico y sin devolver PII ni hashes). `auth_event` y
`password_reset_token` son globales por diseño y MUST NOT exponerse por API; `auth_event` solo la
lee el test como superusuario y `password_reset_token` tiene grants por columna.

#### Scenario: S8.1 — Un tenant solo ve sus propias sesiones y refresh tokens

- **WHEN** con `SET ROLE odontologia_app` y `app.current_tenant = A` se consultan `session` y
  `refresh_token` con filas sembradas de A y B
- **THEN** se devuelven únicamente las filas de A

#### Scenario: S8.2 — Escritura cross-tenant rechazada por la política

- **WHEN** con contexto A se inserta o actualiza una `session` o `refresh_token` con
  `tenant_id = B`, o se borra por id una fila de B
- **THEN** el `INSERT`/`UPDATE` falla por `WITH CHECK` (SQLSTATE `42501`) y el `DELETE` afecta 0
  filas, sin cambiar nada en B

#### Scenario: S8.3 — Sin contexto de tenant la consulta es fail-closed

- **WHEN** una transacción nueva consulta `session` sin `set_config('app.current_tenant', …)`
- **THEN** devuelve 0 filas, sin error de cast aunque el GUC venga vacío

#### Scenario: S8.4 — Prueba de mutación del aislamiento con la receta de C-02

- **WHEN** se ejecuta el **mismo** `SELECT` sobre `session`/`refresh_token` como superusuario (sin
  `SET ROLE`, ve A y B) y como `odontologia_app` con `app.current_tenant = A` (ve solo A); o bien
  se hace `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` dentro de una transacción de test
- **THEN** la comparación demuestra que el verde depende de la política y no de un `WHERE`
  accidental; **dropear la política no es una mutación válida** porque con RLS `FORCE` y cero
  políticas PostgreSQL aplica default-deny (0 filas)
- **AND** la evidencia queda registrada en `docs/auth.md` (tarea 9.2)

#### Scenario: S8.5 — auth_event es append-only y no se lee por API

- **WHEN** el rol de aplicación intenta `UPDATE` o `DELETE` sobre `auth_event`, o cualquier
  endpoint de `platform-auth` responde
- **THEN** `UPDATE`/`DELETE` fallan por el trigger `BEFORE UPDATE OR DELETE` (SQLSTATE `55000`), el
  rol de app no tiene `SELECT` sobre la tabla y ninguna respuesta de la API contiene campos de
  `auth_event`
- **AND** el test que verifica el contenido de `auth_event` lo consulta como superusuario/rol de
  test, nunca como `odontologia_app`

#### Scenario: S8.6 — El aislamiento se sostiene en el camino HTTP

- **WHEN** la app corre conectada como `odontologia_app` y con la cookie de refresh de la sesión
  de B se intenta refrescar, leer `/auth/me` o hacer logout contra una sesión de A (y viceversa)
- **THEN** cada intento responde `401 not_authenticated` o `401 credentials_changed` sin emitir
  cookies y sin revocar ni modificar la sesión del otro tenant
- **AND** la sesión legítima del otro tenant sigue refrescando con `200` y el test no corre como
  superusuario

#### Scenario: S8.7 — El bypass del resolver está confinado a sus funciones

- **WHEN** se inspeccionan los privilegios del rol `odontologia_app` y de `auth_resolver`
- **THEN** `odontologia_app` no puede leer `session`/`refresh_token` sin contexto (0 filas) pero
  sí ejecuta `auth_resolve_session_by_sid`/`auth_resolve_session_by_refresh`
- **AND** las funciones son `SECURITY DEFINER`, su owner es `auth_resolver`, tienen
  `search_path = pg_catalog, public`, no tienen `EXECUTE` para `PUBLIC`, no usan SQL dinámico y
  sus columnas de retorno son solo `session_id`, `tenant_id`, `user_id`, `expires_at`,
  `revoked_at` y `credentials_version`
