# Design — c-03-auth-sessions

## Context

C-02 dejó el sustrato que este change consume y no redefine: `tenant`, `user` (global, sin RLS) y
`membership` (tenant-scoped, RLS `FORCE`) con los 9 roles; `set_tenant_context` con
`set_config('app.current_tenant', :tenant_id, true)`; `tenant_id_from_claims` como función pura
(RN-TEN-03); el rol `odontologia_app` (`NOLOGIN NOSUPERUSER NOBYPASSRLS`) y el hábito de test de
hacer `SET ROLE odontologia_app`. No existe ninguna tabla de sesión, ni hashing de passwords, ni
endpoints de negocio, ni **cliente HTTP** en el frontend. El router base **sí existe**:
`frontend/src/main.tsx` monta `BrowserRouter` y `frontend/src/App.tsx` ya define `<Routes>`; este
change lo **extiende** con `/login` y la ruta protegida, no lo crea.

Restricciones que mandan sobre el diseño: governance **CRÍTICO**; DD-10 (JWT en cookie
`httpOnly`, nunca `localStorage`); RN-AU-01..05 y RN-AU-07; RN-TEN-02/03/05/06; Postgres real en
los tests (sin mocks de DB); `mypy --strict` sin `Any` en dominio; vertical slice (API + pantalla).
SU-01 (1 dev) y SU-02 (deadline 2026-10-23) obligan a no inventar infraestructura que no exista:
no hay proveedor de email ni KMS provisionado. Redis **sí** está en el stack, en Testcontainers y
en `REDIS_URL`, y se usa acotado al desafío MFA.

Ver `proposal.md` § Why para la motivación; las specs de `platform-auth` son el contrato y este
documento explica cómo se cumple.

## Goals / Non-Goals

**Goals**
- Un único punto de verdad para "quién es el usuario y en qué tenant opera": `require_auth`
  (resolver acotado → `set_config`) → `require_tenant` (membership bajo RLS) → endpoint.
- Ciclo de sesión completo y verificable con Postgres real: login, refresh rotativo con familias,
  reuse detection, logout, switch de tenant, invalidación por cambio de credencial.
- Credenciales y secretos con estándares actuales: Argon2id, TOTP cifrado en reposo, tokens
  opacos hasheados en BD, cookies sin lectura desde JS.
- Primer vertical slice demostrable: pantalla de login + guarda de rutas + restauración de sesión,
  con e2e ejecutable contra backend real.

**Non-Goals**
- RBAC/`require_role` y matriz de permisos (C-04): acá los roles solo viajan en la sesión.
- Enumerar memberships o sesiones de un usuario sin tenant (se evita por diseño, ver D4/D7).
- Rotación de claves del secreto TOTP, KMS por tenant, `audit_log` completo (C-14), rate limit
  por IP, CAPTCHA, OAuth/SSO, portal del paciente.

## Decisions

### D1 — Tres cookies, ninguna legible por JavaScript (DD-10 / RN-AU-02)

| Cookie | Contenido | TTL | Atributos |
|--------|-----------|-----|-----------|
| `odontologia_access` | JWT (`HS256`, `SESSION_SECRET`) con `sub`, `sid`, `tenant_id`, `mfa`, `iat`, `exp` | 15 min | `HttpOnly`, `SameSite=Lax`, `Secure`, `Path=/` |
| `odontologia_refresh` | token opaco de 32 bytes (base64url), **hasheado** (SHA-256) en BD | 12 h absolutas desde el login | `HttpOnly`, `SameSite=Lax`, `Secure`, `Path=/api/v1/auth` |
| `odontologia_mfa` | id opaco de desafío (32 bytes), sin PII | 5 min | `HttpOnly`, `SameSite=Lax`, `Secure`, `Path=/api/v1/auth/mfa` |

Ni el access ni el refresh se devuelven en el body: el SPA no puede leerlos (ni por accidente ni
por XSS). `Secure` se controla con `COOKIE_SECURE` (default `true`; `false` solo en `local`/`test`
porque TestClient habla HTTP). `SameSite=Lax` + verificación de `Origin` en los métodos con
efecto (login, refresh, logout, switch-tenant, mfa) cubren CSRF sin token CSRF adicional.

La sesión normal dura **12 h absolutas** (RN-AU-08: 12 h para un usuario normal vs. 4 h del
SuperAdmin, que está fuera de alcance). El refresh **no extiende** la sesión: `expires_at` de cada
refresh es el de su `session`. El access de 15 min se renueva con refresh mientras la sesión viva.

- Alternativas: (a) access en `Authorization: Bearer` + refresh en memoria → el access queda
  accesible a JS y se pierde al recargar; (b) `localStorage` → descartado por DD-10; (c) cookie de
  sesión opaca única sin JWT → válida, pero DD-10 pide JWT y el access corto evita pegarle a la
  BD en cada request.
- Trade-off aceptado: con `SameSite=Lax` el SPA y la API deben ser mismo sitio. En dev se cumple
  con **Vite proxy** `server.proxy['/api']` (D10); en producción, reverse proxy same-site. Si se
  separan dominios habrá que pasar a `SameSite=None` + `Secure` y token CSRF.

### D2 — Refresh opaco, resolución pre-contexto y rotación atómica

El refresh token es opaco: no lleva tenant, no es JWT y la RLS de `session`/`refresh_token` es
`FORCE`. Por eso el endpoint **no puede** hacer `SELECT` directo antes de saber el tenant. El
flujo es:

1. Leer la cookie `odontologia_refresh`, hashear y llamar
   `auth_resolve_session_by_refresh(:token_hash)` (función acotada, D4). Si devuelve 0 filas →
   `401 not_authenticated` (misma respuesta si el token no existe o pertenece a otro tenant).
2. Validar el estado temporal devuelto (`revoked_at`, `expires_at`) y
   `session.credentials_version` contra `user.credentials_version` (tabla global).
3. `set_config('app.current_tenant', :tenant_id, true)` con el tenant devuelto por el resolver.
4. Recién ahora consultar `refresh_token WHERE token_hash=:h` bajo RLS y rotar:

   ```sql
   UPDATE refresh_token
      SET estado = 'rotado', used_at = now(), replaced_by = :nuevo
    WHERE token_hash = :h AND estado = 'activo' AND expires_at > now()
   RETURNING id, family_id, session_id, tenant_id;
   ```

   **El que gana el `UPDATE` rota; el que no, no puede rotar.** Si la fila existe y está
   `rotado`, es un reuso: `UPDATE ... SET estado='revocado' WHERE family_id=:f` +
   `session.revoked_at = now()` y `401 refresh_reuse`. Si ya está `revocado` (logout o familia
   cerrada por un reuso anterior), responde `401 not_authenticated` sin volver a revocar nada.
