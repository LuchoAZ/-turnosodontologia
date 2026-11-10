# Evidencia — `spec-scenario-review` sobre `c-03-auth-sessions`

**Fecha de ejecución**: 2026-11-06 · **Skill**: `spec-scenario-review`
**Change revisado**: `openspec/changes/c-03-auth-sessions/`
**Rol del revisor**: independiente (no se modificó ningún artefacto del change; esta es la única escritura).
**Entradas leídas**: `proposal.md`, `design.md`, `specs/platform-auth/spec.md`, `tasks.md`;
KB `05_reglas_de_negocio.md` (§ Autenticación, § Tenancy), `03_actores_y_roles.md`
(§ Detalle de roles base, § Rutas públicas, § RBAC), `04_modelo_de_datos.md` (§ Tenancy),
`08_arquitectura_propuesta.md` (§ Seguridad / Autenticación), `09_decisiones_y_supuestos.md` (§ DD-10),
`10_preguntas_abiertas.md` (PQ-08), `CHANGES.md` (§ Cuándo cuenta un change, § Estado del roadmap),
`docs/core-tenancy.md` y el código real de `backend/` y `frontend/`.

---

# Revisión de escenarios — c-03-auth-sessions

## Veredicto
**BLOQUEADO**

Motivo: hay una contradicción estructural entre el contrato de tenancy del change (RLS `FORCE` sobre
`session`/`refresh_token`, sin lectura sin contexto) y flujos que **deben** resolver filas antes de
conocer el tenant (`/auth/refresh`, la carga de `session` en `require_auth`, y la revocación de todas
las sesiones en `/auth/reset-password`). Tal como está escrito, el ciclo de sesión no se puede
implementar con RLS activa. Además, `switch-tenant` permite emitir una sesión `owner`/`billing` sin
segundo factor, lo que contradice RN-AU-04. Ninguno de los dos es un "test faltante": son defectos de
contrato que hay que resolver en la spec/design antes de `/opsx:apply`.

No es un problema de prolijidad: el resto de la cobertura de escenarios es sólida (32 escenarios,
32 con tarea mapeada; 7 de 8 requisitos con borde real).

## Cobertura por requisito

| Requisito | Esperado | Error de negocio | Borde | RN citada | Tareas | Estado |
|-----------|----------|------------------|-------|-----------|--------|--------|
| R1 Login con credenciales y emisión de sesión (`spec.md:12`) | ✅ S1.1 | ✅ S1.2 + S1.3 | ❌ S1.3 es **otra variante del error** (no revelar la cuenta), no un borde | RN-AU-01/02, RN-TEN-03 | 3.1, 3.2 | Falta borde real |
| R2 Ciclo de sesión, refresh rotativo y reuse (`spec.md:41`) | ✅ S2.1 | ✅ S2.2 (reuse) + S2.3 (expirado/revocado) | ✅ S2.4 concurrencia + S2.5 logout idempotente | RN-AU-03 | 3.3–3.5 | OK (implementabilidad bloqueada por B1) |
| R3 Lockout progresivo y eventos (`spec.md:85`) | ✅ S3.1 | ✅ S3.2 (password correcto en bloqueo) | ✅ S3.3 vencimiento + S3.4 backoff y lockout global por cuenta | RN-AU-05 (ver M1) | 4.1, 4.2 | OK con observación |
| R4 MFA TOTP para `owner`/`billing` (`spec.md:117`) | ✅ S4.1 + S4.3 | ✅ S4.2 (código inválido/reusado) | ✅ S4.2 replay + S4.4 `skip_mfa`/reposo | RN-AU-04 | 5.1–5.3 | OK de cobertura; falta modelo de estado (H4) y switch (B2) |
| R5 Recuperación de contraseña (`spec.md:156`) | ✅ S5.1 | ✅ S5.2 + S5.3 (anti-enumeración) | ✅ S5.4 exposición por entorno | — (KB `03` § Rutas públicas; ver M3) | 6.1, 6.2 | OK de cobertura; "revocar todas las sesiones" choca con RLS (B1) |
| R6 Tenant activo y switch (`spec.md:189`) | ✅ S6.1 | ✅ S6.2 | ✅ S6.3 body/query ignorado + S6.4 A≠B | RN-AU-07, RN-TEN-03, RN-TEN-05 | 7.1, 7.2, 3.8 | Contradicción interna en S6.3 (H9) + MFA (B2) |
| R7 Guarda de sesión y `/auth/me` (`spec.md:221`) | ✅ S7.1 | ✅ S7.2 | ✅ S7.3 manipulada/expirada/membership off | RN-AU-02, RN-TEN-03 | 3.6, 3.7 | OK de cobertura (ver B1) |
| R8 Aislamiento RLS de tablas de sesión (`spec.md:249`) | ✅ S8.1 | ✅ S8.2 + S8.5 | ✅ S8.3 sin contexto | RN-TEN-02 | 2.3–2.6 | Receta de mutación inválida (H2) |

