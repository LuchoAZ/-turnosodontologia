# Design

## Context

Ver `proposal.md` — Why para la motivación y `specs/agenda/appointments/spec.md` para el contrato observable. Estado actual del repo (2026-11-05): C-01 y C-02 están **archivados**; C-02 dejó la base de tenancy (rol `odontologia_app`, contexto de tenant con `set_config` y RLS fail-closed) pero **excluyó explícitamente** `chair`, `professional`, `patient` y `appointment` de su alcance. Por eso este change **es dueño del modelo `appointment` y del `EXCLUDE USING gist`** (sección 0 de `tasks.md`) y depende de C-03 (sesión/scoping), C-05 (`chair`, `professional`, `availability_rule`) y C-06 (`patient`).

Restricciones dominantes: governance **MEDIO** (lógica de negocio), strict TDD con vertical slices (DD-03), RN-TEN-02 como gate de merge, y el stack fijo (FastAPI + Python 3.12 + React 18/Vite + SQLAlchemy 2.0 + PostgreSQL 16, contrato OpenAPI/Pydantic).

## Goals / Non-Goals

**Goals:**
- Crear el turno reservando **dos recursos a la vez** (`professional_id` + `chair_id`, RN-AG-01) en una **transacción**.
- Prevenir solapamientos con **doble mecanismo**: (a) validación en aplicación que responde `409` amigable con recurso y rango en conflicto, y (b) **garantía dura en PostgreSQL** — `EXCLUDE USING gist` sobre `chair_id` y `professional_id` con `tstzrange` (RN-AG-02) — que la BD rechaza el doble booking bajo concurrencia aunque la validación de aplicación no lo vea.
- Derivar duración y buffers desde `tipo_practica`/`availability_rule` (RN-AG-03) y operar todo en UTC (RN-AG-09).
- Aislar por tenant: `tenant_id` solo de la sesión/token (RN-TEN-03), RLS activa, cruce de tenant → `404` (RN-TEN-02).
- Entregar el slice vertical completo: API + formulario mínimo de UI con el mismo contrato Pydantic/OpenAPI.

**Non-Goals:**
- Reprogramar/reschedule, cancelar, check-in/complete, lista de espera, `GET /availability`, vistas de agenda (C-07/C-08).
- Portal paciente, reserva pública, WhatsApp (C-19/C-20).
- Idempotency key (RN-EX-02 aplica a cliente externo vía webhook/portal/API key; acá el `origen = recepcion` es cliente interno — el portal C-20 lo resolverá).
- Optimistic locking vía `appointment.version` (defensa secundaria que cierra C-07; este change usa el `EXCLUDE` como garantía).
- RN-AG-06 (equipo de RX único): depende de la configuración de sillones de C-05 y de la semántica de "otro sillón `rx` activo"; este change no la implementa. La regla queda declarada como deuda explícita para C-07.

## Decisions

**D1 — Slice vertical `appointments` en el backend FastAPI como módulo de feature (no por capas).**
`backend/app/domain/agenda/appointments/` (router + service + DTO Pydantic + dependencia de tenant), siguiendo DD-03: API + UI de la capacidad en el mismo change. El service compone la dependencia de tenant (provista por C-03) que resuelve `tenant_id` del token/sesión.
- Alternativas: servicio global `appointments.service.py` compartido por capa (viola DD-03), o lógica en el router (no testeable como seam).

**D2 — Doble mecanismo anti-solapamiento, con la BD como garantía final.**
El flujo de creación corre dentro de una transacción de SQLAlchemy (`session.begin()`):
1. Resolver `tenant_id` de la sesión (nunca del body, RN-TEN-03) y abrir la sesión de BD con `SELECT set_config('app.current_tenant', :tenant_id, true)` (bindeado, transaction-local).
2. Leer `professional`, `chair` y `patient` **scoped al tenant** (`WHERE id = ? AND tenant_id = current`); si falta alguno → `404` (RN-EX-06; no distingue recurso inexistente de ajeno); si `professional.activo = false` o `chair.activo = false` → `409` `motivo = recurso_inactivo`.
3. Pre-chequeo de solape en aplicación: overlap query sobre el **rango bloqueado** (`inicio - buffer_previo`, `fin + buffer_posterior`) con `estado NOT IN ('cancelado','no_asistio')` para `professional_id` y `chair_id`, y RN-AG-10 (`estado IN ('pendiente','confirmado','en_curso')` por paciente+profesional, solo si `patient_id` no es NULL). Si hay solape → `409` con `resource` y `rangoEnConflicto` del turno encontrado. El rango es semiabierto —`[inicio, fin)`—, así que un turno contiguo no es solape.
4. Insert del turno. Si la BD lanza *exclusion violation* (`SQLSTATE 23P01`) por el `EXCLUDE USING gist` (race entre 3 y 4), el filtro de excepciones la mapea a `409` con el mismo contrato.
- Alternativas: **solo** validación en aplicación (tiene race conditions — explícitamente descartada por RN-AG-02), **solo** `EXCLUDE` (el `409` amigable con rango depende de parsear el error de la BD).
- Por qué: RN-AG-02 manda que la garantía sea de BD; la aplicación agrega el mensaje accionable y un único contrato de error en ambos caminos.