5. Emitir el refresh nuevo con el **mismo `family_id`** y `expires_at = session.expires_at`; emitir
   access nuevo. La rotación no extiende la vida de la sesión.
6. **Logout idempotente**: resuelve la sesión por la cookie de access o, si el access ya venció,
   por el hash del refresh con el resolver. Si no hay fila o la sesión ya está revocada, limpia
   las cookies y responde `204` igual; no usa `require_auth` estricto.

Estados explícitos de un refresh:

| Estado | Condición |
|--------|-----------|
| `activo` | `estado = 'activo' AND expires_at > now()` |
| `expirado` | `estado = 'activo' AND expires_at <= now()` |
| `rotado` | `estado = 'rotado' AND used_at IS NOT NULL AND replaced_by IS NOT NULL` |
| `revocado` | `estado = 'revocado'` (terminal) |

Estados de una sesión (derivados, sin columna `estado`):

| Estado | Condición |
|--------|-----------|
| `pendiente_mfa` | `mfa_satisfied = false AND revoked_at IS NULL AND expires_at > now()` |
| `vigente` | `mfa_satisfied = true AND revoked_at IS NULL AND expires_at > now()` |
| `revocada` | `revoked_at IS NOT NULL` |
| `expirada` | `revoked_at IS NULL AND expires_at <= now()` |

Consecuencia asumida de la concurrencia: dos requests con el mismo refresh hacen que el perdedor
sea tratado como reuso y revoque la familia (fail-closed). El cliente web lo evita con
*single-flight* (D10); se prefiere un logout ocasional ante una ventana de gracia que permitiría a
un atacante con el token viejo seguir refrescando.

- Alternativas: (a) refresh JWT sin estado → no hay detección de reuso posible (RN-AU-03 lo
  exige); (b) tabla de lookup no-RLS con hash + tenant → duplica el dato y amplía la superficie;
  (c) tenant firmado en la cookie → el token deja de ser opaco y hay que rotar la firma. Se elige
  el resolver `SECURITY DEFINER` acotado (D4).
- El TTL del refresh es **absoluto desde el login** (la rotación no lo extiende) y coincide con el
  de la sesión: 12 h. Evita sesiones eternas y hace el test de expiración trivial.

### D3 — El login resuelve el tenant por `slug`, antes del contexto (RN-TEN-03/05/06)

`POST /api/v1/auth/login` recibe `{tenant_slug, email, password}`. Flujo:

1. Normalizar email (`citext` en `user`, sin RLS) y verificar el password Argon2id.
2. Resolver `tenant` por `slug` (sin RLS, igual que en C-02) y mirar `tenant.estado`. Si está
   `suspended`, responder `403 tenant_not_available` sin sesión y registrar `auth_event` con
   `detail.reason = "tenant_suspended"` (RN-TEN-06).
3. Abrir transacción, `set_config('app.current_tenant', tenant.id, true)` y consultar `membership`
   activa del usuario en ese tenant. RLS aplica normal: solo ve la membresía de ese tenant.
4. Resolver los roles del usuario **en ese tenant**. Si alguno es `owner`/`billing`, la sesión
   nace `pendiente_mfa` (`mfa_satisfied = false`), se crea el desafío (D5) y se responde `403
   mfa_required`/`mfa_enrollment_required` sin cookies de sesión. Si no requiere MFA, la sesión
   nace `vigente` (`mfa_satisfied = true`), se crea la primera fila `refresh_token` y se emiten
   cookies.
5. Registrar `auth_event` de éxito/fallo, todo en la misma transacción.

Por qué esto **no** viola RN-TEN-03: en el login todavía no hay sesión, y el `tenant_slug` no es
el tenant de una operación autenticada sino el ámbito al que se pide entrar; la autorización real
la da la `membership`. Si el usuario tiene memberships en A y B y pide B, la sesión queda en B y no
en A (S1.4). Desde el primer request autenticado en adelante, el `tenant_id` sale
**exclusivamente** de `sid`/claims y cualquier `tenant_id` del body/query se ignora (S6.3), salvo
el destino explícito de `switch-tenant` (D4.3).

- Alternativas descartadas: (a) login solo con email y resolver memberships sin contexto → con
  RLS `FORCE` `membership` devuelve 0 filas (fail-closed), y saltearla requiere `BYPASSRLS` o
  `SECURITY DEFINER`; (b) función `SECURITY DEFINER` que enumere memberships de un `user_id` →
  bypass más amplio que el necesario para v1; el resolver de D4 solo resuelve una sesión/token
  existente; (c) tenant por `Host`/subdominio → correcto en producción pero difícil de testear con
  TestClient y de operar en dev; el `slug` en el body es explícito y el frontend lo deriva del
  subdominio (o de `VITE_DEFAULT_TENANT_SLUG` en dev). El día que haya subdominios reales, el
  borde puede completar `tenant_slug` desde el `Host` sin cambiar la spec.

### D4 — RLS, resolver acotado y credencial (RN-TEN-02 / B1)

#### D4.1 — Dónde va RLS y dónde no

| Tabla | `tenant_id` | RLS | Justificación |
|-------|-------------|-----|---------------|
| `session` | `NOT NULL`, FK | `ENABLE` + `FORCE` + política | Dato de negocio: una sesión pertenece a un tenant |
| `refresh_token` | `NOT NULL`, FK | `ENABLE` + `FORCE` + política | Ídem; permite revocar por familia por tenant |
| `auth_event` | nullable | **sin** RLS, append-only | Se escribe **antes** de resolver tenant (email inexistente, lockout, fallo de MFA); no se lee por API |
| `password_reset_token` | sin `tenant_id` | **sin** RLS | El password es global al `user` (C-02); un token tenant-scoped sería una tenancy falsa |

Las políticas son idénticas a las de C-02, con `USING` y `WITH CHECK`:

```sql
USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
```

`auth_event` tiene trigger `BEFORE UPDATE OR DELETE` que lanza excepción y el rol de app recibe
solo `INSERT` (no `SELECT`). `password_reset_token` se consulta por hash exacto y el rol de app
recibe grants **por columna** (D8), no un `SELECT` amplio. El test cross-tenant obligatorio se
aplica a las dos tablas tenant-scoped (`session`, `refresh_token`), que son las que expone la API,
a nivel SQL **y** a nivel endpoint (S8.6).