**Lectura explícita de R1**: tiene 3 escenarios, pero el tercero (membership inactiva / tenant
inexistente) es una **variante del error de credenciales** con la misma respuesta `401
invalid_credentials`; no prueba un límite. R1 no tiene borde real.

## Huecos detectados

### Bloqueantes

1. **RLS `FORCE` vs. resolución de sesión antes de tener contexto (refresh, `require_auth`, reset).**
   - La spec exige que `session` y `refresh_token` tengan `tenant_id NOT NULL`, RLS habilitada y
     forzada, con política `USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)`
     (`spec.md:251-253`) y que **sin contexto la consulta devuelva 0 filas** (`spec.md:269-272`).
     C-02 ya documenta ese comportamiento (`docs/core-tenancy.md:86-87`).
   - `POST /api/v1/auth/refresh` sólo recibe un token opaco de 32 bytes (`design.md:45`). Para rotarlo
     hay que hacer `UPDATE refresh_token ... WHERE token_hash=:h AND estado='activo'` (`design.md:63-64`),
     pero sin `app.current_tenant` la fila no es visible: la rotación afecta 0 filas y el endpoint
     devolvería `401` siempre. El design no define de dónde sale el tenant en refresh (no hay JWT en
     esa cookie y el token es opaco). Lo mismo aplica a la revocación de la familia por reuso
     (`design.md:66`) y a `session.revoked_at`.
   - `require_auth` "carga la `session` por `sid`" (`design.md:219-220`) y la cadena es
     `require_auth → require_tenant` (`design.md:222`, `08_arquitectura_propuesta.md:104`); el
     `set_config` recién ocurre en `require_tenant`. Con RLS forzada, la lectura de `session` en
     `require_auth` ve 0 filas → todo endpoint autenticado responde `401`. El design debería decir que
     `require_auth` fija el GUC desde los claims del access antes de leer la sesión, o mover la carga
     de sesión después de `require_tenant`.
   - `reset-password` debe "revocar todas las sesiones del usuario" (`spec.md:160`, `design.md:180-181`,
     `tasks.md:51-52`). `session` está RLS-scoped y `membership` también; sin contexto no se pueden
     enumerar los tenants ni actualizar sus sesiones. Una transacción no puede "ver" varias tenants
     salvo iterando contextos, y para iterar memberships hace falta el mismo contexto que no se tiene.
   - **Qué falta decidir y testear**: una de estas salidas, explícita y con escenario/tarea:
     (a) función `SECURITY DEFINER` acotada que reciba el hash y devuelva sólo `tenant_id`/`session_id`
     (con `search_path` fijo y grants mínimos); (b) tabla de *lookup* no-RLS con sólo el hash y el
     `tenant_id`; (c) tenant firmado en la cookie de refresh. Sin eso, R2/R5/R7 y S8.3 no son
     implementables en conjunto.
   - **Impacto**: bloquea el criterio "Autenticación y permisos" del TPI y el gate RN-TEN-02.

2. **`switch-tenant` emite sesión `owner`/`billing` sin segundo factor (RN-AU-04).**
   - RN-AU-04 exige MFA para `owner`/`billing` (`05_reglas_de_negocio.md:61-62`) y la spec lo exige
     "en el tenant de la sesión" (`spec.md:119-122`). El escenario de switch (`spec.md:196-201`) sólo
     pide `200`, sesión nueva y roles de B; **no** contempla que B sea un tenant donde el usuario es
     `owner`/`billing`.
   - Caso concreto: usuario `professional` en A (login sin MFA) que también es `owner` en B. Hace
     `switch-tenant(B)` y recibe una sesión con rol `owner` **sin haber presentado TOTP**: bypass de
     RN-AU-04. Tampoco se define qué pasa si nunca enroló MFA en B (`mfa_enrollment_required`).
   - **Qué falta**: escenario "switch a tenant con roles `owner`/`billing` → `403 mfa_required` (o
     `mfa_enrollment_required`) y sesión nueva sólo después del step-up", más tarea de verificación
     en `tasks.md` (7.1/7.2) y la regla de si el factor se reutiliza entre tenants.

