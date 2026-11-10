# Proposal — c-03-auth-sessions

## Why

C-01 (runtime) y C-02 (modelo multi-tenant + RLS) están archivados: existen las tablas de
identidad (`tenant`, `user`, `membership`), el rol de aplicación sin `BYPASSRLS`, el helper
`set_tenant_context` y el `TenantGuard` puro, pero **no hay forma de que una persona entre al
sistema**. Sin login no existe sesión, y sin sesión no existe tenant activo: todos los changes de
la "ruta del turno" (C-05 profesionales/sillones, C-06 pacientes, `agendar-turno-sin-solapamiento`)
quedan bloqueados, igual que C-04 (RBAC) porque no hay sobre qué claims aplicar permisos.

El riesgo dominante es de seguridad, no de features: este change introduce el único lugar del
sistema donde se decide *quién es el usuario* y *sobre qué tenant opera*. Un error acá no se
compensa con UI: una cookie legible por JavaScript, un refresh sin rotación o un `tenant_id`
tomado del body convierten el aislamiento de C-02 en decorativo (RN-AU-02, RN-AU-03, RN-TEN-03).
Por eso se implementa con la cadena completa `require_auth → require_tenant` de la KB
(`08_arquitectura_propuesta.md` § Seguridad), con una resolución pre-contexto **acotada** para
refresh y con el test cross-tenant de las tablas de sesión como gate de merge (RN-TEN-02).

Además es el primer **vertical slice** del proyecto (DD-03): entrega API + pantalla de login +
guarda de rutas, y con eso el TPI pasa a tener algo demostrable de punta a punta.

## What Changes

- **Credenciales y hashing Argon2id** (RN-AU-01): `password_hash` con `argon2-cffi`
  (`Argon2id`, parámetros versionados en el hash), verificación a tiempo constante y rehash
  transparente cuando suben los parámetros.
- **`POST /api/v1/auth/login`**: autentica email + password dentro del `tenant_slug` solicitado,
  resuelve las `membership` activas de ese tenant e inicia sesión. La contraseña se verifica
  contra el `user` global (sin RLS, C-02); la sesión se crea **ya con** el `tenant_id` resuelto
  desde `membership`. Un tenant en estado `suspended` responde `403 tenant_not_available` sin
  sesión (RN-TEN-06).
- **Sesión en cookie `httpOnly`** (RN-AU-02 / DD-10): access JWT corto + refresh opaco rotativo,
  ambos en cookies `httpOnly`, `SameSite=Lax` y `Secure` (configurable solo en `local`/`test`).
  La sesión normal dura 12 h absolutas (RN-AU-08); el refresh nunca la excede.
  **Nada de tokens en `localStorage`.**
- **Resolución pre-contexto acotada (B1)**: el refresh opaco no lleva tenant y la RLS `FORCE` de
  `session`/`refresh_token` no permite leer sin `app.current_tenant`. Se agrega el rol
  `auth_resolver` (`NOLOGIN`, `BYPASSRLS`) dueño de dos funciones `SECURITY DEFINER` mínimas que
  resuelven la sesión por `sid` (access) y por `token_hash` (refresh) devolviendo **solo**
  `session_id`, `tenant_id`, `user_id`, `expires_at`, `revoked_at` y `credentials_version`.
  `require_auth` y `refresh` usan el resolver, fijan el GUC con el tenant devuelto y recién
  entonces consultan `session`/`refresh_token` bajo RLS. El bypass queda confinado a las
  funciones, con `search_path` fijo, `REVOKE ALL FROM PUBLIC` y `GRANT EXECUTE` solo a
  `odontologia_app`.
- **`POST /api/v1/auth/refresh`** con rotación atómica y detección de reuse (RN-AU-03): cada uso
  marca el refresh anterior como `rotado` y emite uno nuevo de la misma familia; la reutilización
  de un refresh ya rotado revoca **toda la familia** y la sesión asociada.