#### D4.2 — El resolver pre-contexto (B1)

La RLS `FORCE` no permite leer `session`/`refresh_token` antes de conocer el tenant. Para no
aflojar la RLS ni agregar una tabla espejo, la migración crea:

- Rol **`auth_resolver`**: `NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS`.
  No se usa para conectarse: solo es dueño de dos funciones `SECURITY DEFINER`.
- `auth_resolve_session_by_sid(p_sid uuid)` → `session_id, tenant_id, user_id, expires_at,
  revoked_at, credentials_version`.
- `auth_resolve_session_by_refresh(p_token_hash text)` → los mismos campos, resolviendo
  `refresh_token → session`.

Requisitos obligatorios de ambas funciones:

- `SECURITY DEFINER` y owner `auth_resolver` (el bypass queda dentro de la función).
- `SET search_path = pg_catalog, public` (sin `pg_temp`).
- `REVOKE ALL ON FUNCTION ... FROM PUBLIC` y `GRANT EXECUTE` **solo** a `odontologia_app`.
- Sin SQL dinámico (`EXECUTE format(...)`, `EXECUTE '...'`).
- Devuelven **solo** los seis campos listados: ni email, ni `password_hash`, ni `mfa_secret`, ni
  hashes de refresh, ni `detail` de eventos.
- Si no encuentran fila devuelven 0 filas; el borde responde `401 not_authenticated` **sin
  filtrar** si la sesión existe en otro tenant.

La RLS sigue `FORCE` en `session`/`refresh_token`: el bypass está confinado a las funciones y el
rol de app no puede hacer `SELECT` directo sin contexto (devuelve 0 filas, S8.3/S8.7).

#### D4.3 — Orden exacto de `require_auth` → `require_tenant` (y `switch-tenant`)

`require_auth` (dependencia en `backend/app/api/v1/deps.py`):

1. Leer `odontologia_access`. Sin cookie o firma inválida → `401 not_authenticated`; firma válida
   con `exp` vencido → `401 session_expired`.
2. Llamar `auth_resolve_session_by_sid(:sid)`. 0 filas → `401 not_authenticated`.
3. Rechazar si `revoked_at IS NOT NULL` o `expires_at <= now()` → `401 not_authenticated`.
4. `set_config('app.current_tenant', :tenant_id, true)` con el tenant devuelto por el resolver.
5. Bajo RLS, cargar `session WHERE id = :sid` y el `user` global; si
   `session.credentials_version < user.credentials_version` → marcar `session.revoked_at` (escritura
   tenant-scoped permitida por el GUC) y `401 credentials_changed`.
6. `require_tenant` valida la `membership` activa del `user` en el tenant con el GUC ya seteado. Si
   no está activa → revocar la sesión y `401 not_authenticated`.
7. Recién entonces el endpoint corre.

`require_auth` y `require_tenant` comparten el **mismo `Session`/transacción** del request: el
`set_config(..., true)` es transaction-local y no debe haber commit entre el paso 4 y las
consultas. El endpoint no recibe el `tenant_id` del cliente: lo toma del claim y lo revalida con
la sesión y la membership.

`switch-tenant` es la **única excepción**: lee el tenant destino del body, abre un savepoint,
fija el GUC del destino, valida `membership` activa y roles, y restaura el GUC de la sesión
original si no hay step-up. Un destino sin membership → `403 tenant_not_available` sin tocar A. Un
destino con `owner`/`billing` → desafío de step-up (D5), sin sesión nueva y sin revocar A hasta que
el step-up complete (S6.5/S6.6).

#### D4.4 — Invalidación por credencial, no por barrido de tenants

Resetear/cambiar la contraseña **no** enumera tenants ni escribe `session` cross-tenant. Se agrega
`user.credentials_version int NOT NULL DEFAULT 0` (tabla global, sin RLS). Al cambiar/resetear la
password se hace `UPDATE "user" SET password_hash=:h, credentials_version = credentials_version + 1`
en la misma transacción. Cada `session` guarda la versión con la que se emitió; `require_auth` y
`refresh` la comparan contra `user.credentials_version` y, si quedó atrás, responden
`401 credentials_changed` (y revocan esa sesión bajo su tenant). No hay escritura cross-tenant y no
hace falta bypass. Lo mismo aplica en `refresh`.

### D5 — TOTP cifrado, replay y desafío efímero

`user.mfa_secret` ya existe desde C-02. Se guarda **cifrado** con `Fernet` (`cryptography`) usando
una clave derivada por HKDF-SHA256 de `MFA_ENCRYPTION_KEY` con `info = "mfa:<key_version>"`. Se
agregan `mfa_enrolled_at` y `mfa_secret_key_version` para rotar la clave sin adivinar con qué
versión se cifró cada fila. El alta del secreto ocurre en `enroll/confirm` (nunca se persiste un
secreto sin confirmar un código); el `otpauth://` se devuelve **una sola vez** al cliente y no se
loguea. `GET /api/v1/auth/me` solo devuelve el booleano `mfa_enrolled`.

**Replay TOTP (dos niveles):**

- `user.last_totp_step bigint NULL` es la **barrera global por credencial**: antes de aceptar un
  código se ejecuta
  `UPDATE "user" SET last_totp_step = :step WHERE id = :uid AND (last_totp_step IS NULL OR last_totp_step < :step)`
  y se exige que haya actualizado una fila. Dos requests concurrentes con el mismo código no
  pueden ganar ambos.
- `session.last_used_step bigint NULL` registra el paso aceptado para esa sesión (auditoría y
  rechazo explícito del replay en la misma sesión).

**Desafío efímero (Redis, `GETDEL` atómico):**

- Clave `auth:mfa:challenge:<challenge_id>` con TTL 300 s; valor JSON mínimo:
  `{purpose, pending_session_id, source_session_id?, user_id, tenant_id}`. Sin secretos ni PII.
- `purpose ∈ {login_verify, login_enroll, switch_verify, switch_enroll}`.
- La cookie `odontologia_mfa` lleva solo el `challenge_id` (opaco, `HttpOnly`,
  `Path=/api/v1/auth/mfa`, `Secure` salvo local/test, `Max-Age=300`).
- `mfa/verify` (y `enroll/confirm`) hacen `GETDEL` **antes** de validar el código: el desafío es de
  un solo uso. Un código incorrecto consume el desafío (fail-closed) y el usuario debe reiniciar
  el login; el fallo incrementa el lockout de la cuenta. Esto evita reintentos dentro del mismo
  desafío y hace verificable el "un solo uso".