### Altos (spec/ejecutabilidad)

3. **R1 sin borde real**: los 3 escenarios son 1 camino feliz + 2 variantes del mismo `401`. Agregar
   un borde de negocio, p. ej. "usuario con memberships activas en A y B entra con `tenant_slug = B` y
   la sesión queda en B (RN-TEN-05)", o "tenant en `estado = suspended`" (definir la respuesta).

4. **La prueba de mutación de S8.4 no puede dar el resultado que promete.** El escenario dice que al
   eliminar la política "se ven filas de B" (`spec.md:274-279`), y la tarea 2.5 propone borrar la
   política dentro de una transacción (`tasks.md:23`). Con RLS `FORCE` y **cero políticas**, PostgreSQL
   aplica *default deny* para el rol no-owner: se ven 0 filas, no las de B, y el test **no falla**.
   C-02 resolvió la mutación comparando el mismo `SELECT` como superusuario (ve A y B) vs.
   `SET ROLE odontologia_app` (ve sólo A) (`backend/tests/integration/test_core_tenancy_migration.py:398-414`,
   `docs/core-tenancy.md:179-181`). La receta de 2.5 debe ser esa (o `DISABLE ROW LEVEL SECURITY` como
   mutación explícita), no "dropear la política".

5. **El esquema de `session` no está definido en el design ni en la migración.** La spec y las tareas
   usan `session.mfa_satisfied` (`spec.md:130`, `tasks.md:45`), `session.revoked_at`,
   `session.expires_at` y `session.user_id`; el design sólo enumera las columnas de `refresh_token`
   (`design.md:61-62`) y la tarea 2.1 sólo verifica el índice `session(tenant_id, user_id)`
   (`tasks.md:19`). No hay DDL ni verificación de migración para esas columnas: el implementador tiene
   que inventarlas y el escenario S4.1 queda sin test de esquema. Lo mismo pasa con las columnas de
   `auth_event` (`tipo`, `user_id`, `tenant_id`, `detail`, `created_at`): no se enumeran.

6. **Estado de replay TOTP y del desafío MFA no modelado.** La tarea 1.4 exige controlar
   `last_used_step` (`tasks.md:8`) y el escenario S4.2 exige rechazar un código ya usado y contar el
   fallo (`spec.md:132-137`), pero ni la propuesta ni el design agregan una columna/tabla para ese
   estado (`proposal.md:54-58`, `design.md:136-149`, migración `design.md:190-209`). Igual pasa con el
   "desafío efímero (`HttpOnly`, 5 min, un solo uso)" de `tasks.md:46`: no se define dónde vive, qué
   identifica al usuario/tenant y cómo se garantiza el "un solo uso". Sin eso, S4.2 y el requisito de
   `mfa/verify`/`enroll/start` no son verificables.

7. **No hay plumbing de base de datos para los endpoints ni fixture HTTP contra Testcontainers.**
   `backend/app/db/` sólo tiene `tenant_context.py`; no hay engine/session factory ni dependencia
   `get_db`. El Impact del proposal no menciona crearlo (`proposal.md:86-88`) y las tareas 3.1–3.7 no
   lo declaran. El `conftest` actual abre containers y ejecuta Alembic, pero **no** arma un
   `TestClient` con `DATABASE_URL`/`REDIS_URL` del container ni una fixture de app bajo test
   (`backend/tests/integration/conftest.py:57-83`). Además no se declara **con qué rol se conecta la
   app**: si es el superusuario del container, los tests de endpoints no ejercitan RLS (un superusuario
   la ignora, `docs/core-tenancy.md:81-82`) y el test de aislamiento queda sólo a nivel SQL. Falta,
   como mínimo: tarea de engine/sesión, tarea de fixture `client` contra containers y tarea de rol de
   conexión (`odontologia_app`) para el camino HTTP.

