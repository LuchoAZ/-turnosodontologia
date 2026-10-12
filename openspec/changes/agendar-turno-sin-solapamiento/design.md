# Design

## Context

Ver `proposal.md` — Why para la motivación y `specs/agenda/appointments/spec.md` para el contrato observable. Estado actual del repo: solo existe `openspec/changes/c-01-foundation-setup` propuesto; el monorepo y las capacidades de las que depende este change **no están implementadas todavía**. Este change es la segunda entrega de la "ruta del turno" del Sprint 1 dev y se apoya en capacidad previa provista por sus dependencias: el modelo `appointment` con `EXCLUDE USING gist` (C-02/C-07), sesión y scoping de tenant (C-03), `chair`/`professional`/`availability_rule` (C-05) y `patient` (C-06).

Restricciones dominantes: governance **MEDIO** (lógica de negocio), strict TDD con vertical slices (DD-03), RN-TEN-02 como gate de merge, y el stack fijo (NestJS 11 + Next.js 15 + Prisma 6 + PostgreSQL 16, Zod compartido).

## Goals / Non-Goals

**Goals:**
- Crear el turno reservando **dos recursos a la vez** (`professional_id` + `chair_id`, RN-AG-01) en una **transacción**.
- Prevenir solapamientos con **doble mecanismo**: (a) validación en aplicación que responde `409` amigable con recurso y rango en conflicto, y (b) **garantía dura en PostgreSQL** — `EXCLUDE USING gist` sobre `chair_id` y `professional_id` con `tstzrange` (RN-AG-02) — que la BD rechaza el doble booking bajo concurrencia aunque la validación de aplicación no lo vea.
- Derivar duración y buffers desde `tipo_practica`/`availability_rule` (RN-AG-03) y operar todo en UTC (RN-AG-09).
- Aislar por tenant: `tenant_id` solo de la sesión/token (RN-TEN-03), RLS activa, cruce de tenant → `404` (RN-TEN-02).
- Entregar el slice vertical completo: API + formulario mínimo de UI con el mismo schema Zod.

**Non-Goals:**
- Reprogramar/reschedule, cancelar, check-in/complete, lista de espera, `GET /availability`, vistas de agenda (C-07/C-08).
- Portal paciente, reserva pública, WhatsApp (C-19/C-20).
- Idempotency key (RN-EX-02 aplica a cliente externo vía webhook/portal/API key; acá el `origen = recepcion` es cliente interno — el portal C-20 lo resolverá).
- Optimistic locking vía `appointment.version` (defensa secundaria que cierra C-07; este change usa el `EXCLUDE` como garantía).

## Decisions

**D1 — Slice vertical `appointments` en NestJS como módulo de feature (no por capas).**
`apps/api/src/appointments/` (controller + service + DTO Zod + guard de tenant), siguiendo DD-03: API + UI de la capacidad en el mismo change. El servicio compone el guard de tenant (provisto por C-03) que resuelve `tenant_id` del token/sesión.
- Alternativas: servicio global `appointments.service.ts` compartido por capa (viola DD-03), o lógica en el controller (no testeable como seam).

**D2 — Doble mecanismo anti-solapamiento, con la BD como garantía final.**
El flujo de creación corre dentro de `prisma.$transaction`:
1. Resolver `tenant_id` de la sesión (nunca del body, RN-TEN-03) y abrir la sesión de BD con `SET LOCAL app.current_tenant`.
2. Ler `professional`, `chair` y `patient` **scoped al tenant** (`WHERE id = ? AND tenant_id = current`); si falta alguno → `404` (RN-EX-06; no distingue recurso inexistente de ajeno).
3. Pre-chequeo de solape en aplicación: overlap query `inicio < nuevo.fin AND fin > nuevo.inicio` con `estado NOT IN ('cancelado','no_asistio')` para `professional_id` y `chair_id`, y RN-AG-10 (`estado IN ('pendiente','confirmado','en_curso')` por paciente+profesional). Si hay solape → `409` con `resource` y `rangoEnConflicto` del turno encontrado.
4. Insert del turno. Si la BD lanza *exclusion violation* (`SQLSTATE 23P01`) por el `EXCLUDE USING gist` (race entre 3 y 4), el filtro de excepciones la mapea a `409` con el mismo contrato.
- Alternativas: **solo** validación en aplicación (tiene race conditions — explícitamente descartada por RN-AG-02), **solo** `EXCLUDE` (el `409` amigable con rango depende de parsear el error de la BD).
- Por qué: RN-AG-02 manda que la garantía sea de BD; la aplicación agrega el mensaje accionable y un único contrato de error en ambos caminos.