- Si Redis no responde → `503 mfa_unavailable`, sin cookie de desafío ni de sesión; no se guarda
  estado en memoria del proceso (S4.6).
- En login, la `session` se crea en estado `pendiente_mfa` (sin cookies de sesión). En
  `switch-tenant` con `owner`/`billing`, el `pending_session_id` es la sesión de B y
  `source_session_id` es la de A: al completar el step-up se revoca A y se emiten las cookies de B.
- `mfa/verify` fija el GUC con el `tenant_id` del payload **antes** de actualizar la sesión
  pendiente. En `switch_*` el orden es: `GETDEL` → validar TOTP y actualizar `user.last_totp_step`
  → `set_config(A)` y revocar `source_session_id` → `set_config(B)`, marcar `pending_session_id`
  con `mfa_satisfied = true` y `last_used_step` → commit → cookies de B. Si algo falla, rollback y
  A sigue vigente.
- `mfa_satisfied` es por sesión y por tenant: la sesión de B nace `false` aunque A haya completado
  MFA; un factor satisfecho en A no habilita B (S6.5).

> **Ajustes de implementación (apply).**
> - `switch-tenant` usa `require_tenant` (A) y pasa al servicio `user_id`, `source_session_id` y
>   `source_tenant_id`; el servicio fija el GUC del destino, lee `_roles_of` bajo RLS y, si no hay
>   membership, hace `rollback()` y restaura el contexto de A antes del `403`.
> - Con `owner`/`billing` el servicio crea la `session` pendiente de B y el desafío en la misma
>   transacción (commit) y responde el 403 con `Set-Cookie`; `enroll/start` acepta también
>   `switch_enroll` y re-emite el desafío conservando el `purpose` y el `source_session_id`.
> - `verify_mfa`/`confirm_mfa_enrollment` revocan A (refresh + `session.revoked_at`) **después** de
>   validar el TOTP y antes de completar B, cambiando el GUC A → B dentro de la misma transacción.
>   Un fallo deja A intacta y la sesión pendiente de B sin refresh (no usable): no hay sesión
>   `vigente` con tenant B (S6.6).

> **Ajustes de implementación (apply).**
> - La sesión `pendiente_mfa` se representa con `session.mfa_satisfied = false` (no hay columna
>   `estado` nueva); no tiene `refresh_token` hasta que el step-up se completa, y `require_auth`
>   la rechaza aunque alguien fabricara un access.
> - El secreto del alta en curso vive en `auth:mfa:enroll:<challenge_id>` (TTL 300, `GETDEL`) y
>   nunca se escribe en `user.mfa_secret` antes de confirmar. `enroll/start` consume el desafío de
>   login y emite uno nuevo con el mismo `pending_session_id`, así el alta también es de un solo uso.
> - El `UPDATE ... WHERE last_totp_step IS NULL OR last_totp_step < :step` se ejecuta con
>   `rowcount == 1` como única condición de aceptación; los fallos de MFA usan la misma máquina de
>   lockout del login y registran `mfa_fail` (y `lockout` en el quinto).
> - El 403 de `mfa_required`/`mfa_enrollment_required` lleva el `Set-Cookie` del desafío: `AuthError`
>   admite `extra_headers` y el handler global los reenvía sin tocar el body.

- Alternativa: KMS por tenant (KB `08` § Datos sensibles) → no hay KMS provisionado en v1 y el
  secreto TOTP no es dato clínico; la columna de versión deja la migración a KMS como deuda
  explícita (open question).
- Alternativa: TOTP en claro → inaceptable incluso en dev (un dump de BD filtraría segundos
  factores).
- Alternativa: desafío en la propia `session`/BD → el `GETDEL` atómico y el TTL de Redis son más
  simples y ya están en el stack; una fila de desafío requeriría cleanup y otra migración.

### D6 — Lockout como estado del `user`, no como contador en Redis

Columnas en `user`: `failed_login_count` (0..5), `lockout_strikes` (bloqueos consecutivos),
`locked_until` y `last_lockout_at`. Máquina de estados:

| Estado | Condición | Efecto en login |
|--------|-----------|-----------------|
| `NORMAL` | `locked_until IS NULL OR locked_until <= now()` | verifica credenciales |
| `LOCKED` | `locked_until > now()` | `423 locked` + `Retry-After` en segundos |
| `RESET` | login correcto | `failed_login_count = 0`, `lockout_strikes = 0` |

Al 5.º fallo: `lockout_strikes += 1`, `locked_until = now() + 15 min * 2^(strikes-1)` (tope 24 h).
El incremento se hace con `UPDATE ... SET failed_login_count = failed_login_count + 1 ...
RETURNING` para que sea atómico frente a intentos concurrentes. La verificación de `LOCKED` ocurre
**antes** de comparar el password, así una cuenta bloqueada no filtra si el password era correcto
por timing ni por respuesta. Los fallos de MFA cuentan para el mismo lockout (S4.2).

> **Ajuste de implementación (apply).** La atomicidad se logra con
> `SELECT ... FROM "user" WHERE email = :email FOR UPDATE` al inicio del login: la fila queda
> bloqueada durante la transacción y los contadores se recalculan con las funciones puras de
> `app/domain/auth/lockout.py` antes del `commit()`. El efecto observable es el mismo que el
> `UPDATE ... RETURNING` (dos intentos concurrentes no pueden perder un fallo) pero la exponencial
> y las transiciones viven en un solo lugar testeado, sin duplicarlas en SQL.

- Alternativas: contador en Redis → agrega una dependencia obligatoria al login (Redis ya se usa
  para MFA, pero el lockout no debe depender de que Redis esté arriba) y pierde estado si Redis se
  cae; tabla de intentos con `count(*)` → más filas y una consulta con RLS/tenant que no aplica
  antes de autenticar.
- `auth_event` se escribe siempre (éxito y fallo), con `tenant_id` cuando se conoce y
  `detail jsonb` sin secretos (`reason`, `ip`, `user_agent`, `family_id` cuando aplica). Reemplaza
  al `audit_log` de RN-AU-05 en este change (C-14 decide la proyección definitiva).

### D7 — Token de recuperación: opaco, hasheado, un solo uso + invalidación por credencial

`forgot-password` genera 32 bytes (`secrets.token_urlsafe(32)`), guarda `sha256(token)` en
`password_reset_token` con `expires_at = now() + 30 min` y responde `202` siempre. El consumo es:

```sql
UPDATE password_reset_token
   SET used_at = now()
 WHERE token_hash = :h AND used_at IS NULL AND expires_at > now()
RETURNING user_id;
```

