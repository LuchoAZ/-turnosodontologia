# Evidencia — `spec-scenario-review` sobre `c-03-auth-sessions` (r2)

**Fecha de ejecución**: 2026-11-06 · **Skill**: `spec-scenario-review`
**Change revisado**: `openspec/changes/c-03-auth-sessions/`
**Pasada anterior**: [`revision-c-03.md`](revision-c-03.md) — veredicto `BLOQUEADO` (B1, B2 + 10 altos)
**Alcance de esta pasada**: cierre de los dos bloqueantes y de los diez hallazgos altos, más la
verificación de que el contrato corregido sigue siendo implementable.

> **Nota de método (declarada, no maquillada)**: la r1 la hizo un revisor independiente que no
> escribió los artefactos. Esta r2 la ejecutó el orquestador que coordinó la corrección, porque el
> sub-agente revisor no estaba disponible (límite de uso del modelo). Los chequeos de estructura
> (requisito → escenarios → tarea, conteos, IDs, ausencia de códigos prohibidos) son **mecánicos**
> y se corrieron con script; la revisión semántica se contrastó contra cada hallazgo de la r1, con
> archivo y línea. Si el docente exige un revisor externo también para la r2, el gate queda
> repetible: el informe de la r1 y este documento listan exactamente qué mirar.

---

## Veredicto

**LISTO PARA APLICAR**

Los dos bloqueantes están cerrados con decisiones explícitas y verificables, no con una nota al
pie. La cobertura quedó en **8 requisitos / 43 escenarios / 54 tareas**, con **43/43 escenarios
mapeados a una tarea de verificación** y `openspec validate --strict` en verde.

---

## Cobertura por requisito

| # | Requisito (`specs/platform-auth/spec.md`) | Escenarios | Esperado | Error de negocio | Borde | Tareas |
|---|-------------------------------------------|-----------|----------|------------------|-------|--------|
| R1 | Login con credenciales y emisión de sesión (`:12`) | 5 | S1.1 | S1.2, S1.3 | **S1.4** (memberships A/B, login queda en B), **S1.5** (tenant suspendido) | 3.1, 3.2, 3.9 |
| R2 | Ciclo de sesión, refresh rotativo y reuso (`:58`) | 6 | S2.1 | S2.2, S2.6 | S2.3 (otras familias intactas), S2.4 (concurrencia), S2.5 (logout idempotente) | 3.3–3.5, 6.1 |
| R3 | Lockout progresivo y eventos (`:116`) | 4 | S3.1 | S3.2 | S3.3 (expira), S3.4 (backoff + lockout por cuenta) | 4.1, 4.2 |
| R4 | MFA TOTP para `owner`/`billing` (`:151`) | 6 | S4.1, S4.3 | S4.2 (inválido/reusado) | S4.5 (desafío de un solo uso), S4.6 (Redis caído) | 5.1–5.4 |
| R5 | Recuperación de contraseña (`:216`) | 5 | S5.1 | S5.2, S5.3 | S5.4 (exposición por entorno), S5.5 (dos resets concurrentes) | 6.1, 6.2 |
| R6 | Tenant activo y switch (`:260`) | 6 | S6.1 | S6.2 | S6.3 (body ignorado salvo switch), S6.4 (A no lee **ni escribe** B), **S6.5** (step-up), **S6.6** (step-up expirado) | 3.8, 7.1–7.3 |
| R7 | Guarda de sesión y `/auth/me` (`:323`) | 4 | S7.1 | S7.2 | S7.3 (cookie manipulada/expirada/membership off), S7.4 (credencial vieja) | 3.6, 3.7, 3.9 |
| R8 | Aislamiento RLS de tablas de sesión (`:365`) | 7 | S8.1 | S8.2, S8.5 | S8.3 (sin contexto), S8.4 (mutación), S8.6 (endpoint), S8.7 (resolver confinado) | 2.5–2.9, 3.10 |