**D3 — Cálculo de rango como función pura (seam de TDD).**
`resolveTurnoRange({ inicio, tipoPractica, professional, rule }) → { inicio, fin }` calcula duración y hereda `buffer_previo_min`/`buffer_posterior_min` (RN-AG-03); `fin = inicio + duración + buffer_previo + buffer_posterior`. Selección de regla: `availability_rule` con `professional_id` coincidente o `NULL` (aplica a todos). Sin `tipo_practica` ni regla → `duracion_default_min` del profesional con buffers 0.
- Alternativas: resolver en SQL (difícil de testear y duplica lógica), o en el controller (no testeable sin levantar HTTP).

**D4 — Horarios: `timestamptz` (UTC) en datos, zona local en presentación.**
Wire format `RFC 3339`/ISO 8601 incluso en el DTO Zod (coerción a `Date`); BD `timestamptz`; toda la lógica de negocio opera sobre `Date` (RN-AG-09); la UI muestra en `tenant.timezone` (default `America/Argentina/Buenos_Aires`) con `date-fns-tz` y **nunca** serializa zonas a mano.
- Alternativas: strings con zona local del tenant (rompe RN-AG-09 y el solape con `tstzrange`), o milis (no legible en payloads).

**D5 — Un solo contrato Zod en `packages/shared`.**
`CreateAppointmentSchema` (y tipos derivados) consumido por NestJS (validación del body, `422` con detalle de `error.issues`) y por el formulario Next.js (validación antes del submit). Mismo schema = sin divergencia frontend↔backend (regla dura del proyecto). `z.coerce.date()` valida ISO y Timezone.
- Alternativas: DTOs separados por app con `class-validator` (dos fuentes de verdad), matear por capas de API (duplica el DTO).

**D6 — Contrato HTTP de errores centralizado.**
Con `ExceptionFilter` global: `201` creado; `409` `{ recurso, rangoEnConflicto }` para RN-AG-02/10; `422` para Zod; `404` para cross-tenant/recurso ausente del tenant; `401` sin sesión. Los `409` de aplicación y de BD convergen al mismo shape (D2).

**D7 — Formulario mínimo como parte del slice vertical.**
Ruta `/turnos/nuevo` en Next.js 15 (App Router + shadcn/ui): selects de paciente/profesional/sillón cargados de los endpoints de C-05/C-06, `tipo_practica`, y `inicio` en datetime-local convertido a UTC al submit. Mapa de errores del endpoint: `409` → mensaje de conflicto con recurso, `422` → errores por campo, `404` → "recurso no encontrado o sin acceso". Sin grilla de disponibilidad (C-08).
- Alternativas: solo API sin UI (viola DD-03), o UI completa de agenda (scope creep → C-08).

**D8 — Tests de integración con Postgres real y 2 tenants siempre.**
Vitest + Testcontainers (nunca mock de BD en flujos con RLS/tenancy): cada suite siembra **como mínimo** el tenant A (sujeto) y un tenant B extra, de modo que el test cross-tenant (gate RN-TEN-02) sea parte del setup, no un caso especial. Prisma con `SET LOCAL app.current_tenant` por transacción (middleware/extensión provista por C-02).

### Seams de TDD (a confirmar antes de escribir tests)