**D3 — Cálculo de rango como función pura (seam de TDD).**
`resolveTurnoRange({ inicio, tipoPractica, professional, rule }) → { inicio, fin, duracionMin, bufferPrevioMin, bufferPosteriorMin }` calcula la duración base con esta precedencia: (1) `rule.slot_min` de la `availability_rule` que matchea profesional (o `NULL`), sillón (o `NULL`), día y ventana, y declara el `tipo_practica`; (2) `professional.duracion_default_min`. Luego `duracion_min` se persiste, `fin = inicio + duracion_min`, y los buffers de la regla aplicable se guardan como snapshot en el turno. El **rango bloqueado** es `[inicio - buffer_previo_min, fin + buffer_posterior_min)` y es el que usan el pre-chequeo y el `EXCLUDE` (no solo el rango clínico), porque los buffers son tiempo real de higiene/esterilización (RN-AG-03). Una duración base `<= 0` es error de negocio (`duracion_invalida`), no un turno de duración cero.
- El payload **no** acepta `fin` ni `duracion_min`: el servidor los deriva (una sola fuente de verdad). `extra = "forbid"` hace que enviarlos devuelva `422`.
- Por qué `slot_min`: la KB define `availability_rule.slot_min` como la duración del slot y no existe una tabla de duración por `tipo_practica`; usar `slot_min` evita inventar esquema. **Supuesto explícito** a validar con el usuario/docente (ver Open Questions).
- Alternativas: resolver en SQL (difícil de testear y duplica lógica), o en el controller (no testeable sin levantar HTTP).

**D4 — Horarios: `timestamptz` (UTC) en datos, zona local en presentación.**
Wire format `RFC 3339`/ISO 8601 incluso en el DTO Pydantic (coerción a `datetime`); BD `timestamptz`; toda la lógica de negocio opera sobre `datetime` (RN-AG-09); la UI muestra en `tenant.timezone` (default `America/Argentina/Buenos_Aires`) con `date-fns-tz` y **nunca** serializa zonas a mano.
- Alternativas: strings con zona local del tenant (rompe RN-AG-09 y el solape con `tstzrange`), o milis (no legible en payloads).

**D5 — Un contrato de datos: schema Pydantic v2 en el backend que genera el OpenAPI.**
`CreateAppointment` (y modelos derivados) en `backend/app/schemas`, validado en FastAPI (`422` con detalle de campos) y del que el frontend deriva sus tipos TypeScript; el formulario usa Zod solo en el cliente para validar antes del submit. Un único contrato = sin divergencia frontend↔backend (regla dura del proyecto). El borde HTTP **descarta** `tenant_id` de body/query/header antes de validar (nunca se lee ni se rechaza por RN-TEN-03); el schema usa `extra = "forbid"` para el resto, de modo que `fin` y `duracion_min` enviados por el cliente devuelven `422`. Pydantic exige offset en `inicio`. El DTO de respuesta sí incluye `fin` y `duracion_min`, ya derivados.
- Alternativas: DTOs duplicados por lado (dos fuentes de verdad), o mapear por capas de API (duplica el DTO).

**D6 — Contrato HTTP de errores centralizado.**
Con un exception handler global de FastAPI: `201` creado; `409 { recurso, motivo?, rangoEnConflicto? }` para RN-AG-02/10 (`motivo = recurso_inactivo` o `duracion_invalida` cuando no hay solape); `422` para Pydantic; `404` para cross-tenant/recurso ausente del tenant; `401` sin sesión o sin membership activa. Los `409` de aplicación y de BD convergen al mismo shape (D2).

**D7 — Formulario mínimo como parte del slice vertical.**
Ruta `/turnos/nuevo` en React + Vite (React Router + shadcn/ui): selects de paciente/profesional/sillón cargados de los endpoints de C-05/C-06, `tipo_practica`, y `inicio` en datetime-local convertido a UTC al submit. Mapa de errores del endpoint: `409` → mensaje de conflicto con recurso, `422` → errores por campo, `404` → "recurso no encontrado o sin acceso". Sin grilla de disponibilidad (C-08).
- Alternativas: solo API sin UI (viola DD-03), o UI completa de agenda (scope creep → C-08).

**D8 — Tests de integración con Postgres real y 2 tenants siempre.**
pytest + Testcontainers (nunca mock de BD en flujos con RLS/tenancy): cada suite siembra **como mínimo** el tenant A (sujeto) y un tenant B extra, de modo que el test cross-tenant (gate RN-TEN-02) sea parte del setup, no un caso especial. SQLAlchemy con `SELECT set_config('app.current_tenant', :tenant_id, true)` por transacción y `SET ROLE odontologia_app` en los tests que corran como superusuario (el superusuario ignora RLS y el verde sería falso).

### Seams de TDD (a confirmar antes de escribir tests)