**R1 ya tiene borde real**: S1.4 prueba una decisión de negocio (con memberships en dos tenants, la
sesión queda en el solicitado y no en el otro) y S1.5 prueba el estado `suspended`. No son dos
variantes del mismo `401`.

---

## Cierre de los bloqueantes de la r1

### B1 — RLS `FORCE` vs. resolución pre-contexto — **CERRADO**

| Qué pedía la r1 | Cómo quedó | Dónde |
|-----------------|------------|-------|
| Decidir el mecanismo de resolución antes de tener tenant | Rol `auth_resolver` (`NOLOGIN NOSUPERUSER NOINHERIT BYPASSRLS`) dueño de dos funciones `SECURITY DEFINER`: `auth_resolve_session_by_sid(uuid)` y `auth_resolve_session_by_refresh(text)` | `design.md` D4.2 (`:186-210`), D8.6 (`:473-518`) |
| Confinamiento del bypass | Retorno fijo de 6 columnas, `SET search_path = pg_catalog, public`, `REVOKE ALL FROM PUBLIC`, `GRANT EXECUTE` solo a `odontologia_app`, sin SQL dinámico, sin PII ni hashes | `design.md:198-207`, `spec.md:365-375`, `spec.md:424-432` |
| Orden de `require_auth` / `require_tenant` | Resolver → `set_config(..., true)` → `session` bajo RLS → `credentials_version` → membership; mismo `Session`/transacción, sin commit intermedio | `design.md` D4.3 (`:212-231`), `tasks.md` 3.7 |
| Refresh: de dónde sale el tenant | Del resolver por `token_hash`; si no hay fila → `401 not_authenticated` sin distinguir si existe en otro tenant | `design.md:69-98`, `spec.md:58-69`, `tasks.md` 3.4 |
| Reset: revocar sesiones de todos los tenants sin contexto | Invalidación por credencial: `user.credentials_version` incrementado en la misma transacción; la sesión guarda la versión y se rechaza con `401 credentials_changed`; sin escritura cross-tenant ni bypass | `design.md` D4.4 (`:239-247`), D7 (`:325-346`), `spec.md` S2.6 y S5.1, `tasks.md` 6.2 |
| Test de aislamiento a nivel endpoint | `test_auth_isolation_http.py`: A no refresca/lee/cierra B, corriendo con la app como `odontologia_app` (no superusuario) | `spec.md` S8.6 (`:415-422`), `tasks.md` 3.10 |

La RLS sigue `FORCE` en `session` y `refresh_token`; el único bypass es el de dos funciones
revisadas, y S8.7 lo verifica por introspección de privilegios (`tasks.md` 2.9).

### B2 — `switch-tenant` emitía sesión `owner`/`billing` sin segundo factor — **CERRADO**

| Qué pedía la r1 | Cómo quedó | Dónde |
|-----------------|------------|-------|
| Escenario de switch a tenant con rol privilegiado | S6.5: `403 mfa_required` / `403 mfa_enrollment_required`, sin cookie de B, A intacta hasta completar el step-up | `spec.md:304-314` |
| Desafío fallido/expirado | S6.6: `401 mfa_step_up_expired`, A sigue `200`, no hay sesión `vigente` de B | `spec.md:316-321` |
| Alcance de `mfa_satisfied` entre tenants | Por sesión y por tenant: la sesión de B nace `pendiente_mfa` aunque A haya completado MFA; el factor no se reutiliza | `spec.md:269`, `design.md:281-290` |
| Tarea de verificación | 7.3 (RED→GREEN) cubre los dos caminos y el rollback de A | `tasks.md:64` |

---

## Cierre de los diez hallazgos altos