- **`resolveTurnoRange`** (pura, sin BD): duración por tipo, buffers heredados, default del profesional, fin > inicio.
- **Servicio `createAppointment`** (integración con Postgres real): scoping al tenant, pre-chequeo de solape por profesional/sillón y RN-AG-10, 404 de recurso ajeno, mapeo de `23P01 → 409`.
- **HTTP** (`supertest`): `201`/`409`/`422`/`404`/`401` como contrato observable.
- **Concurrencia**: dos `create` simultáneos sobre el mismo recurso → uno `201`, otro `409` (lo rechaza el `EXCLUDE`).
- **UI** (Playwright, con API real o tipada por contrato): alto ok, conflicto visible, error 404 legible.

## Project Standards (auto-resolved)

- **tdd**: red → green → (refactor fuera del loop); costuras acordadas arriba; vertical slices (un test → una implementación → repetir). Tests leen como spec público; prohibidos los tautológicos (no recomputar `fin` con la misma función bajo test).
- **prisma-client-api**: transacciones con `$transaction`; `findFirst`/`findMany` con `where` scoped por tenant; mapeo de infracciones de exclusión (23P01) y de `P2002` a `409`.
- **supabase-postgres-best-practices**: RLS verificada con tests (cross-tenant leak = 0, RN-TEN-02); el `EXCLUDE USING gist` requiere la extensión `btree_gist` (provista por C-02 en `008_agenda`); los índices existentes (`idx(tenant_id, inicio)`, `idx(patient_id, inicio)`) soportan el overlap query.
- **nestjs-best-practices**: módulo por feature (D1); inyección por constructor; `ExceptionFilter` centralizado (D6); validación de todo input; tirar excepciones HTTP de Nest.
- **vercel-react-best-practices**: cargar referencias (pacientes/profesionales/sillones) en paralelo con `Promise.all`; evitar waterfalls en el form; `React.cache()` donde se re-lea el mismo dato.

## Risks / Trade-offs

- **[Validación de aplicación con race condition]** La ventana entre overlap-check e insert permite doble booking concurrente. → Mitigación: el `EXCLUDE USING gist` es la garantía final (D2); el test de concurrencia lo demuestra; el `409` de BD reusa el mismo contrato de error.
- **[Mapeo del error de exclusión en Prisma]** El código exacto del driver para `23P01` puede variar según la versión de Prisma/adapter. → Mitigación: el filtro captura el error por `SQLSTATE`/mensaje y testea el resultado observable (409), no el código interno; se pinnea la versión al aplicar.
- **[Dependencias no implementadas al momento del apply]** C-02/C-03/C-05/C-06 deben existir (modelo `appointment` con `EXCLUDE`, sesión/tenant, `chair`/`professional`/`availability_rule`, `patient`). → Mitigación: requisitos previos explícitos en tasks; este change es de integración vertical sobre ese stack, no escribe el modelo.
- **[UI mínima sin grilla]** El recepcionista no ve disponibilidad; un horario ocupado devuelve 409 post-submit. → Trade-off aceptado del alcance (C-08 agrega la grilla); el `409` es el mecanismo definido del spec.
- **[Sin idempotency]** Dos submis del mismo form podrían crear dos turnos (distintos rangos) — no hay `idempotency_key` en este change. → Mitigación: `origen = recepcion` es cliente interno (RN-EX-02 no aplica); el form previene doble submit en el cliente como mitigación de UX.

## Migration Plan

No requiere migración nueva si C-02 ya provee `appointment` con `EXCLUDE USING gist` + RLS (migración `008_agenda`, extensión `btree_gist`). Si al aplicar faltara la restricción, se agrega en un delta de la misma migración de C-02 (prerequisito, fuera del scope de este change). Sin datos que migrar ni despliegue en producción: rollback = `git revert` del commit del change.

## Open Questions

- **Código exacto del error de exclusión**: se resuelve al aplicar (pinner de Prisma); no cambia spec, approach ni tasks (el contrato observable es 409).
- **Convención de nombres de rutas/UI**: `/turnos/nuevo` vs `/appointments/nuevo` — se alinea con lo que C-07 decida; no afecta el contrato del spec.