- **`resolveTurnoRange`** (pura, sin BD): duración por tipo, buffers heredados, default del profesional, fin > inicio.
- **Servicio `createAppointment`** (integración con Postgres real): scoping al tenant, pre-chequeo de solape por profesional/sillón y RN-AG-10, 404 de recurso ajeno, mapeo de `23P01 → 409`.
- **HTTP** (`httpx.AsyncClient`/`TestClient`): `201`/`409`/`422`/`404`/`401` como contrato observable.
- **Concurrencia**: dos `create` simultáneos sobre el mismo recurso → uno `201`, otro `409` (lo rechaza el `EXCLUDE`).
- **UI** (Playwright, con API real o tipada por contrato): alto ok, conflicto visible, error 404 legible.

## Project Standards (auto-resolved)

- **tdd**: red → green → (refactor fuera del loop); costuras acordadas arriba; vertical slices (un test → una implementación → repetir). Tests leen como spec público; prohibidos los tautológicos (no recomputar `fin` con la misma función bajo test).
- **SQLAlchemy 2.0**: transacciones con `session.begin()`; `select(...).where(...)` scoped por tenant; mapeo de infracciones de exclusión (23P01, `IntegrityError`) a `409`.
- **supabase-postgres-best-practices**: RLS verificada con tests (cross-tenant leak = 0, RN-TEN-02); el `EXCLUDE USING gist` requiere la extensión `btree_gist`, que crea la migración `009_agenda` de este change; los índices `idx(tenant_id, inicio)` e `idx(patient_id, inicio)` soportan el overlap query.
- **FastAPI**: router por feature (D1); dependencias inyectadas (`Depends`); exception handler centralizado (D6); validación de todo input con Pydantic; `HTTPException` de FastAPI.
- **vercel-react-best-practices**: cargar referencias (pacientes/profesionales/sillones) en paralelo con `Promise.all`; evitar waterfalls en el form; `React.cache()` donde se re-lea el mismo dato.

## Risks / Trade-offs

- **[Validación de aplicación con race condition]** La ventana entre overlap-check e insert permite doble booking concurrente. → Mitigación: el `EXCLUDE USING gist` es la garantía final (D2); el test de concurrencia lo demuestra; el `409` de BD reusa el mismo contrato de error.
- **[Mapeo del error de exclusión]** El código exacto del driver para `23P01` puede variar según la versión de SQLAlchemy/psycopg. → Mitigación: el filtro captura el error por `SQLSTATE`/mensaje y testea el resultado observable (409), no el código interno; se pinnea la versión al aplicar.
- **[Dependencias no implementadas al momento del apply]** C-03/C-05/C-06 deben existir (sesión/tenant, `chair`/`professional`/`availability_rule`, `patient`). C-02 **no** aporta `appointment`: este change crea el modelo, el `EXCLUDE` y su RLS en la migración `009_agenda`. → Mitigación: requisitos previos explícitos en `tasks.md`; la sección 0 es DDL propio, no un prerequisito ajeno.
- **[UI mínima sin grilla]** El recepcionista no ve disponibilidad; un horario ocupado devuelve 409 post-submit. → Trade-off aceptado del alcance (C-08 agrega la grilla); el `409` es el mecanismo definido del spec.
- **[Sin idempotency]** Dos submis del mismo form podrían crear dos turnos (distintos rangos) — no hay `idempotency_key` en este change. → Mitigación: `origen = recepcion` es cliente interno (RN-EX-02 no aplica); el form previene doble submit en el cliente como mitigación de UX.

## Migration Plan

La migración `009_agenda` (o el siguiente número libre al aplicar) crea `appointment` con `tenant_id NOT NULL`, RLS `FORCE`, `duracion_min`, `buffer_previo_min` y `buffer_posterior_min` (snapshot, NOT NULL default 0), `EXCLUDE USING gist` por `professional_id` y `chair_id` sobre el rango bloqueado, `CHECK (fin > inicio)`, índices `(tenant_id, inicio)` y `(patient_id, inicio)`, y los grants al rol `odontologia_app`. Requiere `btree_gist` y las tablas de C-05/C-06; `down_revision` = head real de Alembic al momento del apply. `upgrade` y `downgrade` se prueban en Testcontainers; sin datos que migrar ni despliegue en producción: rollback = `alembic downgrade` + `git revert` del commit del change.

## Open Questions

- **Fuente de la duración por tipo de práctica**: la KB no define una tabla de duración por `tipo_practica`; este design usa `availability_rule.slot_min` y, en su defecto, `professional.duracion_default_min` (D3). Confirmar con el docente/usuario antes del apply; si se define un catálogo, solo cambia `resolveTurnoRange`, no el contrato HTTP.
- **Código exacto del error de exclusión**: se resuelve al aplicar (pinner de SQLAlchemy/psycopg); no cambia spec, approach ni tasks (el contrato observable es 409).
- **Convención de nombres de rutas/UI**: `/turnos/nuevo` vs `/appointments/nuevo` — se alinea con lo que C-07 decida; no afecta el contrato del spec.