8. **Configuración y `.env.example`: la tarea 1.1 apunta a un archivo que no existe y rompe fixtures
   existentes.** `tasks.md:5` dice `backend/.env.example`, pero el archivo real es `.env.example` en la
   raíz del repo (`backend/tests/unit/test_env_example.py` calcula `parents[3] / ".env.example"`). Si
   `MFA_ENCRYPTION_KEY` se agrega como campo requerido de `Settings` (`backend/app/config.py:53-56`),
   `load_config(base_env)` falla en todos los tests porque `BASE_ENV` no la define
   (`backend/tests/conftest.py:13-19`); actualizar esa fixture no figura en ninguna tarea y el guard
   `test_env_example_documents_every_schema_variable` fallaría. Hay que declarar ambas cosas (ruta
   correcta y actualización de `BASE_ENV`, o requerimiento condicional por entorno).

9. **Frontend/e2e: rutas y orquestación no ejecutables como están escritas.**
   - `tasks.md:66` crea `frontend/e2e/auth.spec.ts`, pero Playwright tiene `testDir: './tests/e2e'`
     (`frontend/playwright.config.ts:5`) y Vitest excluye `tests/e2e/**`
     (`frontend/vite.config.ts`). El test no se ejecutaría con `npm run test:e2e -- auth.spec.ts`.
   - El design dice que en dev se usa "Vite proxy a `/api`" (`design.md:56-57`), pero
     `frontend/vite.config.ts` **no** tiene `server.proxy` y el backend no tiene `CORSMiddleware`
     (`backend/app/main.py`). Sin proxy ni CORS con credenciales, el SPA en `:5173` no puede hablar con
     la API en `:8000`; agregar el proxy no está en ninguna tarea.
   - No se declara cómo Playwright arranca el backend real + Testcontainers: `playwright.config.ts`
     sólo levanta el dev server de Vite; el seed `backend/tests/fixtures/seed_auth_e2e.py` no tiene
     orquestación asociada.
   - **Regresiones no declaradas**: `frontend/src/App.test.tsx` renderiza `/` y espera el heading de
     `Home`; con `RequireAuth` esa ruta redirige a `/login` y el test falla. `frontend/tests/e2e/smoke.spec.ts`
     hace lo mismo y fallará con el guard. La tarea 9.3 exige `npm run test` y `npm run test:e2e` en 0,
     pero ni 8.5 ni 8.6 mencionan actualizar esos dos tests.

10. **Contradicción de contrato de error MFA.** El proposal dice `403 mfa_challenge`
    (`proposal.md:45`); el design fija `mfa_required` / `mfa_enrollment_required` (`design.md:213-216`),
    la spec usa esos códigos (`spec.md:120`, `127`, `152`) y las tareas también (`tasks.md:45`). El
    frontend además usa `mfa_challenge` como *estado de UI* (`design.md:235`), lo que aumenta la
    confusión. Debe quedar un solo catálogo de `code`.

11. **La spec se contradice con `switch-tenant` en "el tenant del body/query es ignorado".**
    R6 abre con "El `tenant_id` de toda operación autenticada MUST salir de la sesión" (`spec.md:191`)
    y S6.3 dice que un `tenant_id` en body/query se ignora (`spec.md:209-213`). Pero `switch-tenant`
    **necesita** leer el tenant destino del body (`spec.md:192-194`, `tasks.md:56`). Hay que acotar S6.3
    a "endpoints distintos de `switch-tenant`" y declarar a `switch-tenant` como la excepción explícita
    (destino solicitado + membership validada), o el implementador puede leer el bloqueo como "no
    aceptar el destino".

12. **El design afirma cosas que el código no sostiene.**
    - `design.md:9-10`: "No existe ... ni router/cliente HTTP en el frontend". El router **sí existe**:
      `react-router-dom` está en `frontend/package.json`, `frontend/src/main.tsx` monta `BrowserRouter`
      y `frontend/src/App.tsx` ya define `<Routes>`/`<Route>`. No hay cliente HTTP, pero la mitad de la
      frase es falsa y la tarea 8.5 ("implementar el router") en realidad extiende uno existente.
    - `proposal.md:87` ubica las dependencias en `app/core/auth_deps.py`; `tasks.md:35` las ubica en
      `app/api/v1/deps.py`. Es un detalle, pero define el layout del vertical slice.
    - `design.md:196-209` promete "4 tablas" y `proposal.md:54-58` lista 4, pero no define el DDL de
      `session`, `auth_event` ni `password_reset_token` (sólo `refresh_token`); ver hueco 5.