Si no devuelve fila, `400 invalid_or_expired_token`. El consumo, el cambio de `password_hash` y el
incremento de `user.credentials_version` van en la misma transacción. **No** se enumeran ni se
actualizan sesiones: las sesiones viejas quedan invalidadas por credencial y fallan en su próximo
uso con `401 credentials_changed` (D4.4). Dos resets concurrentes con el mismo token: solo uno
gana el `UPDATE` (S5.5).

Exposición del token: solo con `ENVIRONMENT in {local, development, test}` se agrega `token` al
body y se registra como `auth_event.detail` (nunca `logging.info` del token fuera de desarrollo).
Sin proveedor de email (PQ-08 abierta, ver Open Questions). Fuente de la regla: token de un solo
uso, 30 min, `03_actores_y_roles.md:90`; no hay RN específica de reset.

- Alternativas: JWT de reset → no revocable antes de expirar y sin garantía de un solo uso; token
  en claro en BD → un dump permite resetear cuentas.

> **Ajustes de implementación (apply).**
> - El token se genera con `new_opaque_token()` (los mismos 32 bytes de `secrets.token_urlsafe`),
>   y el consumo es `UPDATE password_reset_token ... RETURNING user_id` seguido de
>   `UPDATE "user" SET password_hash = :h, credentials_version = credentials_version + 1
>   RETURNING id` en la misma transacción; si el segundo `UPDATE` no devuelve fila, rollback (el
>   token no queda marcado).
> - `forgot-password` responde `202` (`{"token": "..."}` solo donde se expone) y `reset-password`
>   responde `200` con `{"status": "ok"}`; el DTO `ForgotPasswordResponse` usa
>   `response_model_exclude_none=True`, así que en `production` el campo `token` **no aparece**
>   en el JSON (no es `null`), y S5.3 compara cuerpos idénticos.
> - El `auth_event.detail` del pedido incluye el token **solo** en `local`/`development`/`test`;
>   no hay `logging.*` del token en ningún entorno.
> - El rol de app ya tenía grants por columna en `003_auth` (`SELECT` sin `created_at`,
>   `UPDATE (used_at)`); el test de 6.1 los fija como contrato y verifica que no puede reescribir
>   `token_hash` ni borrar filas.

### D8 — Migración `003_auth` (DDL completo)

Orden: tipos → columnas nuevas en `user` → tablas → índices/constraints → rol y funciones del
resolver → grants → trigger append-only → RLS + políticas. `down_revision = "002_core_tenancy"`.

#### D8.1 — Tipos y columnas de `user`

```sql
CREATE TYPE refresh_estado AS ENUM ('activo', 'rotado', 'revocado');
CREATE TYPE auth_event_tipo AS ENUM (
  'login_success', 'login_fail', 'lockout', 'logout',
  'refresh_rotated', 'refresh_reuse',
  'mfa_success', 'mfa_fail', 'mfa_enroll', 'mfa_step_up_issued',
  'password_reset_request', 'password_reset', 'switch_tenant'
);

ALTER TABLE "user"
  ADD COLUMN failed_login_count smallint NOT NULL DEFAULT 0
    CHECK (failed_login_count BETWEEN 0 AND 5),
  ADD COLUMN lockout_strikes smallint NOT NULL DEFAULT 0
    CHECK (lockout_strikes >= 0),
  ADD COLUMN locked_until timestamptz NULL,
  ADD COLUMN last_lockout_at timestamptz NULL,
  ADD COLUMN mfa_enrolled_at timestamptz NULL,
  ADD COLUMN mfa_secret_key_version smallint NULL,
  ADD COLUMN credentials_version integer NOT NULL DEFAULT 0
    CHECK (credentials_version >= 0),
  ADD COLUMN last_totp_step bigint NULL;
```

#### D8.2 — `session`

```sql
CREATE TABLE session (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  tenant_id           uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  credentials_version integer NOT NULL,
  mfa_satisfied       boolean NOT NULL DEFAULT false,
  last_used_step      bigint NULL,
  expires_at          timestamptz NOT NULL,
  revoked_at          timestamptz NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  CHECK (expires_at > created_at)
);

CREATE INDEX session_tenant_user_idx ON session (tenant_id, user_id);
CREATE INDEX session_expires_at_idx  ON session (expires_at);
```

Estados derivados: `pendiente_mfa`, `vigente`, `revocada`, `expirada` (tabla de D2).

#### D8.3 — `refresh_token`

```sql
CREATE TABLE refresh_token (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  uuid NOT NULL REFERENCES session(id) ON DELETE CASCADE,
  tenant_id   uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  family_id   uuid NOT NULL,
  token_hash  text NOT NULL UNIQUE,
  estado      refresh_estado NOT NULL DEFAULT 'activo',
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz NULL,
  replaced_by uuid NULL REFERENCES refresh_token(id) ON DELETE SET NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (replaced_by IS NULL OR replaced_by <> id),
  CHECK (estado <> 'rotado' OR (used_at IS NOT NULL AND replaced_by IS NOT NULL))
);

CREATE INDEX refresh_token_family_idx        ON refresh_token (family_id);
CREATE INDEX refresh_token_tenant_session_idx ON refresh_token (tenant_id, session_id);
CREATE INDEX refresh_token_expires_at_idx    ON refresh_token (expires_at);
```

#### D8.4 — `auth_event` (append-only, sin RLS)

```sql
CREATE TABLE auth_event (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tipo       auth_event_tipo NOT NULL,
  user_id    uuid NULL REFERENCES "user"(id) ON DELETE SET NULL,
  tenant_id  uuid NULL REFERENCES tenant(id) ON DELETE SET NULL,
  detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX auth_event_tenant_created_idx ON auth_event (tenant_id, created_at);
CREATE INDEX auth_event_user_created_idx   ON auth_event (user_id, created_at);

CREATE FUNCTION auth_event_forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'auth_event is append-only' USING ERRCODE = '55000';
END;
$$;
REVOKE ALL ON FUNCTION auth_event_forbid_mutation() FROM PUBLIC;

CREATE TRIGGER auth_event_append_only
  BEFORE UPDATE OR DELETE ON auth_event
  FOR EACH ROW EXECUTE FUNCTION auth_event_forbid_mutation();
```

Quién la lee: **solo** el superusuario/migrador y los tests que consultan como superusuario (o rol
de test con privilegio explícito); `odontologia_app` **no** tiene `SELECT`. No se expone por API.

