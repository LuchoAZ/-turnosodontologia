# Auth y sesiones — contrato, sesión httpOnly, MFA y RBAC de ingreso

Este documento describe lo que entrega el change `c-03-auth-sessions`: el modelo de sesión del
sistema, el contrato de los 10 endpoints de auth, el bloqueo progresivo, el segundo factor, el
reset de contraseña, el cambio de clínica (switch-tenant) y el frontend que consume ese contrato
(cliente HTTP, pantalla de login y guarda de rutas).

> Regla que manda: **RN-TEN-03** — el tenant activo sale del token/sesión, **nunca** del body.
> La única excepción deliberada es `POST /auth/switch-tenant`, que recibe el `tenant_slug`
> destino y **revalida la membership bajo RLS** antes de emitir una sesión nueva.

---

## 1. Qué se entrega

| Pieza | Dónde |
|---|---|
| Migración `003_auth` (sesiones, refresh, lockout, MFA, reset, `auth_event`) | `backend/alembic/versions/003_auth.py` |
| Modelos SQLAlchemy 2.0 | `backend/app/models/auth.py` |
| Políticas RLS + rol `auth_resolver` | `003_auth.py` (upgrade) |
| Reglas de dominio (login, refresh, lockout, MFA, switch, reset) | `backend/app/domain/auth/` |
| Router + DTOs | `backend/app/api/v1/auth/router.py`, `backend/app/schemas/auth.py` |
| Cliente HTTP + contrato TypeScript | `frontend/src/api/http.ts`, `frontend/src/api/auth.ts` |
| Estado de sesión, guardas y pantalla de login | `frontend/src/features/auth/`, `frontend/src/routes/Login.tsx` |
| Backend real para e2e | `backend/scripts/e2e_server.py`, `backend/tests/fixtures/seed_auth_e2e.py` |
| e2e | `frontend/tests/e2e/auth.spec.ts`, `frontend/tests/e2e/smoke.spec.ts` |

---

## 2. Modelo de sesión

Los tokens **no existen en JavaScript**. El access y el refresh viajan como cookies `HttpOnly`; el
SPA nunca los lee ni los escribe en `localStorage`/`sessionStorage` (verificado por test y por
barrido, §13).