### Mejoras (no bloquean por sí solas)

13. **RN-AU-05 cita `audit_log` literalmente** (`05_reglas_de_negocio.md:64-65`), pero el change
    escribe `auth_event` y declara `audit_log` fuera de alcance (C-14). La desviación está declarada
    (`proposal.md:121-122`, `design.md:290-292`), pero la spec la cita como cumplida sin aclarar el
    reemplazo; conviene una nota en R3 y en `docs/auth.md`.
14. **`Secure` en producción no se verifica en ninguna tarea.** S1.1 exige `Secure` salvo local/test
    (`spec.md:24-25`), pero la tarea 3.1 sólo comprueba el caso sin `Secure` (`tasks.md:29`). El design
    promete "un test dedicado" (`design.md:248-249`) que no aparece en `tasks.md`. Igual falta el
    atributo `Path` en la verificación.
15. **Recuperación de contraseña no cita fuente de regla.** No hay RN para reset; la fuente es
    `03_actores_y_roles.md:90` (token de un solo uso, 30 min). Citar esa sección evita que parezca una
    regla inventada. Además, en producción el flujo no entrega el token (PQ-08); está declarado
    (`design.md:282-285`), pero el capability del proposal podría rotularlo "solo dev".
16. **`password_reset_token` con "sin SELECT amplio" es ambiguo** (`design.md:123`). El consumo
    `UPDATE ... WHERE token_hash = :h RETURNING user_id` necesita privilegios de `SELECT` sobre las
    columnas usadas; hay que definir grants por columna (o `SELECT` acotado) y testearlo, o el
    implementador puede elegir un grant que rompa el flujo o que sea demasiado amplio.
17. **`session_expired` (401) está en el catálogo** (`design.md:216`, `tasks.md:14`) pero ningún
    escenario lo usa: todos los 401 de sesión se describen sin `code`. Definir qué endpoint devuelve
    `session_expired` vs. `401` genérico, o quitarlo del catálogo.
18. **Criterios del TPI**: el límite con C-04 está declarado en Out of Scope (`proposal.md:111-113`,
    `design.md:33`), lo cual es correcto, pero la tabla de criterios presenta "Autenticación y
    permisos — acceso autorizado" como cubierto por `require_auth`/`require_tenant`
    (`proposal.md:132`), sin aclarar que la autorización **por rol/permiso** llega en C-04. Agregar una
    nota de una línea en esa tabla.
19. **`auth_event` sin RLS y sin `SELECT` para el rol de app** (`design.md:117-125`, `tasks.md:24`),
    pero la tarea 4.1 verifica su contenido (`tasks.md:40`). Hay que decir explícitamente que ese test
    consulta como superusuario (o el rol de test), porque `odontologia_app` no puede leerla.
20. **S6.4 "Operar en A no filtra datos de B"** se verifica con `3.8`/`7.1`, que prueban lectura
    (`tenant_id` de body ignorado) pero no "ni escribe" (`spec.md:215-219`). Agregar una aserción de
    escritura cross-tenant en el camino autenticado (o cambiar el texto del escenario).

## Tenancy (RN-TEN-02)
- [x] El change toca tablas con `tenant_id` (`session`, `refresh_token`; `auth_event` nullable y
      `password_reset_token` globales, justificados en `design.md:111-125`).
- [x] Hay escenario cross-tenant: R8 S8.1/S8.2 (SQL) y R6 S6.4 (A≠B).
- [x] `tenant_id` sale de la sesión en operaciones autenticadas (R6 S6.3, R7); las dos excepciones
      —`tenant_slug` en login y tenant destino en `switch-tenant`— están justificadas por membership,
      aunque la segunda contradice la redacción de S6.3 (hueco 11).
- [x] `tasks.md` incluye el test de aislamiento con `SET ROLE odontologia_app` (2.3, 2.5) y prueba de
      mutación (2.5).

**Resultado del check**: los cuatro casilleros de la skill están cubiertos, pero el gate no queda
verde por dos motivos que van más allá del checklist:
1. **Bloqueante B1**: con RLS `FORCE` y sin contexto, refresh/`require_auth`/reset no pueden resolver
   las filas que necesitan; el contrato actual es incoherente, no sólo incompleto.