**Ajuste de implementación (apply):** el trigger deja pasar el `UPDATE` que dispara una acción
referencial interna (`ON DELETE SET NULL` de `user`/`tenant`) usando `pg_trigger_depth() > 1`.
Sin esto, borrar un usuario o un tenant con eventos fallaba con `55000` y la FK quedaba
inutilizable. No abre una vía externa: el rol de app solo tiene `INSERT` sobre `auth_event` y no
puede anidar triggers; el `UPDATE`/`DELETE` directo (incluso como superusuario) sigue fallando con
`55000` (test `test_auth_event_cannot_be_updated_or_deleted_even_by_superuser`).

#### D8.5 — `password_reset_token`

```sql
CREATE TABLE password_reset_token (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  used_at    timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX password_reset_token_user_idx       ON password_reset_token (user_id);
CREATE INDEX password_reset_token_expires_at_idx ON password_reset_token (expires_at);
```

#### D8.6 — Rol `auth_resolver` y funciones `SECURITY DEFINER`

```sql
CREATE ROLE auth_resolver NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
GRANT USAGE ON SCHEMA public TO auth_resolver;
GRANT SELECT (id, tenant_id, user_id, expires_at, revoked_at, credentials_version)
  ON session TO auth_resolver;
GRANT SELECT (session_id, tenant_id, token_hash)
  ON refresh_token TO auth_resolver;

CREATE FUNCTION auth_resolve_session_by_sid(p_sid uuid)
RETURNS TABLE (
  session_id uuid, tenant_id uuid, user_id uuid,
  expires_at timestamptz, revoked_at timestamptz, credentials_version integer
)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT s.id, s.tenant_id, s.user_id, s.expires_at, s.revoked_at, s.credentials_version
  FROM public.session s
  WHERE s.id = p_sid;
$$;

CREATE FUNCTION auth_resolve_session_by_refresh(p_token_hash text)
RETURNS TABLE (
  session_id uuid, tenant_id uuid, user_id uuid,
  expires_at timestamptz, revoked_at timestamptz, credentials_version integer
)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT s.id, s.tenant_id, s.user_id, s.expires_at, s.revoked_at, s.credentials_version
  FROM public.refresh_token rt
  JOIN public.session s ON s.id = rt.session_id
  WHERE rt.token_hash = p_token_hash;
$$;

ALTER FUNCTION auth_resolve_session_by_sid(uuid) OWNER TO auth_resolver;
ALTER FUNCTION auth_resolve_session_by_refresh(text) OWNER TO auth_resolver;
REVOKE ALL ON FUNCTION auth_resolve_session_by_sid(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION auth_resolve_session_by_refresh(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_resolve_session_by_sid(uuid) TO odontologia_app;
GRANT EXECUTE ON FUNCTION auth_resolve_session_by_refresh(text) TO odontologia_app;
```

No hay SQL dinámico ni columnas de PII/hash en el retorno.

#### D8.7 — Grants y RLS

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON session, refresh_token TO odontologia_app;
GRANT INSERT ON auth_event TO odontologia_app;
GRANT USAGE ON SEQUENCE auth_event_id_seq TO odontologia_app;

-- password_reset_token: grants por columna (no SELECT amplio)
GRANT SELECT (id, user_id, token_hash, expires_at, used_at)
  ON password_reset_token TO odontologia_app;
GRANT INSERT (id, user_id, token_hash, expires_at, used_at, created_at)
  ON password_reset_token TO odontologia_app;
GRANT UPDATE (used_at) ON password_reset_token TO odontologia_app;