- **`POST /api/v1/auth/logout`** idempotente: revoca la sesión y su familia, y borra ambas cookies.
- **`GET /api/v1/auth/me`**: devuelve usuario, tenant activo y roles **sin** `password_hash`,
  `mfa_secret`, hashes de refresh ni tokens.
- **Lockout progresivo** (RN-AU-05): 5 intentos fallidos → bloqueo con `423 Locked` y
  `Retry-After`; el backoff duplica la ventana en bloqueos consecutivos. Cada intento se registra
  en `auth_event`, tabla append-only que **reemplaza al `audit_log` de RN-AU-05 en este change**
  (C-14 decidirá la proyección definitiva).
- **MFA TOTP obligatorio para `owner` y `billing`** (RN-AU-04): login con step-up obligatorio;
  `403 mfa_required` (ya enrolado) o `403 mfa_enrollment_required` (sin secreto), con un desafío
  efímero de un solo uso guardado en Redis (TTL 5 min, `GETDEL` atómico) y cookie `HttpOnly`
  `Path=/api/v1/auth/mfa`; `POST /api/v1/auth/mfa/verify`, enrolamiento en dos pasos
  (`/api/v1/auth/mfa/enroll/start` + `/api/v1/auth/mfa/enroll/confirm`) y secreto TOTP **cifrado
  en reposo**. `mfa_satisfied` es por sesión y por tenant. No existe endpoint para desactivar MFA
  en esos roles.
- **Recuperación de contraseña** con token opaco de un solo uso, 30 min
  (`POST /api/v1/auth/forgot-password`, `POST /api/v1/auth/reset-password`). Sin proveedor de
  email: en v1 el token se persiste hasheado y se expone **solo** en
  `local`/`development`/`test` (PQ-08). El reset **invalida todas las sesiones previas por
  credencial**: incrementa `user.credentials_version` en la misma transacción; no enumera
  tenants ni escribe `session` cross-tenant.
- **Cambio de tenant activo con re-emisión de sesión** (RN-AU-07):
  `POST /api/v1/auth/switch-tenant` lee el tenant destino del body (excepción explícita a
  RN-TEN-03), valida `membership` activa y emite una sesión nueva con su propia familia de
  refresh. Si el destino tiene al usuario con rol `owner` o `billing`, **no emite sesión**:
  responde `403 mfa_required` / `mfa_enrollment_required` y la sesión nueva se emite recién
  después del step-up; el factor satisfecho en A no habilita B.
- **Migración Alembic `003_auth`** (`down_revision = 002_core_tenancy`): DDL completo de
  `session`, `refresh_token`, `password_reset_token`, `auth_event`; columnas nuevas en `user`
  (`failed_login_count`, `locked_until`, `lockout_strikes`, `last_lockout_at`,
  `mfa_enrolled_at`, `mfa_secret_key_version`, `credentials_version`, `last_totp_step`); rol
  `auth_resolver` y sus dos funciones; grants por columna; trigger append-only; `session` y
  `refresh_token` con `tenant_id NOT NULL` + RLS `FORCE`.
- **Dependencias FastAPI de auth** en `app/api/v1/deps.py`: `require_auth` (resolver → GUC →
  sesión bajo RLS) y `require_tenant` (membership con el GUC ya seteado), más el contrato de
  errores `401`/`403`/`423`.
- **Plumbing de datos**: engine/session factory y dependencia `get_db` en `backend/app/db/`, con
  `SET ROLE odontologia_app` al abrir cada conexión; cliente Redis para el desafío MFA. En tests,
  la app se conecta como `odontologia_app`; el superusuario del contenedor solo corre migraciones.
- **Frontend (vertical slice)**: se **extiende** el router existente (`main.tsx` monta
  `BrowserRouter`, `App.tsx` ya define `<Routes>`), pantalla de login (React Hook Form + Zod +
  shadcn/ui), cliente HTTP con `credentials: 'include'` y refresh *single-flight* con una sola
  reintentativa, restauración de sesión con `GET /api/v1/auth/me`, guarda de rutas y logout.