2. **Test de aislamiento a nivel endpoint**: RN-TEN-02 pide un test por **endpoint** que toque una
   tabla con `tenant_id`; hoy sólo hay tests SQL (2.3/2.5). Además la app no declara con qué rol se
   conecta, y los tests HTTP correrían como superusuario (RLS ignorada). Falta una tarea de
   `client` + `odontologia_app` y un caso "sesión de A no puede refrescar/leer/cerrar la sesión de B".

## Verificación en tasks.md (32 escenarios)

| # | Escenario (`spec.md`) | Tarea(s) | Estado |
|---|----------------------|----------|--------|
| S1.1 | Login válido emite cookies y sesión del tenant | 3.1, 3.2 | ⚠️ 3.1 no verifica body ni `Path`/`Secure` en producción |
| S1.2 | Credenciales inválidas sin sesión | 3.1 | ✅ |
| S1.3 | Membership inactiva / tenant inexistente | 3.1 | ✅ (pero es variante de error, no borde) |
| S2.1 | Refresh válido rota y conserva sesión | 3.3, 3.4 | ⚠️ no afirma `Set-Cookie` distinto |
| S2.2 | Reuse revoca la familia | 3.3 | ✅ |
| S2.3 | Expirado/revocado no afecta otras familias | 3.3 | ⚠️ no verifica que la otra familia siga refrescando con `200` |
| S2.4 | Dos refresh concurrentes | 3.5 | ✅ |
| S2.5 | Logout idempotente | 3.5 | ✅ |
| S3.1 | 4 fallos / 5.º bloquea 15 min | 4.1 | ✅ |
| S3.2 | Password correcto en bloqueo no entra | 4.1 | ✅ |
| S3.3 | Bloqueo expira y resetea | 4.1 | ✅ |
| S3.4 | Backoff duplicado + lockout por cuenta | 4.1 | ✅ |
| S4.1 | Owner enrolado completa step-up | 5.1, 5.2 | ⚠️ desafío `HttpOnly`/TTL sin verificación explícita |
| S4.2 | TOTP inválido/reusado cuenta para lockout | 5.1 | ⚠️ depende de `last_used_step` no modelado (hueco 6) |
| S4.3 | Owner/billing sin secreto debe enrolar | 5.1 | ✅ |
| S4.4 | Roles sin MFA + secreto nunca expuesto | 5.1, 5.3 | ✅ |
| S5.1 | Reset consume el token una sola vez | 6.1 | ⚠️ "revoca todas las sesiones" choca con RLS (B1) |
| S5.2 | Token expirado/usado/manipulado | 6.1 | ✅ |
| S5.3 | Email inexistente responde igual | 6.1 | ✅ |
| S5.4 | Token no expuesto fuera de dev | 6.1 | ✅ |
| S6.1 | Switch a tenant con membership activa | 7.1 | ⚠️ sin MFA si B es `owner`/`billing` (B2) |
| S6.2 | Switch sin membership no rompe A | 7.1 | ✅ |
| S6.3 | Tenant del body/query ignorado | 3.8, 7.1 | ⚠️ contradice el contrato de `switch-tenant` (hueco 11) |
| S6.4 | Operar en A no filtra B | 3.8, 7.1 | ⚠️ cubre lectura, no escritura |
| S7.1 | `/me` válido sin secretos | 3.6, 3.7 | ✅ (implementabilidad en B1) |
| S7.2 | Sin sesión o revocada → 401 | 3.6 | ✅ |
| S7.3 | Cookie manipulada/expirada/membership off | 3.6 | ✅ |
| S8.1 | Un tenant ve sólo sus sesiones/refresh | 2.3 | ✅ |
| S8.2 | Escritura cross-tenant rechazada | 2.5 | ✅ |
| S8.3 | Sin contexto → 0 filas | 2.3 | ✅ |
| S8.4 | Prueba de mutación del aislamiento | 2.5 | ❌ receta inválida (hueco 4) |
| S8.5 | `auth_event` append-only y no leída por API | 2.6 | ✅ |