ALTER TABLE session ENABLE ROW LEVEL SECURITY;
ALTER TABLE session FORCE ROW LEVEL SECURITY;
CREATE POLICY session_tenant_isolation ON session
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE refresh_token ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_token FORCE ROW LEVEL SECURITY;
CREATE POLICY refresh_token_tenant_isolation ON refresh_token
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
```

`DELETE` se otorga porque los tests de aislamiento necesitan comprobar que un `DELETE` cross-tenant
afecta 0 filas; la aplicación no borra sesiones (las revoca con `UPDATE`).

#### D8.8 — Downgrade

`DROP TRIGGER`/función append-only → `DROP FUNCTION` del resolver → `DROP OWNED BY auth_resolver` →
`DROP ROLE auth_resolver` → `DROP TABLE password_reset_token, auth_event, refresh_token, session`
(en orden de FK) → `ALTER TABLE "user" DROP COLUMN ...` → `DROP TYPE auth_event_tipo,
refresh_estado`. No toca `002`. El rol es un objeto de clúster: el test de reversibilidad corre en
su propio contenedor (igual que C-02).

No hay backfill: no existen usuarios con password en producción (los del seed/test son ficticios).
Si existieran, quedarían con `failed_login_count = 0`, `credentials_version = 0` y sin MFA, que es
un estado válido para roles que no lo exigen.

### D9 — Contrato de errores, códigos y guardas

Códigos estables en el body (`{"code": "...", "message": "..."}`) para que el frontend no dependa
de strings:

| `code` | HTTP | Endpoint / condición |
|--------|------|----------------------|
| `invalid_credentials` | 401 | login: password/email/usuario/membership inválidos |
| `not_authenticated` | 401 | `require_auth`/refresh: cookie ausente, firma inválida, sesión revocada/expirada o inexistente |
| `session_expired` | 401 | `require_auth`: access JWT con firma válida y `exp` vencido (el cliente intenta refresh) |
| `credentials_changed` | 401 | `require_auth`/refresh: `session.credentials_version` atrás de `user.credentials_version` |
| `invalid_mfa_code` | 401 | `mfa/verify`/`enroll/confirm`: código incorrecto o replay |
| `mfa_step_up_expired` | 401 | `mfa/verify`: desafío inexistente, consumido o vencido |
| `mfa_required` | 403 | login/switch: `owner`/`billing` ya enrolado, falta step-up |
| `mfa_enrollment_required` | 403 | login/switch: `owner`/`billing` sin secreto |
| `mfa_unavailable` | 503 | `mfa/*`: Redis no disponible |
| `tenant_not_available` | 403 | login con tenant `suspended`; switch sin membership activa |
| `locked` | 423 | login: cuenta bloqueada, con `Retry-After` |
| `refresh_reuse` | 401 | refresh: token ya rotado/revocado |
| `invalid_or_expired_token` | 400 | reset: token vencido, usado o inexistente |

No existe el `code` `mfa_challenge`: si la UI necesita un estado, se llama `mfaStepUp` (D10). El
`401` genérico es `not_authenticated`; `session_expired` solo lo devuelve `require_auth` cuando el
access venció. Ningún error incluye email, hash, token ni `tenant_id` ajeno.

### D10 — Frontend: router existente, sesión restaurada, refresh single-flight y proxy

- **Router**: se extiende `frontend/src/App.tsx` (ya tiene `<Routes>`) con `/login` y `/` protegida
  por `RequireAuth`; `main.tsx` sigue montando `BrowserRouter`. No se crea un router nuevo.
- `src/api/http.ts`: `fetch` con `credentials: 'include'`; en `401` (incluido `session_expired`)
  intenta **un** `POST /api/v1/auth/refresh`, y si funciona reintenta la request original **una sola
  vez**; si falla, dispara `onUnauthorized` (logout local + `/login`). El refresh es *single-flight*:
  una `Promise` en vuelo compartida por todas las requests concurrentes, para no disparar dos
  rotaciones y caer en la revocación por reuso (D2).
- `AuthProvider` arranca en `loading`, llama `GET /api/v1/auth/me`: `200` → sesión restaurada;
  `401` → anónimo. `RequireAuth` redirige a `/login` con `state.from` y vuelve al destino original
  después del login.
- `Login.tsx`: RHF + Zod (`tenant_slug`, `email`, `password`), estados explícitos `idle` |
  `mfaStepUp` | `mfaEnrollment` (nunca `mfa_challenge` como estado ni como código), y mapeo de
  errores: `401 invalid_credentials` → "Email o contraseña incorrectos"; `423 locked` → "Cuenta
  bloqueada, reintentá en N minutos"; `403 mfa_required` / `mfa_enrollment_required` → paso de
  código o secreto; `401 mfa_step_up_expired` → reiniciar login; red → "No pudimos conectar".
- **Proxy de desarrollo**: se agrega `server.proxy['/api']` en `frontend/vite.config.ts` con target
  `process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'`. Se elige proxy sobre CORS porque
  mantiene el SPA y la API en el **mismo origen** para el navegador, que es lo que `SameSite=Lax`
  y las cookies `httpOnly` necesitan; CORS con credenciales obligaría a `SameSite=None`, `Secure`,
  `allow_credentials` y un token CSRF. En producción el reverse proxy cumple el mismo rol.
- No hay `localStorage`/`sessionStorage` con tokens: el estado vive en memoria y se reconstruye
  con `/api/v1/auth/me` al recargar.

### D11 — Plumbing de base de datos, Redis y fixture HTTP

- `backend/app/db/engine.py`: `create_db_engine(settings)` (SQLAlchemy 2.0, `pool_pre_ping`),
  `SessionLocal` y `get_db` (yield de `Session`, cierre garantizado). Se usa `Session` **síncrona**
  porque los helpers de C-02 (`set_tenant_context`, `tenant_context.py`) y los tests ya son sync;
  FastAPI ejecuta las dependencias/endpoints sync en el threadpool. La variante async queda como
  deuda explícita, no bloquea el vertical slice.
- Cada conexión ejecuta `SET ROLE odontologia_app` en el evento `connect` del engine. **La app se
  conecta como `odontologia_app`**; en tests el usuario del contenedor (superusuario) se usa
  **solo** para Alembic. Sin esto los tests HTTP correrían como superusuario, que ignora RLS, y el
  aislamiento sería ficticio (`docs/core-tenancy.md:81-83`).
- `backend/app/db/redis.py`: `create_redis_client(settings)` y `get_redis`; usado solo por MFA.
  El lifespan de la app cierra engine y Redis.
- `backend/tests/integration/conftest.py` agrega la fixture `client` (TestClient/httpx) que:
  1. toma `DATABASE_URL`/`REDIS_URL` de `docker_services`,
  2. depende de `migrated_database` (Alembic aplicado),
  3. construye `Settings` con `ENVIRONMENT=test`, `COOKIE_SECURE=false`, `MFA_ENCRYPTION_KEY`
     ficticia y las URLs del contenedor,
  4. crea el engine con `SET ROLE odontologia_app` y lo inyecta en `create_app`,
  5. entrega un `TestClient` con cookies persistentes.
  Un test de humo verifica `current_user = 'odontologia_app'` y que sin contexto `SELECT count(*)
  FROM session` devuelve 0. El superusuario queda solo para `migrated_database` y para leer
  `auth_event` en los tests.
- La dependencia `get_db` comparte la transacción del request; `set_config(..., true)` es
  transaction-local y el commit ocurre al final del request (o en el endpoint cuando necesita
  atomicidad explícita, como login/reset).

### D12 — Playwright ejecutable contra backend real + seed

- El spec va en `frontend/tests/e2e/auth.spec.ts` (Playwright usa `testDir: './tests/e2e'`; Vitest
  excluye `tests/e2e/**`).
- `frontend/playwright.config.ts` pasa a `webServer` **array**:
  - backend: `uv run python scripts/e2e_server.py` con `cwd: '../backend'`, health en
    `http://127.0.0.1:8000/health`;
  - frontend: el `npm run dev -- --port 5173 --strictPort` actual, con el proxy de D10.
  `E2E_EXTERNAL_SERVER=1` sigue permitiendo usar servicios ya levantados en CI.
- `backend/scripts/e2e_server.py` levanta Postgres 16 + Redis 7 con Testcontainers (o reutiliza
  `E2E_DATABASE_URL`/`E2E_REDIS_URL`), aplica Alembic, ejecuta
  `backend/tests/fixtures/seed_auth_e2e.py` (tenant `clinica-demo`, usuario `demo@example.test`,
  rol `professional`) y corre `uvicorn app.main:app --port 8000`. El engine de la app usa
  `SET ROLE odontologia_app`; el superusuario solo migra/semilla.
- El seed es idempotente y ficticio; no contiene secretos reales. Si Docker no está disponible, el
  e2e falla explícitamente (no se skippea en silencio).

## Risks / Trade-offs

- **[Resolver con `BYPASSRLS`]** Una función mal escrita podría devolver de más o ampliar el
  bypass. → Mitigación: retorno fijo de seis columnas, `search_path` fijo, sin SQL dinámico,
  `REVOKE ALL FROM PUBLIC`, `GRANT EXECUTE` solo a `odontologia_app`, y test de privilegios/DDL
  (S8.7, tarea 2.10).
- **[Rotación y tests]** Un fixture que reutiliza la cookie de refresh "vieja" dispara
  `refresh_reuse` y revoca la familia, haciendo fallar tests no relacionados. → Mitigación: cada
  test extrae las cookies de la respuesta y usa siempre la última; los helpers de fixture
  (`login_as`, `refresh_once`) son los únicos que tocan cookies; los tests de reuse son explícitos.
- **[Desafío MFA de un solo uso]** Un código incorrecto consume el desafío y obliga a reiniciar el
  login. → Trade-off aceptado: evita reintentos dentro del mismo desafío y hace el "un solo uso"
  verificable; el lockout de la cuenta sigue contando los fallos.
- **[Secure en TestClient]** Con `COOKIE_SECURE=true` y `http://testserver`, el cliente puede no
  reenviar la cookie. → Mitigación: `COOKIE_SECURE=false` en `ENVIRONMENT=test`, y un test
  dedicado que verifique que en `production` el atributo `Secure` y el `Path` correcto están
  presentes (tarea 3.9).
- **[Argon2 lento]** Con parámetros de producción, cientos de logins de test suman minutos. →
  Mitigación: parámetros reducidos **solo** cuando `ENVIRONMENT=test` (documentado en
  `docs/auth.md`); el test de hashing verifica que el hash es Argon2id y que verifica correctamente.
- **[Reloj]** Lockout y TTL con `now()` de Postgres vs `datetime.now()` de Python. → Mitigación:
  una sola fuente (la BD) para `locked_until`, `expires_at` y las comparaciones de validez de
  sesión; los tests fuerzan el tiempo con `UPDATE` de la fila, no durmiendo.
- **[Concurrencia de refresh]** Test de dos requests simultáneos puede ser flaky. → Mitigación:
  dos conexiones/threads con barrera y aserción sobre el estado final de la familia (una fila
  `activo` creada y familia revocada), no sobre cuál request ganó.
- **[`auth_event` sin RLS]** Es una tabla técnica con `tenant_id` nullable. → Mitigación: no se
  expone por API, trigger append-only, sin `SELECT` para el rol de app; si C-14 necesita leerla,
  se le agrega RLS de lectura entonces.
- **[Reset invalida sesiones por versión]** Un request en vuelo puede terminar después del reset;
  el siguiente ya falla. → Trade-off aceptado: no se enumeran tenants ni se escribe cross-tenant,
  que es el requisito duro; la ventana es de milisegundos y no expone datos nuevos.
- **[Login con `tenant_slug` en el body]** Un cambio a subdominios podría parecer una migración de
  contrato. → Mitigación: el campo ya está en el DTO y el borde puede completarlo desde `Host` sin
  romper clientes; documentado en `docs/auth.md`.
- **[Sin rate limit por IP]** La KB pide rate limit + CAPTCHA en `/api/v1/auth/login`. → Trade-off
  aceptado y declarado fuera de alcance: el lockout por cuenta sí está; los intentos distribuidos
  contra muchas cuentas quedan para un change posterior.

## Migration Plan

1. `alembic upgrade head` en test: aplica `003_auth` sobre `002_core_tenancy`; el test verifica
   tablas, columnas, índices, checks, rol/funciones del resolver, grants por columna, trigger y
   políticas.
2. `alembic downgrade 002_core_tenancy` y `alembic upgrade head` de nuevo: ciclo completo sin
   errores (test de reversibilidad, contenedor propio por el `DROP ROLE`).
3. Deploy: migración primero, backend después (el backend nuevo requiere las columnas), frontend
   al final. Sin downtime relevante: no hay datos productivos.
4. Rollback: `alembic downgrade 002_core_tenancy` + `git revert` del change. Las sesiones emitidas
   dejan de ser válidas por diseño (no se migran).

## Supuestos

- **Redis disponible para MFA**: `REDIS_URL` ya está en el stack y en Testcontainers. Si Redis cae,
  el step-up falla cerrado con `503 mfa_unavailable`; el login de roles sin MFA y el resto de la
  sesión no dependen de Redis.
- **Rol `auth_resolver` de clúster**: es `NOLOGIN` y solo existe para ser owner de las funciones;
  la migración asume que ningún otro schema/base del mismo clúster depende de él (el test de
  reversibilidad usa un contenedor propio).
- **Desafío MFA de un solo intento**: un código incorrecto consume el desafío; no hay contador de
  intentos por desafío. El tope de intentos es el lockout de la cuenta (5 fallos, D6).
- **TTL de sesión normal 12 h** (RN-AU-08) y refresh absoluto con el mismo vencimiento; el
  SuperAdmin (4 h) está fuera de alcance.
- **`mfa_satisfied` vacuo**: para roles que no exigen MFA la sesión nace con `mfa_satisfied = true`
  porque no hay factor pendiente; para `owner`/`billing` nace `false` hasta el step-up.
- **Replay TOTP**: `user.last_totp_step` es la barrera global por credencial y
  `session.last_used_step` el registro por sesión; el `UPDATE` atómico se hace sobre `user`.
- **Proxy same-site en dev**: Vite `server.proxy['/api']`; en producción el reverse proxy cumple el
  mismo rol. Si se separan dominios, hay que revisar `SameSite` y CSRF (D1).
- **Sin proveedor de email (PQ-08)**: el reset es funcional solo en `local`/`development`/`test`;
  en producción responde `202` y no entrega el token a nadie.

## Open Questions

- **Proveedor de email (PQ-08)**: sin proveedor, `forgot-password` en `staging`/`production`
  responde `202` y **no entrega el token a nadie**. Supuesto declarado: en v1 el flujo es
  funcional solo en `local`/`development`/`test` y queda inutilizable en producción hasta que se
  resuelva PQ-08. No cambia la spec (la spec ya exige no exponerlo fuera de desarrollo).
- **KMS para el secreto TOTP**: hoy `MFA_ENCRYPTION_KEY` por entorno + `key_version`. Migrar a
  KMS/clave por tenant es un change posterior; el formato (cifrado + versión) ya lo soporta.
- **`mfa_secret` en claro de C-02**: la columna existe pero está vacía; si alguna base de datos de
  desarrollo tuviera valores en claro, la migración no los re-cifra (no hay datos productivos).
- **`audit_log` definitivo (C-14)**: `auth_event` es el mínimo de auth y reemplaza al `audit_log`
  de RN-AU-05 en este change; C-14 decidirá si los eventos de autenticación se proyectan al
  `audit_log` append-only o si `auth_event` se conserva como tabla propia.
- **Alta disponibilidad de Redis**: el stack usa Redis 7 single-node; si el despliegue necesita HA,
  el desafío MFA es el único consumidor crítico y queda para infraestructura.