## Capabilities

### New Capabilities

- `platform-auth`: identidad y ciclo de vida de la sesión de usuarios internos — credenciales
  Argon2id, emisión/rotación/revocación de sesión en cookie `httpOnly`, detección de reuse de
  refresh, lockout progresivo con auditoría mínima, MFA TOTP obligatorio para `owner`/`billing`
  (incluido el step-up al cambiar de tenant), recuperación de contraseña con token de un solo uso
  y cambio de tenant activo con re-emisión.

### Modified Capabilities

Ninguna. El `TenantGuard` de `platform-tenancy` no cambia de contrato: este change solo lo
conecta como `Depends` y agrega la sesión que lo alimenta, tal como anticipa esa spec.

## Impact

| Área | Impacto |
|------|---------|
| Backend `app/domain/auth` | Hashing Argon2id, TOTP con control de replay, tokens opacos, reglas de lockout (funciones puras, sin I/O) |
| Backend `app/models/auth.py` | `Session`, `RefreshToken`, `PasswordResetToken`, `AuthEvent` + columnas de lockout/MFA/credencial en `User` |
| Backend `app/api/v1/auth` | 10 endpoints: login, refresh, logout, me, forgot/reset-password, switch-tenant, mfa verify/enroll start/enroll confirm |
| Backend `app/api/v1/deps.py` | `require_auth`, `require_tenant` (ubicación única; el proposal y las tareas coinciden) |
| Backend `app/core` | `security.py` (cookies, JWT), `crypto.py` (cifrado del secreto TOTP) |
| Backend `app/db` | `engine.py` (engine/session factory + `get_db` + `SET ROLE odontologia_app`), `redis.py` (cliente del desafío MFA) |
| Backend `app/config.py` | Nuevas variables: `COOKIE_SECURE`, `ACCESS_TOKEN_TTL_SECONDS`, `SESSION_TTL_HOURS`, `MFA_ENCRYPTION_KEY` |
| Base de datos | Migración `003_auth`: 4 tablas con DDL completo, columnas en `user`, rol `auth_resolver` + 2 funciones `SECURITY DEFINER`, RLS `FORCE` en `session`/`refresh_token`, grants por columna, trigger append-only, índices |
| Dependencias backend | `argon2-cffi`, `pyjwt`, `pyotp`, `cryptography`, `redis`; `httpx` ya existe |
| Frontend | `react-router-dom` (ya en `package.json`), `react-hook-form`, `zod`, `@hookform/resolvers`, componentes shadcn (`button`, `input`, `label`, `alert`, `card`); `src/api/http.ts`, `src/api/auth.ts`, `src/features/auth/**`, `src/routes/Login.tsx`, `src/App.tsx` (extender `<Routes>`), `src/routes/Home.tsx`, `vite.config.ts` (proxy `/api`) |
| Tests | Unitarios puros (hashing, TOTP, lockout, tokens), integración con Postgres real (migración, RLS, resolver, rotación, reuse, lockout), fixture HTTP `client` como `odontologia_app`, Vitest/RTL, Playwright con backend real + seed |
| Documentación | `docs/auth.md` (contrato, variables, estados, reemplazo `audit_log` → `auth_event`, salida real de los tests) |
| Changes existentes | Desbloquea C-04, C-05, C-06, C-07 y todo endpoint protegido |

**Governance**: CRÍTICO (autenticación + tenancy + secretos). Sin test de aislamiento cross-tenant
en `session`/`refresh_token` —a nivel SQL **y** a nivel endpoint— el change no se mergea
(RN-TEN-02).

## Dependencies

- C-02 `core-models-tenancy` (archivado): `tenant`/`user`/`membership`, rol `odontologia_app`,
  RLS `FORCE`, `set_tenant_context`, `tenant_id_from_claims`.