**Confirmación**: los **32/32 escenarios tienen al menos una tarea mapeada**. La excepción de fondo es
S8.4: está mapeada a la tarea 2.5, pero la receta de esa tarea no produce el resultado que el escenario
afirma (dropear la política deja 0 filas, no expone las de B). S1.1 y S4.1 tienen sub-afirmaciones
(cookies `Secure`/`Path`, `HttpOnly`/TTL del desafío) sin verificación explícita.

## Afirmaciones del design contra el código real

| Afirmación del change | Código real | Resultado |
|-----------------------|-------------|-----------|
| `user.mfa_secret` ya existe desde C-02 (`design.md:138`) | `backend/app/models/tenancy.py:92` | ✅ |
| `User` tiene `password_hash`, `activo`, `last_login_at` | `tenancy.py:84-92` | ✅ |
| `Membership` tiene `tenant_id`, `rol`, `activo` | `tenancy.py:116-129` | ✅ |
| Faltan columnas de lockout/MFA en `user` y las agrega `003_auth` | no existen en `tenancy.py:84-92` | ✅ coherente |
| `003_auth` con `down_revision = "002_core_tenancy"` y 003 libre | `alembic/versions/` sólo `c01_baseline.py` y `002_core_tenancy.py`; head = `002_core_tenancy` | ✅ |
| `set_config('app.current_tenant', :tenant_id, true)` transaction-local | `backend/app/db/tenant_context.py:19-34` | ✅ |
| Rol `odontologia_app` NOLOGIN NOSUPERUSER NOBYPASSRLS y `SET ROLE` en tests | `002_core_tenancy.py:141`, `test_core_tenancy_migration.py:77-88` | ✅ |
| Predicado RLS con `NULLIF(current_setting(...), '')::uuid` | `002_core_tenancy.py:146` | ✅ |
| "No existe ... router ... en el frontend" (`design.md:9-10`) | `frontend/src/main.tsx` (BrowserRouter), `App.tsx` (Routes), `react-router-dom` en `package.json` | ❌ el router ya existe |
| "Vite proxy a `/api`" (`design.md:56-57`) | `frontend/vite.config.ts` no tiene `server.proxy`; backend sin CORS | ❌ no existe y no hay tarea |
| e2e en `frontend/e2e/auth.spec.ts` (`tasks.md:66`) | `playwright.config.ts:5` usa `testDir: './tests/e2e'` | ❌ ruta incorrecta |
| `backend/.env.example` (`tasks.md:5`) | el archivo real es `.env.example` en la raíz (`test_env_example.py`) | ❌ ruta incorrecta |
| `403 mfa_challenge` (`proposal.md:45`) | design/spec/tasks usan `mfa_required`/`mfa_enrollment_required` | ❌ contrato inconsistente |
| `session`/`refresh_token` con RLS y flujo de refresh resoluble antes del contexto | `docs/core-tenancy.md:86-87` (sin contexto = 0 filas) + `design.md:61-67` | ❌ contradicción (B1) |

## Próximo paso

1. **Cerrar B1 (tenancy) en `design.md` y `spec.md`**: decidir el mecanismo de resolución pre-contexto
   para refresh (`SECURITY DEFINER` acotado, tabla de lookup no-RLS, o tenant firmado en la cookie),
   el orden `require_auth`/`require_tenant` (quién fija el GUC y con qué claims), y cómo se revocan
   las sesiones de todos los tenants en `reset-password`. Agregar el escenario y la tarea del test de
   aislamiento **a nivel endpoint** con `SET ROLE odontologia_app`.
2. **Cerrar B2 (RN-AU-04)**: escenario y tarea para `switch-tenant` cuando el tenant destino tiene
   roles `owner`/`billing` (step-up o `mfa_enrollment_required`), y definir el alcance del
   `mfa_satisfied` entre tenants.
3. **Antes de aplicar**: agregar el borde de R1; corregir la receta de mutación (S8.4/2.5); definir el
   DDL de `session`/`auth_event` y el estado de replay/desafío MFA; declarar las tareas de
   engine/sesión + fixture HTTP + rol de conexión; corregir `.env.example`/`BASE_ENV`, la ruta de
   Playwright, el proxy de Vite y la actualización de `App.test.tsx`/`smoke.spec.ts`; unificar
   `mfa_challenge` → `mfa_required`; acotar S6.3 respecto de `switch-tenant`.
4. Recién entonces volver a correr `spec-scenario-review` y pasar a `/opsx:apply`.