| # de la r1 | Hallazgo | Cierre | Evidencia |
|-----------|----------|--------|-----------|
| 3 | R1 sin borde real | S1.4 (multi-membership) y S1.5 (tenant suspendido) | `spec.md:44-56`, `tasks.md` 3.1 |
| 4 | Receta de mutación inválida (dropear política = default-deny) | Se usa la receta de C-02: mismo `SELECT` como superusuario vs. `SET ROLE odontologia_app`, o `DISABLE ROW LEVEL SECURITY`; el escenario dice explícitamente que dropear la política **no** es mutación válida | `spec.md:395-403`, `tasks.md` 2.7 |
| 5 | Sin DDL de `session`/`auth_event`/`password_reset_token` | DDL completo de las 4 tablas + columnas de `user`, con índices, checks y trigger | `design.md` D8.1–D8.5 (`:356-471`), `tasks.md` 2.3 |
| 6 | Replay TOTP y desafío MFA sin estado | `user.last_totp_step` (barrera global, `UPDATE ... WHERE last_totp_step < :step`) + `session.last_used_step`; desafío en Redis con `GETDEL` y TTL 300 s | `design.md` D5 (`:249-298`), `spec.md:159-161`, `spec.md:173-181`, `tasks.md` 2.3, 5.4 |
| 7 | Sin plumbing DB ni fixture HTTP ni rol de conexión | `engine.py`/`redis.py`/`get_db`, listener `SET ROLE odontologia_app`, fixture `client` contra Testcontainers, smoke de `current_user` y de 0 filas sin contexto | `design.md` D11 (`:612-637`), `tasks.md` 2.1, 2.2 |
| 8 | `.env.example` en ruta falsa y `BASE_ENV` roto | Ruta raíz explícita, actualización de `BASE_ENV` y del guard `test_env_example_documents_every_schema_variable`; test que falla si falta `MFA_ENCRYPTION_KEY` en `production` | `tasks.md` 1.1, `design.md:53-55` |
| 9 | Frontend/e2e no ejecutable | Spec en `frontend/tests/e2e/auth.spec.ts`, `server.proxy['/api']`, `webServer` array con backend real + seed, y actualización de `App.test.tsx`/`smoke.spec.ts` al guard | `design.md` D10 (`:587-610`) y D12 (`:639-654`), `tasks.md` 8.6–8.8 |
| 10 | `mfa_challenge` vs. `mfa_required` | Catálogo único en D9: `mfa_required` / `mfa_enrollment_required`; se declara que el `code` `mfa_challenge` no existe y el estado de UI se llama `mfaStepUp` | `design.md:562-585`, `tasks.md` 1.10, 8.4 |
| 11 | S6.3 contradecía `switch-tenant` | La excepción queda en el texto del requisito: el destino del body se lee **solo** en `switch-tenant` y se valida contra membership activa | `spec.md:260-269`, `spec.md:286-293` |
| 12 | Design contra el código real | Se corrige que el router ya existe y se extiende; ubicación única de dependencias en `app/api/v1/deps.py`; DDL completo | `design.md:10-12`, `design.md:214`, `proposal.md:113-114`, `tasks.md` 8.5 |

Mejoras de la r1 incorporadas: nota del reemplazo `audit_log` → `auth_event` en R3 (`spec.md:116-123`),
fuente del reset citada (`spec.md:219`, `design.md:345-346`), `Secure`/`Path` verificados en test
dedicado (`tasks.md` 3.9), grants por columna de `password_reset_token` (`design.md:527-532`,
`tasks.md` 2.8), lectura de `auth_event` solo como superusuario (`spec.md:405-413`), aserción de
**escritura** cross-tenant en S6.4 (`spec.md:295-302`) y nota de que la autorización por rol llega en
C-04 (`proposal.md:169-171`).

---

## Check de tenancy (RN-TEN-02)

- [x] El change toca tablas con `tenant_id`: `session` y `refresh_token` (`NOT NULL` + FK + RLS
      `FORCE`). `auth_event` (nullable) y `password_reset_token` (global) están justificadas como
      técnicas/globales en `design.md` D4.1 (`:165-184`).