| Cookie | Contenido | `Path` | `Max-Age` | Atributos |
|---|---|---|---|---|
| `odontologia_access` | JWT `HS256` (`sub`, `sid`, `tenant_id`, `mfa`, `iat`, `exp`) | `/` | `ACCESS_TOKEN_TTL_SECONDS` (900") | `HttpOnly`, `SameSite=Lax`, `Secure` según `COOKIE_SECURE` |
| `odontologia_refresh` | token opaco de 32 bytes (en base solo su hash) | `/api/v1/auth` | `SESSION_TTL_HOURS` (12 h) | ídem |
| `odontologia_mfa` | `challenge_id` del desafío en Redis | `/api/v1/auth/mfa` | 300" | ídem |

El refresh **rota en cada uso**: la fila vieja queda revocada y se emite una nueva de la misma
familia. Reutilizar un refresh ya rotado revoca la familia completa (`401 refresh_reuse`).

### 2.1 Estados de sesión

```
                         POST /auth/login
  (anónimo) ─────────────────────────────────┐
      ▲                                       │ 200 → cookies access+refresh
      │                                       ▼
      │                                 (autenticado) ── POST /auth/refresh ──> rota, sigue autenticado
      │                                       │
      │                                       │ 403 mfa_required / mfa_enrollment_required
      │                                       ▼
      │                              (pendiente_mfa)  ← mfa_satisfied = false
      │                                       │ POST /auth/mfa/verify | /mfa/enroll/confirm
      │                                       └──> (autenticado), revoca la sesión de origen
      │
      └── POST /auth/logout (idempotente, 204) ── o ── refresh inválido/reuse/lockout
```

- La sesión emitida por `login` de un rol que exige segundo factor nace **pendiente**: el access
  token lleva `mfa=false` y `require_tenant` solo la acepta para los endpoints de MFA.
- `mfa_satisfied` es **por sesión y por tenant**: cambiar de clínica vuelve a exigir step-up.
- `credentials_version` del usuario se incrementa al cambiar la contraseña; toda sesión emitida
  con una versión anterior queda inválida (`401 credentials_changed`) **sin barridos cross-tenant
  y sin bypass de RLS**.

### 2.2 Bloqueo progresivo (lockout)

Contador por **cuenta** (`user`), no por IP: 4 fallos y el 5.º bloquea. El estado se actualiza con
`SELECT … FOR UPDATE` dentro de la misma transacción, así dos intentos concurrentes no se pisan.
La respuesta es `423 locked` con header `Retry-After: <segundos>`.

---

## 3. Contrato HTTP (10 endpoints)

Prefijo: `/api/v1/auth`. El contrato formal es el OpenAPI de FastAPI (`app/schemas/auth.py`).

| # | Endpoint | Request | Éxito | Errores propios |
|---|---|---|---|---|
| 1 | `POST /login` | `{tenant_slug, email, password}` | `200 SessionOut` + cookies | `401 invalid_credentials`, `423 locked`, `403 mfa_required` / `mfa_enrollment_required`, `403 tenant_not_available` |
| 2 | `GET /me` | cookies | `200 SessionOut` | `401 not_authenticated` / `session_expired` / `credentials_changed` |
| 3 | `POST /refresh` | cookie refresh | `200 SessionOut` (rota) | `401 session_expired`, `401 refresh_reuse` |
| 4 | `POST /logout` | cookies | `204` (idempotente) | — |
| 5 | `POST /mfa/verify` | `{code}` + cookie `odontologia_mfa` | `200 SessionOut` | `401 invalid_mfa_code`, `401 mfa_step_up_expired`, `423 locked` |
| 6 | `POST /mfa/enroll/start` | cookie `odontologia_mfa` | `200 {secret, otpauth_uri}` | `401 mfa_step_up_expired` |
| 7 | `POST /mfa/enroll/confirm` | `{code}` + cookie `odontologia_mfa` | `200 SessionOut` | `401 invalid_mfa_code`, `401 mfa_step_up_expired` |
| 8 | `POST /switch-tenant` | `{tenant_slug}` + sesión | `200 SessionOut` | `403 mfa_required` (+ `Set-Cookie` del desafío), `403 tenant_not_available` |
| 9 | `POST /forgot-password` | `{email}` | `202` **siempre** (sin `token` en `production`) | — (nunca revela si el email existe) |
| 10 | `POST /reset-password` | `{token, new_password}` | `200 {"status":"ok"}` | `400 invalid_or_expired_token` |

`SessionOut` = `{user:{id,email,nombre,apellido}, tenant:{id,slug,nombre_comercial}, roles[], permissions[], mfa_enrolled}`.
`permissions[]` son los permisos efectivos de la sesión (C-04), en orden alfabético; la UI decide
visibilidad por permiso y nunca comparando `roles` (ver `docs/rbac.md` § 3).
Los DTOs son lista blanca: nunca sale `password_hash`, `mfa_secret` ni ningún token.

### 3.1 Catálogo de `code` (design D9)

La UI conmuta **por `code`**, nunca por status ni por texto. Los `code` son estables; el `message`
es solo para el usuario.

| `code` | HTTP | Significado |
|---|---|---|
| `invalid_credentials` | 401 | Email o contraseña incorrectos (no distingue cuál) |
| `not_authenticated` | 401 | Sin sesión válida / token ilegible |
| `session_expired` | 401 | Access vencido: el cliente debe refrescar |
| `credentials_changed` | 401 | La contraseña cambió; hay que volver a entrar |
| `invalid_mfa_code` | 401 | TOTP incorrecto o reutilizado |
| `mfa_step_up_expired` | 401 | El desafío expiró: reiniciar login |
| `mfa_required` | 403 | Falta step-up para esta operación/rol |
| `mfa_enrollment_required` | 403 | El rol exige enrolar TOTP |
| `mfa_unavailable` | 503 | No se pudo evaluar el segundo factor |
| `forbidden` | 403 | La sesión no tiene el permiso que exige el endpoint (guarda `require_permission` de C-04; ver `docs/rbac.md` § 4) |
| `tenant_not_available` | 403 | Tenant inexistente, suspendido o sin membership activa |
| `locked` | 423 | Cuenta bloqueada temporalmente (+ `Retry-After`) |
| `refresh_reuse` | 401 | Refresh ya rotado: familia revocada |
| `invalid_or_expired_token` | 400 | Token de reset inválido, usado o vencido |

---

## 4. Segundo factor (TOTP)

- **Step-up (`403 mfa_required`)**: el rol lo exige (p. ej. `owner`/`billing` al cambiar de clínica
  a un tenant donde tiene ese rol). El 403 viaja con `Set-Cookie` del desafío, así el SPA puede
  pedir el código sin volver a mandar credenciales.
- **Alta (`403 mfa_enrollment_required`)**: el usuario no tiene secreto. `enroll/start` devuelve
  `secret` + `otpauth_uri`; `enroll/confirm` valida el primer código y activa el factor.
- **Redis**: `auth:mfa:challenge:<id>` (JSON con `user_id`, `tenant_id`, `purpose`, `source_*`),
  TTL 300 s, consumido con `GETDEL`; el secreto de alta vive en `auth:mfa:enroll:<id>`.
- **Anti-replay**: `last_totp_step` por usuario; el mismo `step` de 30 s no se acepta dos veces.
- **Los fallos de MFA cuentan para el lockout** igual que un password incorrecto.
- El secreto se guarda cifrado (Fernet con clave derivada por HKDF de `MFA_ENCRYPTION_KEY`).

---

## 5. Reset de contraseña (D7)

1. `POST /forgot-password` responde **`202` siempre**, con el mismo cuerpo exista o no la cuenta:
   `ForgotPasswordResponse` se serializa con `response_model_exclude_none=True` y el campo `token`
   solo se incluye en `local`/`development`/`test` (nunca en `production`). En esos entornos el
   token también queda en `auth_event.detail` para poder probar el flujo; en producción no.
2. `POST /reset-password` ejecuta, en **una sola transacción**:
   `UPDATE password_reset_token … RETURNING user_id` y
   `UPDATE "user" SET password_hash = …, credentials_version = credentials_version + 1 … RETURNING id`.
   Si el segundo update no devuelve fila, se hace `rollback()`: el token no se consume en vano.
3. El incremento de `credentials_version` es lo que invalida las sesiones vivas del usuario — no hay
   `UPDATE` cross-tenant ni rol con `BYPASSRLS` involucrado.

Fuente del flujo: `knowledge-base/03_actores_y_roles.md:90`.

---

## 6. Switch-tenant (D4.3/D5)

`require_tenant` pasa al servicio `user_id`, `source_session_id` y `source_tenant_id`. El servicio:

1. fija el GUC del **tenant destino** (`set_config('app.current_tenant', …)`) y valida la membership
   bajo RLS; si no hay membership activa → `403 tenant_not_available` y `rollback()` que restaura el
   contexto del tenant de origen;
2. si el rol en el destino es `owner`/`billing`, crea la sesión **pendiente** en el destino, abre el
   desafío y responde `403 mfa_required` con `Set-Cookie`;
3. tras el TOTP correcto, revoca la sesión de origen y completa la del destino cambiando el GUC de
   A→B en la misma transacción. Un fallo deja A intacta y B pendiente sin refresh (no usable).

---

## 7. RLS, rol de aplicación y resolución pre-contexto (B1)

- Todas las tablas de auth (`session`, `refresh_token`, `password_reset_token`, `mfa_*`) tienen
  `tenant_id NOT NULL` y RLS `FORCE ROW LEVEL SECURITY`.
- Los tests corren como **`odontologia_app`** (`SET ROLE odontologia_app`). `SET ROLE` es
  transaccional: los helpers hacen `RESET ROLE` **y** `commit()`.
- `SET LOCAL` no acepta parámetros bindeados → se usa
  `SELECT set_config('app.current_tenant', :tenant_id, true)`.
- El login necesita resolver `tenant.slug` + `user.email` **antes** de tener contexto. Se hace con
  una función `SECURITY DEFINER` acotada (rol `auth_resolver`: `NOLOGIN`, `BYPASSRLS`,
  `search_path` fijo, `REVOKE ALL FROM PUBLIC`, `GRANT EXECUTE` solo a `odontologia_app`, **sin SQL
  dinámico**).
- `password_reset_token` tiene grants **por columna** para `odontologia_app`: no puede leer el hash
  del token, solo lo mínimo para el flujo.
- `auth_event` no es legible ni mutable por `odontologia_app`; un trigger
  (`auth_event_forbid_mutation`) deja pasar el `UPDATE` interno provocado por cascadas de FK
  (`pg_trigger_depth() > 1`) pero rechaza DML directo con SQLSTATE `55000`, incluso para el
  superusuario.

### 7.1 Nota sobre auditoría

`auth_event` **reemplaza** al `audit_log` de RN-AU-05 para el alcance de este change: es el mínimo
append-only de auth (login, refresh, logout, lockout, MFA, reset, switch). La tabla `audit_log`
definitiva se diseña en C-14; ahí se decide si absorbe `auth_event` o si conviven (ver design §D8,
riesgo abierto). `auth_event` es multi-tenant y por eso **no** se expone a la app.

### 7.2 Preguntas abiertas que tocan este change

- **PQ-08** (proveedor de email transaccional, Postmark como candidato): `forgot-password` **no**
  envía correo todavía. El token se devuelve solo en entornos de desarrollo/test; en producción el
  canal de entrega queda pendiente de PQ-08.

---

## 8. Frontend: cliente HTTP y sesión

### 8.1 `apiFetch` (`frontend/src/api/http.ts`)

- Toda request va a `/api/v1…` con `credentials: 'include'`.
- `401` → **un** `POST /auth/refresh` compartido por todas las requests en vuelo (*single-flight*
  con un `refreshPromise` de módulo que se limpia en `finally`) y **una** reintentativa.
- Si el refresh falla: no reintenta, avisa por `setUnauthorizedHandler` (el `AuthProvider` vuelve a
  `anonymous`) y propaga el **error original**.
- `skipAuthRetry` en login, MFA, reset, refresh y logout: ahí un `401` es un resultado legítimo, no
  una sesión vencida.
- `ApiError` expone `status`, `code`, `message` y `retryAfter` (parseado de `Retry-After`).
- `204`/`205` resuelven sin intentar parsear body.

### 8.2 Estado y guardas

`AuthProvider` arranca en `loading`, restaura con `GET /auth/me` y registra el handler de
`401` irrecuperable. `RequireAuth` redirige a `/login` conservando el destino (`state.from`), y
`Login` vuelve a ese destino después de autenticar. `Home` muestra `tenant.nombre_comercial` +
nombre del usuario y el botón **Salir**.

### 8.3 Pantalla de login

React Hook Form + Zod + shadcn/ui, con tres estados: `idle` | `mfaStepUp` | `mfaEnrollment`.

| Situación | UI |
|---|---|
| `401 invalid_credentials` | "Email o contraseña incorrectos." |
| `423 locked` | "La cuenta está bloqueada temporalmente. Reintentá en N minutos." (N desde `retryAfter`) |
| `403 mfa_required` | Paso a `mfaStepUp` (código de 6 dígitos) |
| `403 mfa_enrollment_required` | Paso a `mfaEnrollment`: muestra el secreto y confirma el alta |
| `401 mfa_step_up_expired` | Vuelve a `idle` con aviso "Volvé a iniciar sesión" |
| Error de red (`TypeError`) | "No pudimos conectar con el servidor…" |

> Detalle de implementación: `src/components/ui/input.tsx` (generado por shadcn con
> `@base-ui/react`) se reescribió con `React.forwardRef`. Como wrapper de función, RHF perdía el
> `ref` y los campos llegaban `undefined` al resolver.

---

## 9. Mismo origen: por qué proxy y no CORS

Las cookies son `HttpOnly` + `SameSite=Lax`: para que el navegador las mande en cada request del
SPA, frontend y backend tienen que ser **el mismo origen**. Por eso `vite.config.ts` proxya `/api`:

```ts
server: {
  proxy: {
    '/api': { target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000' },
  },
}
```

Con proxy no hace falta `Access-Control-Allow-Origin`, no se habilita `credentials` cross-site y
`SameSite=Lax` sigue siendo la defensa básica contra CSRF. En producción el mismo esquema lo resuelve
el reverse proxy (un solo host sirviendo SPA + API).

**Verificación real del proxy** (backend `uvicorn` en `:8000` con migraciones + seed, Vite en
`:5180` — ver §10 sobre el puerto):

```
$ curl -s -i http://127.0.0.1:5180/api/v1/auth/me
HTTP/1.1 401 Unauthorized
Vary: Origin
date: Tue, 10 Nov 2026 14:19:36 GMT
server: uvicorn
content-length: 68
content-type: application/json
connection: close

{"code":"not_authenticated","message":"No hay una sesión válida."}
```

`server: uvicorn` y el JSON del backend prueban que la request **atravesó** el proxy: si faltara,
Vite devolvería `404` (o el SPA en HTML), y sin backend la respuesta sería `500` con
`ECONNREFUSED` en la terminal de Vite.

Y el login completo por el mismo origen:

```
$ curl -s -X POST http://127.0.0.1:5180/api/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"tenant_slug":"clinica-demo","email":"demo@example.test","password":"demo-password-123"}'
{"user":{"id":"788a26c7-…","email":"demo@example.test","nombre":"Demo","apellido":"Pérez"},
 "tenant":{"id":"5c2515d7-…","slug":"clinica-demo","nombre_comercial":"Clínica Demo"},
 "roles":["professional"],
 "permissions":["appointment.read","chair.read","chart.create","chart.finalize","chart.read",
                "chart.update","clinical_record.create","clinical_record.read",
                "clinical_record.update","consent.create","consent.read","professional.read",
                "report_usage.read","settlement.read_own","tenant_settings.read"],
 "mfa_enrolled":false}
# Set-Cookie: odontologia_access=…; HttpOnly; Path=/; SameSite=Lax
```

---

## 10. Orquestación del e2e (backend real + Vite)

`npm run test:e2e` levanta **todo** desde `playwright.config.ts` (`webServer` como array):

| Servidor | Comando | Health | Reutiliza |
|---|---|---|---|
| Backend (`:8000`) | `uv run python scripts/e2e_server.py` | `GET /health` | **Nunca** |
| SPA (Vite) | `npm run dev -- --port $E2E_WEB_PORT --strictPort` | `GET /` | Solo con `E2E_REUSE_SERVER=1` |

`backend/scripts/e2e_server.py` levanta **Postgres 16 + Redis 7** con Testcontainers (o reutiliza
`E2E_DATABASE_URL`/`E2E_REDIS_URL`), corre la cadena real de Alembic hasta `head`, siembra la cuenta
ficticia (`backend/tests/fixtures/seed_auth_e2e.py`: tenant `clinica-demo`, usuario
`demo@example.test`, rol `professional`, contraseña `demo-password-123`) y arranca
`uvicorn app.main:create_app` con variables de entorno ficticias.

Variables de la orquestación:

| Variable | Default | Para qué |
|---|---|---|
| `E2E_WEB_PORT` | `5173` | Puerto del SPA (cambiar si otro servicio lo ocupa) |
| `E2E_BACKEND_PORT` | `8000` | Puerto del backend de test |
| `E2E_EXTERNAL_SERVER` | — | `1` desactiva ambos `webServer` (CI con servicios ya vivos) |
| `E2E_REUSE_SERVER` | — | `1` permite reutilizar un Vite ya levantado |
| `E2E_BASE_URL` | `http://127.0.0.1:$E2E_WEB_PORT` | `baseURL` de Playwright |
| `E2E_TENANT_SLUG` / `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` | cuenta del seed | Credenciales del e2e |
| `E2E_DATABASE_URL` / `E2E_REDIS_URL` | Testcontainers | Infra externa para el backend de test |

### 10.1 Problemas conocidos al correr el e2e en Windows

- **Puerto 5173 ocupado por Docker Desktop.** `com.docker.backend` puede quedar escuchando en 5173
  (responde `200`), y Playwright aborta con *“is already used”*. Solución: `E2E_WEB_PORT=5180`.
- **Vite viejo con el optimizador desactualizado.** Un dev server levantado mientras cambiaba el
  `package-lock.json` sirve módulos con **500** y el SPA queda en blanco (síntoma: `body` vacío y
  `Failed to load resource: 500`). Por eso el `webServer` **no** reutiliza un server existente.
  Si pasa: matar el proceso del puerto y borrar `frontend/node_modules/.vite`.
- **Docker apagado.** El backend de test necesita Docker: `docker info` debe responder.

---

## 11. Variables de entorno

Las nuevas de este change (el resto ya existía en C-01/C-02):

| Variable | Obligatoria | Default | Uso |
|---|---|---|---|
| `COOKIE_SECURE` | no | `true` | `Secure` de las tres cookies (en `test`/e2e se pone `false` para `http`) |
| `ACCESS_TOKEN_TTL_SECONDS` | no | `900` | TTL del access token |
| `SESSION_TTL_HOURS` | no | `12` | TTL del refresh / de la sesión |
| `SESSION_SECRET` | **sí** | — | firma `HS256` del access; 64 caracteres en tests |
| `JWT_REFRESH_SECRET` | **sí** | — | pepper del hash del refresh; 64 caracteres |
| `MFA_ENCRYPTION_KEY` | **sí** | — | clave del cifrado del secreto TOTP; 32 caracteres |

`load_config` es *fail-fast* y solo lee el mapping inyectado (nunca `os.environ` implícito), así los
tests controlan el entorno completo.

---

## 12. Aislamiento verificado (`test_auth_rls.py`)

```
$ cd backend && uv run pytest tests/integration/test_auth_rls.py -q
.........                                                                [100%]
9 passed, 1 warning in 7.28s
```

Casos (todos ejecutados, ninguno *skipped*):

| Test | Qué prueba |
|---|---|
| `test_select_only_returns_the_context_tenant` | el contexto de A solo ve filas de A |
| `test_select_without_context_returns_zero_rows` | sin GUC → **0 filas** (fail-closed) |
| `test_insert_with_a_foreign_tenant_is_rejected` | `INSERT` con `tenant_id` ajeno rechazado |
| `test_update_cannot_move_a_session_to_another_tenant` | no se puede “mover” una sesión de tenant |
| `test_update_and_delete_of_another_tenant_affect_zero_rows` | `UPDATE`/`DELETE` cross-tenant = 0 filas |
| `test_mutation_proof_superuser_sees_both_tenants` | **prueba de mutación**: el superusuario *sí* ve ambos tenants → el aislamiento es de RLS, no de los datos |
| `test_auth_event_cannot_be_read_by_the_app_role` | `odontologia_app` no lee `auth_event` |
| `test_auth_event_cannot_be_updated_or_deleted_even_by_superuser` | append-only real (`55000`) |
| `test_password_reset_token_grants_are_column_scoped` | grants por columna de `password_reset_token` |

`cross-tenant leak = 0`.

---

## 13. Salida real del pipeline

Ejecutado el **2026-11-10** en `main` (Docker Desktop activo). Números actualizados tras C-04
(`c-04-rbac-permissions`); el detalle por capa está en `docs/rbac.md` § 10.3.

```
$ cd backend && uv run ruff check app tests alembic
All checks passed!

$ cd backend && uv run mypy app
Success: no issues found in 52 source files

$ cd backend && uv run pytest -q
334 passed, 1 warning in 51.31s

$ cd frontend && npm run lint
✖ 1 problem (0 errors, 1 warning)      # react-refresh/only-export-components en button.tsx (preexistente)

$ cd frontend && npm run typecheck
> tsc -b                               # sin salida = sin errores

$ cd frontend && npm run test
 Test Files  8 passed (8)
      Tests  43 passed (43)

$ cd frontend && E2E_WEB_PORT=5180 npm run test:e2e
[WebServer] [e2e] cuenta lista: clinica-demo / demo@example.test
[WebServer] [e2e] uvicorn en http://127.0.0.1:8000
Running 11 tests using 7 workers
  ok 2 [chromium] › tests\e2e\auth.spec.ts:20:1 › sin sesión, la raíz redirige a /login (1.9s)
  ok 3 [chromium] › tests\e2e\smoke.spec.ts:3:1 › sin sesión, la raíz muestra el login (2.0s)
  ok 6 [chromium] › tests\e2e\smoke.spec.ts:10:1 › con sesión, la raíz muestra la home (2.4s)
  ok 4 [chromium] › tests\e2e\auth.spec.ts:36:1 › login válido llega a la home con el tenant de la sesión (2.5s)
  ok 1 [chromium] › tests\e2e\auth.spec.ts:27:1 › credenciales inválidas muestran el error del catálogo (2.6s)
  ok 5 [chromium] › tests\e2e\auth.spec.ts:46:1 › logout vuelve a /login y una recarga no restaura la sesión (2.6s)
  ok 7..11 team.spec.ts (5 tests de permisos de equipo, ver docs/rbac.md § 10.2)
  11 passed (12.6s)
```

Los 4 casos de `auth.spec.ts` cubren el criterio “autenticación y permisos” con navegador real:
redirección sin sesión, rechazo de credenciales inválidas con el mensaje del catálogo, login válido
aterrizando en la home **con el tenant de la sesión**, y logout que no se restaura al recargar.

Barrido de almacenamiento web (task 9.4):

```
$ grep -rn "localStorage\|sessionStorage" frontend/src
frontend/src/api/http.test.ts:164   # solo el test que prohíbe la escritura
frontend/src/api/http.test.ts:175
frontend/src/api/http.test.ts:176
```

No hay una sola escritura de tokens en el SPA: la única aparición es la aserción que lo impide.

---

## 14. Deudas y desviaciones registradas

| Tema | Estado |
|---|---|
| Envío real del email de reset | Bloqueado por **PQ-08** (proveedor transaccional); en dev/test el token sale por la respuesta/`auth_event` |
| `audit_log` definitivo | Se diseña en C-14; `auth_event` es el mínimo de auth por ahora (design §D8) |
| `SessionLocal` global | Se reemplazó por `create_session_factory(engine)` + `get_db` (desviación menor del design, ya adoptada) |
| Trigger `auth_event_forbid_mutation` | Deja pasar el `UPDATE` interno de FK (`pg_trigger_depth() > 1`); el DML directo sigue fallando con `55000` |
| Caducidad de `odontologia_refresh` | `Max-Age` = `SESSION_TTL_HOURS`; la rotación revalida que la sesión siga viva |
