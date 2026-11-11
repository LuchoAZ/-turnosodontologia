# Spec Delta — platform-auth

## Purpose

Delta acotado del contrato de sesión de C-03: `SessionOut` incorpora los permisos efectivos del
tenant activo. La autenticación, el refresh, el lockout, el MFA y el tenant del token no cambian.

## MODIFIED Requirements

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