- C-01 `foundation-setup` (archivado): app factory, settings fail-fast, Testcontainers, CI.
- KB: `05_reglas_de_negocio.md` § Autenticación (RN-AU-01..05, RN-AU-07) y § Tenancy
  (RN-TEN-02, RN-TEN-03, RN-TEN-05, RN-TEN-06); `03_actores_y_roles.md` § Rutas públicas
  (fuente del reset: token de un solo uso, 30 min — `03_actores_y_roles.md:90`) y § Detalle de
  roles base; `08_arquitectura_propuesta.md` § Seguridad; `09_decisiones_y_supuestos.md` § DD-10,
  SU-01/SU-02; `04_modelo_de_datos.md` § Tenancy; `06_funcionalidades.md` US-001/US-005.

## Out of Scope

- **RBAC por rol/permisos** (matriz de `03_actores_y_roles.md`, `require_role`): es C-04. Acá solo
  se emiten los roles en los claims y `/api/v1/auth/me` los devuelve; ningún endpoint de negocio
  los consume todavía.
- **Invitaciones y alta de usuarios** (US-005, expiración 7 días): C-04.
- **Envío real de email** (proveedor transaccional): el token de recuperación se persiste y se
  expone solo en desarrollo (ver `design.md` § Supuestos); PQ-08 sigue abierta.
- **OAuth/SSO**, login por OTP de paciente (RN-AU-06, portal del paciente), `SuperAdmin`
  (RN-AU-08), MFA por WebAuthn/SMS.
- **Rate limiting por IP, CAPTCHA y bloqueo por hash de password** (mitigaciones de la KB para
  `/api/v1/auth/login`): fuera de v1; el lockout por cuenta sí entra.
- **`audit_log` completo** (KB `04`, § `audit_log`; consultas de US-043): es C-14. Acá solo el
  mínimo de auth en `auth_event` append-only, que **reemplaza** al `audit_log` de RN-AU-05 para
  los eventos de autenticación de este change.
- **Endpoints de negocio, agenda, pacientes, facturación**.
- **UI de recuperación de contraseña fuera del flujo mínimo** y pantalla de administración de
  sesiones.

## Criterios del TPI que cubre

| Criterio | Cómo lo cubre este change | Evidencia |
|----------|---------------------------|-----------|
| **Autenticación y permisos** — login de usuario | `POST /api/v1/auth/login` con Argon2id, cookie `httpOnly` y sesión con tenant + roles | Tests de integración de login válido + `GET /api/v1/auth/me` |
| **Autenticación y permisos** — acceso autorizado | `require_auth` + `require_tenant` protegen `/api/v1/auth/me`, `switch-tenant` y todo endpoint futuro; el tenant sale de la sesión, nunca del body (RN-TEN-03), salvo el destino explícito de `switch-tenant` | Tests de guarda (`401` sin cookie) y cross-tenant de `session`/`refresh_token`, SQL y HTTP |
| **Autenticación y permisos** — rechazo de credenciales inválidas | `401` uniforme para password incorrecto/usuario inexistente/inactivo; `423` con `Retry-After` en lockout; `403` cuando falta el segundo factor | Tests de credenciales inválidas, lockout progresivo y MFA obligatorio |
| **Frontend integrado** — pantalla de login | `src/routes/Login.tsx` con RHF + Zod + shadcn/ui y errores visibles por código HTTP | Vitest/RTL + Playwright |
| **Frontend integrado** — guarda de rutas | `RequireAuth` redirige a `/login` sin sesión y restaura la sesión con `GET /api/v1/auth/me` al arrancar | Tests de guarda y de restauración de sesión |

> Nota de alcance: este change prueba **autenticación** (quién es el usuario y sobre qué tenant
> opera). La autorización **por rol/permiso** (`require_role`, matriz de `03_actores_y_roles.md`)
> llega en C-04; acá los roles solo se emiten y se devuelven en `/auth/me`.