- [x] Hay escenario cross-tenant SQL (S8.1, S8.2) y **a nivel endpoint** (S8.6).
- [x] `tenant_id` sale de la sesión en toda operación autenticada; las dos excepciones —`tenant_slug`
      en login y destino en `switch-tenant`— están declaradas y validadas contra membership.
- [x] `tasks.md` incluye test de aislamiento con `SET ROLE odontologia_app` (2.5, 2.7), prueba de
      mutación con receta válida (2.7) y aislamiento HTTP con la app conectada como
      `odontologia_app` (3.10).
- [x] **`cross-tenant leak = 0`** es criterio de salida de 2.7 y 3.10.

---

## Verificación mecánica ejecutada

| Chequeo | Resultado |
|---------|-----------|
| `openspec validate c-03-auth-sessions --strict` | `Change 'c-03-auth-sessions' is valid` |
| Requisitos | 8 |
| Escenarios | 43 (5 + 6 + 4 + 6 + 5 + 6 + 4 + 7) |
| Escenarios por requisito | mínimo 4, máximo 7 — ninguno por debajo de 3 |
| Tareas | 54 |
| Tareas con `Verificación:` | 54/54 |
| IDs de escenario en spec vs. matriz | 43 = 43, sin faltantes ni duplicados |
| `mfa_challenge` como `code` positivo | 0 (solo menciones que lo prohíben) |
| `backend/.env.example` como ruta válida | 0 (solo la mención que la corrige) |
| `frontend/e2e/` | 0; `tests/e2e/` aparece en design y tareas |
| `SECURITY DEFINER`, `search_path`, `REVOKE`, `GRANT EXECUTE` | presentes en D4.2/D8.6 y en R8 |
| `credentials_version` en modelo, spec y tareas | presente (38 referencias) |

---

## Riesgos residuales (declarados, no bloqueantes)

1. **Revisor independiente en r2**: ver la nota de método. El contenido de la r1 sigue siendo la
   referencia externa; esta pasada verifica el cierre punto por punto.
2. **`auth_resolver` con `BYPASSRLS`**: es el precio de resolver la sesión antes del contexto. Está
   confinado a dos funciones con retorno fijo y probado por introspección (S8.7). Si se quisiera
   eliminar el bypass, la alternativa es firmar `sid`+`tid` en la cookie (más manejo de claves).
3. **Rol de login en producción**: `odontologia_app` es `NOLOGIN`; el engine hace `SET ROLE` desde un
   rol de login miembro. En tests el superusuario del contenedor solo migra y siembra. Es una
   decisión operativa que `docs/auth.md` debe dejar escrita (tarea 9.2).
4. **Argon2 en tests**: parámetros reducidos solo con `ENVIRONMENT=test`; el hash de producción se
   verifica en un test unitario, no en la suite de integración (costo).
5. **Desafío MFA de un solo intento**: un código incorrecto consume el desafío y obliga a reiniciar
   el login. Es un trade-off declarado (D5) y verificable (S4.5).
6. **Redis**: único consumidor crítico es el step-up; si cae, `503 mfa_unavailable` y no se emite
   sesión privilegiada (S4.6).
7. **Límite con C-04**: este change prueba autenticación; la autorización por rol/permiso
   (`require_role`, matriz de 9 roles) sigue siendo C-04 y así está declarado.

---

## Próximo paso

1. `/opsx:apply c-03-auth-sessions` por TDD, en el orden de `tasks.md` (sección 1 → 9).
2. Al terminar: correr el pipeline completo de 9.3 y registrar la salida real en `docs/auth.md`
   (9.2), con la mutación de RLS y el aislamiento HTTP **ejecutados**, no skippeados.
3. Documentar en `CHANGES.md` el estado real (aplicado/verificado) y recién entonces archivar el
   change con `openspec archive`.
