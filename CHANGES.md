# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **Gestión Odontológica PyME** (`odontologia-saas`).
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

---

## Cómo usar este documento

1. Identificar el change a implementar (verificar que sus dependencias están en `openspec/changes/archive/`).
2. Leer los docs de la knowledge-base indicados en "Leer antes".
3. Ejecutar `/opsx:propose <nombre-del-change>`.
4. Implementar las tasks y **verificar** (tests + funcionamiento real).
5. Archivar con `/opsx:archive <nombre-del-change>`.
6. Marcar el estado real en este archivo (§ Estado del roadmap).

## Cuándo cuenta un change (definición de terminado)

Un change cuenta solo si recorrió el ciclo completo. Los cuatro gates son acumulativos y ninguno se
puede saltear:

| Gate | Qué exige | Evidencia en el repo |
|------|-----------|----------------------|
| **1. Propuesto** | `proposal.md` (propósito y alcance), `design.md` (decisiones), `specs/**/spec.md` (escenarios verificables) y `tasks.md` | `openspec/changes/<nombre>/` |
| **2. Aplicado** | Implementación integrada y todas las tasks del alcance completadas | Código en `backend/` y `frontend/`, tasks `[x]` |
| **3. Verificado** | Tests automatizados de los escenarios **ejecutados** (`pytest`, `vitest`, `playwright`) + prueba de funcionamiento real contra el backend. Archivar no reemplaza probar | Salida de tests documentada (`docs/<change>.md`) |
| **4. Archivado** | `openspec archive` + spec principal sincronizada + este roadmap actualizado | `openspec/changes/archive/YYYY-MM-DD-<nombre>/` |

> **Un change con funcionalidades incompletas o sin la verificación de su alcance NO se cuenta**,
> aunque la carpeta esté en `archive/`. Si una limitación impide verificar algo comprometido, se
> resuelve antes de contarlo. Los changes propuestos o en desarrollo se informan como tales y no se
> presentan como funcionalidad terminada.

> **Regla de oro (RN-TEN-02)**: ningún change que toque una tabla con `tenant_id` se considera
> terminado sin su test de aislamiento cross-tenant. Es gate de merge, no sugerencia.

> **Nota de alcance**: el proyecto se construye en **vertical slices** (DD-03). Cada change
> entrega API + UI de su capacidad. El plan vigente es para **1 developer** (SU-01) con
> **deadline 2026-10-23** (SU-02): ver **"Sprint 1 dev"** y **"Plan 1 dev"** más abajo. Los
> namespaces por agente del plan original quedaron obsoletos: la ejecución es secuencial.

> **Números de migración**: los que aparecen en cada change son **indicativos**. La numeración
> real vive en `backend/alembic/versions/` (`c01_baseline`, `002_core_tenancy`, `003_auth`,
> `004_rbac`, `005_clinic_setup`, `006_patients`, `007_agenda`). Al proponer un change, usá el
> siguiente número libre, no el del roadmap.

---

## Estado del roadmap (2026-11-12)

| Change | Estado | Evidencia |
|--------|--------|-----------|
| C-01 `foundation-setup` | ✅ **cuenta** — archivado (2026-11-05) | `openspec/specs/platform-runtime/spec.md`, `docs/foundation.md` — 32/32 tasks, tests en verde |
| C-02 `core-models-tenancy` | ✅ **cuenta** — archivado (2026-11-05) | `openspec/specs/platform-tenancy/spec.md`, `docs/core-tenancy.md` — 22/22 tasks, 56 tests, mutación |
| C-03 `auth-sessions` | ✅ **cuenta** — archivado (2026-11-10) | `openspec/specs/platform-auth/spec.md`, `docs/auth.md` — 54/54 tasks; `pytest` **193 passed**, `vitest` **22 passed**, `playwright` **6 passed** (4 de auth con navegador) |
| C-04 `rbac-permissions` | ✅ **cuenta** — archivado (2026-11-11) | `openspec/specs/platform-rbac/spec.md` + `platform-team/spec.md`, `docs/rbac.md` — 49/49 tasks; `pytest` **334 passed**, `vitest` **43 passed**, `playwright` **11 passed**; gate de escenarios pre-archive |
| C-05 `clinic-setup` | ✅ **cuenta** — archivado (2026-11-11) | `openspec/specs/clinic/setup/spec.md`, `docs/clinic.md` — 45/45 tasks; `pytest` **444 passed**, `vitest` **67 passed**, `playwright` **15 passed**; gate RN-TEN-02 con prueba de mutación |
| C-06 `patients` | ✅ **cuenta** — archivado (2026-11-12) | `openspec/specs/clinic/patients/spec.md`, `docs/patients.md` — 37/37 tasks; `pytest` **621 passed**, `vitest` **96 passed**, `playwright` **19 passed**; gate RN-TEN-02 con prueba de mutación; PQ-17 registrada |
| `agendar-turno-sin-solapamiento` | ✅ **cuenta** — archivado (2026-11-12) como `2026-11-12-agendar-turno-sin-solapamiento` | `openspec/specs/agenda/appointments/spec.md` (6 req., 26 escenarios), `docs/appointments.md` — 13/13 tasks; `pytest` **695 passed**, `vitest` **128 passed**, `playwright` **24 passed**; gate RN-TEN-02 con prueba de mutación + gate `spec-scenario-review` pre-archive |

> **Dos deadlines distintos**: el supuesto interno **SU-02 (2026-10-23)** es el deadline del
> plan de sprint de 1 dev; la **entrega académica del TPI es 2026-11-20**. El sprint es una
> guía de priorización, no un bloqueo.
>
> **Estado frente a los 5 criterios del TPI** (fundación, modelos/persistencia, auth/permisos,
> agenda, frontend): C-01 cubre el 1; C-02 + **C-05 y C-06 (archivados: sillones, profesionales,
> disponibilidad y ahora fichas de pacientes con HCE numerada, dedupe y RLS) cubren el 2**; C-03 +
> **C-04 (archivado: matriz de 61 permisos, guardas y rechazo de accesos inválidos, verificado en
> API y UI) cubren el 3**; **el criterio 4 quedó cubierto con `agendar-turno-sin-solapamiento`**
> (alta de turno sin solapamientos por profesional y sillón, duración derivada, RN-AG-10 y
> `EXCLUDE USING gist` como garantía de la base), y el criterio 5 avanza con las pantallas de
> Equipo, Clínica, Pacientes y **`/turnos/nuevo`** operando contra el backend real.

---

## Sprint 1 dev (2026-10-09 → 2026-10-23) — la "ruta del turno"

Alcance del deadline con **1 developer** (SU-01 confirmado) y **2 semanas** (SU-02 confirmado):

| Orden | Change | Estimación | Entregable |
|-------|--------|-----------|------------|
| 1 | C-01 foundation-setup | 1 día | Monorepo, tooling, CI, .gitignore |
| 2 | C-02 core-models-tenancy | 2 días | Modelos, migraciones, **RLS**, seed |
| 3 | C-03 auth-sessions | 2 días | Login/OTP, sesión, scoping de tenant |
| 4 | C-05 clinic-setup | 1.5 días | Sillones, profesionales, disponibilidad |
| 5 | C-06 patients | 1.5 días | Ficha de pacientes con HCE numerada y dedupe |
| 6 | **`agendar-turno-sin-solapamiento`** (núcleo de C-07 agenda-booking) | 3 días | **META (entregable TP)**: crear turno sin solapamientos — RN-AG-01/02/03/09/10 |

**Fuera de este sprint (backlog post-deadline)**: C-08…C-23, incluyendo toda la
facturación ARCA (C-14…C-17), con el mismo árbol de dependencias de abajo.

## Árbol de dependencias

```
C-01 foundation-setup
  └── C-02 core-models-tenancy                   ← CRITICO: RLS + todo lo referencia
        └── C-03 auth-sessions                    ← desbloquea TODO lo protegido
              │
              ├── C-04 rbac-permissions (✅ archivado 2026-11-11)
              ├── C-05 clinic-setup (✅ archivado 2026-11-11)
              ├── C-06 patients
              ├── C-16 fiscal-onboarding           ← independiente del dominio clínico
              └── C-18 comms-infra
                    │
                    ├── C-07 agenda-booking ◄── C-05 + C-06
                    │     ├── C-08 agenda-views
                    │     └── C-14 cash-settlements ◄── C-07 + C-12
                    │           └── C-15 invoicing-core ◄── C-16
                    │                 └── C-17 arca-emission
                    │                       ├── C-23 superadmin-console
                    │                       └── C-22 reports ◄── C-07
                    │
                    └── C-09 clinical-records ◄── C-06
                          └── C-10 odontogram-periodontogram
                                ├── C-11 consents
                                │     └── C-12 treatment-plans
                                └── C-13 audit-and-aaip

C-18 comms-infra ──► C-19 comms-flows ◄── C-07

C-07 + C-12 + C-18 ──► C-20 patient-portal
C-06 + C-07 ─────────► C-21 data-migration
```

### Plan 1 dev (secuencia lineal al 23/10)

```
Paso │ Change                     │ Días │ Semana
─────┼────────────────────────────┼──────┼───────
  1  │ C-01 foundation-setup      │  1   │ S1
  2  │ C-02 core-models-tenancy   │  2   │ S1
  3  │ C-03 auth-sessions         │  2   │ S1
  4  │ C-05 clinic-setup          │  1.5 │ S2
  5  │ C-06 patients              │  1.5 │ S2
  6  │ agendar-turno (núcleo C-07) │  3   │ S2  ← META (entregable TP)
```

**Reglas del sprint (1 dev)**:
- 6 changes, ~11 días efectivos; buffer de 3 días para imprevistos y QA.
- **Vertical slices**: cada change entrega API + UI de su capacidad (DD-03).
- **Gate de merge obligatorio**: test de aislamiento cross-tenant en todo endpoint con
  `tenant_id` (RN-TEN-02). No se rompe este gate ni bajo deadline.
- **QA diario**: suite completa en verde antes de cerrar el día.
- Si el sprint se atrasa, **se recorta C-07** (reserva sin lista de espera ni recordatorios),
  nunca se saltea RLS (C-02) ni auditoría base (C-03).

**Backlog post-deadline (23/10 en adelante)**: retomar el árbol de dependencias de arriba en el
mismo orden — C-04, C-08, C-09…C-23 — priorizando facturación (C-14…C-17) según DD-01.

---

## FASE 0 — Cimientos

### [C-01] `foundation-setup` — SPRINT
- **Estado**: `[x]` archivado (2026-11-05) — 32/32 tasks
- **Scope**: Scaffolding del repositorio backend/frontend (FastAPI + React/Vite) + infraestructura base
  - Estructura: `backend/` (FastAPI) + `frontend/` (React + TS + Vite)
  - `docker-compose.yml`: PostgreSQL 16 + Redis 7 para desarrollo
  - SQLAlchemy 2.0 + Alembic inicializado en `backend/` con schema vacío + migración baseline
  - Validación de config al boot: la app **falla al arrancar** si falta una env requerida
  - `GET /health` y `GET /ready` sin datos de negocio
  - OpenTelemetry + Sentry skeleton (traza con `tenant_id` en el contexto)
  - `.env.example` documentando las 24 variables de `08_arquitectura_propuesta.md`
  - CI (GitHub Actions): lint → typecheck → unit → build, jobs paralelos backend/frontend
- **Dependencias**: ninguna
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/02_descripcion_general.md` §Stack tecnológico
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios, §Variables de entorno
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-04 (stack), §DD-05 (nube)

---

## FASE 1 — Identidad y Tenancy

### [C-02] `core-models-tenancy` — SPRINT
- **Estado**: `[x]` archivado (2026-11-05) — 22/22 tasks
- **Scope**: Modelos base, aislamiento multi-tenant y catálogos seed
  - Modelos: `tenant`, `user`, `membership`, `role` (enum), `specialty` (global), `price_concept` (tenant-scoped), `currency` (global)
  - `tenant_id NOT NULL` en toda tabla de negocio + **Row Level Security** activada con `FORCE ROW LEVEL SECURITY`
  - Contexto de tenant por transacción con `SELECT set_config('app.current_tenant', :tenant_id, true)`
    (parameterizado: `SET LOCAL` no acepta binds) — el `TenantGuard` nunca toma `tenant_id` del body (RN-TEN-03)
  - Rol de aplicación `odontologia_app` (`NOLOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`); políticas con
    `NULLIF(current_setting('app.current_tenant', true), '')::uuid`
  - Migración `002_core_tenancy` (rollback verificado) + baseline `c01_baseline`
  - Seed: 9 roles de `03_actores_y_roles.md`, `ARS`/`USD`, **9 specialties**, **80 `price_concept`**
    (`UNIQUE NULLS NOT DISTINCT (tenant_id, codigo)`; seed previo a habilitar RLS)
  - **RN-TEN-04 parcial**: índice único parcial `uq_membership_owner_activo`
    (`tenant_id WHERE rol = 'owner' AND activo`) garantiza nunca 2 owners activos; el caso
    "cero owners" (transferencia atómica) se cierra en C-04
  - **Tests: aislamiento cross-tenant (gate obligatorio RN-TEN-02)** con `SET ROLE odontologia_app`
    (el superusuario de tests ignora RLS) + **prueba de mutación** que desactiva una política y
    demuestra que el test falla
- **Dependencias**: C-01
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Tenancy, §Catálogos, §Estrategia de aislamiento multi-tenant
  - `knowledge-base/03_actores_y_roles.md` §Detalle de roles base
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Tenancy
  - `knowledge-base/08_arquitectura_propuesta.md` §Aislamiento (defense in depth)

### [C-03] `auth-sessions` — SPRINT
- **Estado**: `[x]` archivado (2026-11-10) — 54/54 tasks; spec en `openspec/specs/platform-auth/`, documento en `docs/auth.md`
- **Scope**: Autenticación completa con sesión y MFA
  - `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
  - `GET /forgot-password`, `POST /reset-password` (token opaco de un solo uso, 30 min)
  - Password con **Argon2id**; cookie `httpOnly` + `Secure` + `SameSite=Lax` (RN-AU-02)
  - Refresh rotativo con **detección de reuse → revoca la familia** (RN-AU-03)
  - Lockout progresivo tras 5 intentos + registro en `audit_log` (RN-AU-05)
  - **MFA (TOTP) obligatorio** para `owner` y `billing` (RN-AU-04)
  - Cambio de tenant activo **con re-emisión de sesión** (RN-AU-07)
  - Migración `003_auth` (sessions, refresh_tokens, mfa_secrets)
  - Tests: login ok, password mal, lockout, refresh rotation + reuse detection, MFA enforcement
- **Dependencias**: C-02
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Autenticación
  - `knowledge-base/03_actores_y_roles.md` §Rutas públicas
  - `knowledge-base/08_arquitectura_propuesta.md` §Seguridad §Autenticación
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-10 (sesión httpOnly)

### [C-04] `rbac-permissions`
- **Estado**: `[x]` archivado (2026-11-11) — 49/49 tasks; spec en `openspec/specs/platform-rbac/` y
  `platform-team/`, documento en `docs/rbac.md`
- **Scope**: Autorización por roles y gestión de equipo
  - `require_permission` + matriz de 57 permisos centralizada (03 actores)
  - `SessionOut.permissions[]` derivado del rol; la UI decide con `hasPermission`, nunca con `roles`
  - Fronteras duras codificadas: recepción NO lee historia clínica; SuperAdmin no lee clínica; lab no ve HC (RN-CMP-04)
  - `GET/POST/PATCH/DELETE /team/members` + transferencia de ownership atómica (nunca 0 owners, RN-TEN-04)
  - `membership` con `professional_id` (rol ↔ profesional): el mismo user en N tenants con roles distintos (RN-TEN-05)
  - `membership_event` (auditoría) bajo RLS
  - Migración `004_rbac`
  - Tests: cada rol ve exactamente lo de su matriz; intentos de escalada fallan
  - **Recorte registrado (PQ-08)**: sin invitaciones por email. El alta de miembro la hace un rol con
    `team.invite`; el proveedor de email llega con C-18.
- **Dependencias**: C-03
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §RBAC — Matriz de permisos, §Restricciones horizontales
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Tenancy, §Dominio: Compliance (RN-CMP-04)
  - `knowledge-base/06_funcionalidades.md` §US-005
  - `knowledge-base/08_arquitectura_propuesta.md` §Autorización

### [C-05] `clinic-setup` — SPRINT
- **Estado**: `[x]` archivado (2026-11-11) — 45/45 tasks; spec en `openspec/specs/clinic/setup/`,
  documento en `docs/clinic.md`
- **Scope**: Configuración operativa de la clínica
  - Modelos: `chair`, `professional`, `availability_rule` (RLS `FORCE` + `tenant_id NOT NULL`)
  - `GET/POST/PATCH /clinic/chairs` + `DELETE` = baja lógica (`activo = false`)
  - `GET/POST/PATCH /clinic/professionals` (la baja es `PATCH activo = false`; no hay `professional.delete`)
  - `GET /clinic/specialties`: catálogo global + propio, fuente del alta de profesional
  - `GET/POST/PATCH /clinic/availability` con `slot_min`, `buffer_previo_min`, `buffer_posterior_min` y validación de solape
  - Migración `005_clinic_setup`
  - Tests: CRUD, unicidad `(tenant_id, nombre)` y `(tenant_id, matricula)`, buffers persisten, cross-tenant con mutación de RLS
  - **Fuera de alcance (registrado)**: `GET /chairs/{id}/utilization` (pertenece a C-07); RN-AG-06 se evalúa por turno en C-07; `tipo_practica` queda como `varchar(40)` hasta el catálogo de facturación.
- **Dependencias**: C-03
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Agenda (chair, professional, availability_rule)
  - `knowledge-base/06_funcionalidades.md` §US-010, §US-011
  - `knowledge-base/05_reglas_de_negocio.md` §RN-AG-03, §RN-AG-06

### [C-06] `patients` — SPRINT
- **Estado**: `[x]` archivado 2026-11-12 — 37/37 tasks (`docs/patients.md`, `openspec/specs/clinic/patients/`)
- **Scope**: Ficha de pacientes y número de historia clínica
  - Modelos `patient` + `patient_counter` (contador por tenant, solo avanza)
  - **HCE secuencial y no reciclable** (RN-CLI-01): upsert atómico dentro de la transacción del alta;
    nunca `MAX + 1`; sin huecos si el alta falla; crece de 6 a 7 dígitos sin migración
  - `GET/POST /patients`, `GET/PATCH /patients/{id}` (los 4 endpoints; **no** hay `DELETE`)
  - Dedupe **duro** por DNI con índice único parcial (incluye pacientes dados de baja; `confirmar_duplicado`
    no lo vence) y **blando** por nombre/teléfono normalizados, solo activos, máximo 5 candidatos
  - Búsqueda insensible a mayúsculas y acentos sobre columnas normalizadas + GIN trigram, con
    `%`/`_`/`\` escapados y `q` de hasta 60 caracteres
  - **Frontera dura**: recepción NO ve ni escribe historia clínica (RN-CMP-04). `alergias` y
    `alerta_clinica` existen en la tabla pero **no se exponen** hasta C-09 (PQ-17)
  - Matriz RBAC: fila `patient` (owner `CRUD`; clinical_admin/front_desk `CRU`; profesional/asistente/
    facturación `R`; resto —). Catálogo **19 recursos / 61 permisos**
  - Migración `006_patients` (RLS `FORCE` en ambas tablas + `pg_trgm`)
  - Pantalla `/pacientes` (buscador, tabla, alta/edición, diálogo de posible duplicado)
  - Tests: 174 nuevos; pipeline 621 back / 96 unit front / 19 e2e; gate RLS con mutación
  - **Fuera de alcance (registrado)**: `GET /patients/{id}/timeline` y la captura clínica de
    `alergias`/`alerta_clinica` son C-09; `patient.delete` sin endpoint hasta C-13; portal del paciente,
    `obra_social_id` con FK y auditoría de lecturas, post-deadline. Ver `docs/patients.md` §12.
- **Dependencias**: C-03 (RBAC de C-04 para los permisos)
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Clínica (patient)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CLI-01, §RN-CMP-04
  - `knowledge-base/06_funcionalidades.md` §US-030
  - `knowledge-base/03_actores_y_roles.md` §RBAC

### [C-16] `fiscal-onboarding`
- **Estado**: `[ ]` pendiente
- **Scope**: Identidad fiscal del tenant y certificados (paralelizable con el dominio clínico)
  - Modelos: `fiscal_profile`, `fiscal_certificate`, `arca_token_cache`
  - `POST /onboarding/fiscal`, `POST /onboarding/certificate`, `POST /fiscal/verify-token`
  - Parser X.509: `subject_cn`, `serial_number`, `fecha_vencimiento`; **rechaza si el CUIT del cert ≠ tenant**
  - Cifrado del `certificado_pem`, `clave_pem` y `access_token` en reposo (KMS, clave por tenant)
  - **`clave_pem` nunca en logs** — test automatizado (RN-CMP-08)
  - Cliente WSAA real con cache Redis + lock por tenant (RN-ARCA-04)
  - Alertas de vencimiento 30/15/7 días (RN-ARCA-10)
  - Migración `007_fiscal`
  - Tests: cert con CUIT ajeno → rechazo; cert vencido → no emite; token cacheado; log sanitizado
- **Dependencias**: C-03
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/11_facturacion_arca.md` §2 fiscal_certificate, §3 arca_token_cache
  - `knowledge-base/04_modelo_de_datos.md` §Configuración fiscal
  - `knowledge-base/05_reglas_de_negocio.md` §RN-ARCA-04, §RN-ARCA-09, §RN-ARCA-10, §RN-CMP-01
  - `knowledge-base/07_flujos_principales.md` §Flujo 1

### [C-18] `comms-infra`
- **Estado**: `[ ]` pendiente
- **Scope**: Infraestructura de comunicación multicanal (outbox)
  - **Outbox publisher** + worker Celery (Redis) operativo
  - Modelos: `comms_thread`, `comms_message`, `comms_template`, `webhook_event`
  - Estrategia WhatsApp (Cloud API oficial) + estrategia email (provider a definir, PQ-08)
  - `POST /webhooks/whatsapp` con **verificación `X-Hub-Signature-256` obligatoria** (RN-COM-04)
  - **Deduplicación por `(proveedor, evento_id)`** (RN-COM-03)
  - Plantillas versionadas + `RN-COM-01` (los mensajes van por cola, no en el request)
  - Migración `008_comms`
  - Tests: firma inválida rechazada, webhook duplicado no reprocesa, fallo de canal no revierte negocio
- **Dependencias**: C-03
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Comunicación
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Comunicación
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones (Outbox, Strategy)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-11 (WhatsApp oficial)
  - `knowledge-base/10_preguntas_abiertas.md` §PQ-08, §PQ-11

---

## FASE 2 — Pacientes y Agenda

### [C-07] `agenda-booking` — SPRINT (núcleo META: `agendar-turno-sin-solapamiento`)

> El entregable acotado del deadline (y del TP) es el change `agendar-turno-sin-solapamiento`
> (una funcionalidad: crear turno evitando solapamientos por profesional y sillón, con la
> justificación en su proposal.md). Reprogramar, cancelar, lista de espera y disponibilidad
> completa quedan post-deadline si no alcanza el tiempo.
- **Estado**: `[x]` **entregado parcial** — archivado el 2026-11-12 como
  `agendar-turno-sin-solapamiento` (solo el alta con anti-solapamiento: `POST /api/v1/appointments`
  + pantalla `/turnos/nuevo`). El resto del scope de C-07 (consulta de disponibilidad, reprogramar,
  cancelar, check-in, lista de espera, auto-`no_asistio`) queda como C-07b post-deadline.
- **Scope**: Turnos con doble recurso (profesional + sillón)
  - Modelo `appointment` + `waiting_list_entry`
  - **Restricción `EXCLUDE USING gist`** sobre `chair_id` y `professional_id` (RN-AG-02 — la garantía dura, no validación de app)
  - `GET /availability?professionalId&from&to&chairId` con exclusión de solapes y respeto de buffers
  - `POST/PATCH /appointments`, `reschedule`, `cancel` (con regla de 12h, RN-AG-05), `checkin`, `complete`
  - Auto-`no_asistio` por job a las 4h de gracia (RN-AG-04)
  - Optimistic locking `appointment.version` (defensa secundaria)
  - RN-AG-10: paciente sin turnos solapados
  - Migración `009_agenda` (+ extensión btree_gist)
  - Tests: double-booking bajo concurrencia rechazado por la BD, buffers ocupan tiempo real, waiting list por prioridad, cross-tenant
- **Dependencias**: C-05, C-06
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Agenda (appointment, waiting_list_entry)
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Agenda
  - `knowledge-base/07_flujos_principales.md` §Flujo 2, §Flujo 3
  - `knowledge-base/06_funcionalidades.md` §US-012 a §US-015

### [C-08] `agenda-views`
- **Estado**: `[ ]` pendiente
- **Scope**: Vistas de agenda por sillón y día
  - Grilla columnas = sillones, filas = hora (US-013)
  - Resaltado de huecos aprovechables y sobrecupos
  - Filtros por profesional y estado; responsive tablet para consultorio
  - Consumo de `GET /availability` y `/appointments` de C-07
- **Dependencias**: C-07
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-013
  - `knowledge-base/07_flujos_principales.md` §Flujo 2
  - `knowledge-base/02_descripcion_general.md` §API REST (recursos Agenda/Disponibilidad)

### [C-09] `clinical-records`
- **Estado**: `[ ]` pendiente
- **Scope**: Historia clínica append-only con cifrado
  - Modelo `clinical_record` + **trigger de BD `BEFORE UPDATE OR DELETE → reject`** (RN-CMP-02)
  - Cifrado de `contenido` en reposo con clave por tenant + `key_version` (RN-CMP-01)
  - `GET/POST /patients/:id/records`; autoguardado durante la atención
  - Autoría real (RN-CLI-07): profesional solo escribe turnos propios
  - `audit_log` básico para READ/CREATE sobre HC (se completa en C-13)
  - Migración `010_clinical_records`
  - Tests: UPDATE y DELETE fallan a nivel BD; corrección vía `supersedes_id`; recepción recibe 403; cifrado verificable
- **Dependencias**: C-06
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Clínica (clinical_record)
  - `knowledge-base/12_historia_clinical_y_compliance.md` §Inmutabilidad como principio de diseño
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CMP-01, §RN-CMP-02, §RN-CLI-07
  - `knowledge-base/06_funcionalidades.md` §US-031

### [C-10] `odontogram-periodontogram`
- **Estado**: `[ ]` pendiente
- **Scope**: Odontograma FDI y periodontograma, ambos append-only
  - Modelos `chart_entry`, `chart_periodontal` con `supersedes_id` y trigger de inmutabilidad
  - Validación estricta FDI `11`–`48` / `51`–`85` (RN-CLI-02)
  - `GET /patients/:id/chart`, `POST /patients/:id/chart/entries`
  - Estado vigente de una pieza = entrada no-superseded más reciente (RN-CLI-03)
  - Heurística de alerta clínica (profundidad > 5mm, sangrado > 30%) — **explícitamente NO diagnóstico** (RN-CLI-04)
  - Migración `011_odontogram`
  - Tests: FDI inválido rechazado, supersedes correcto, alerta se dispara en umbral, append-only
- **Dependencias**: C-09
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §chart_entry, §chart_periodontal
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CLI-02 a §RN-CLI-04
  - `knowledge-base/06_funcionalidades.md` §US-032, §US-033
  - `knowledge-base/03_actores_y_roles.md` §Restricciones horizontales (higienista no finaliza)

---

## FASE 3 — Clínica Avanzada y Compliance

### [C-11] `consents`
- **Estado**: `[ ]` pendiente
- **Scope**: Consentimiento informado versionado con firma
  - Modelos `consent_template`, `consent` con `template_version` **congelado al firmar** (RN-CMP-05)
  - `GET /consents`, `POST /consents/:templateId/sign`, `GET /consents/:id/evidence`
  - Firma con evidencia: timestamp, IP, user agent, **hash del PDF**
  - PDF inmutable en S3 (bucket con versionado)
  - Ruta pública `/portal/consentimientos/:token` (token firmable de un solo uso)
  - Seed de **estructuras** de plantilla (el contenido legal requiere revisión — PQ-04)
  - Migración `012_consents`
  - Tests: firma congela versión, cambio de plantilla no altera firmados, hash verificable
- **Dependencias**: C-06, C-09
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/12_historia_clinical_y_compliance.md` §Consentimiento informado
  - `knowledge-base/04_modelo_de_datos.md` §Compliance (consent, consent_template)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CMP-05
  - `knowledge-base/10_preguntas_abiertas.md` §PQ-04, §SU-07

### [C-12] `treatment-plans`
- **Estado**: `[ ]` pendiente
- **Scope**: Planes de tratamiento y procedimientos por pieza
  - Modelos `treatment_plan`, `tooth_procedure` con `professional_id` (necesario para liquidar)
  - Post del plan a ítems facturables (los consume C-14/C-15)
  - **Bloqueo duro**: procedimiento no pasa a `realizado` sin consentimiento obligatorio vigente (RN-CLI-06)
  - **Bloqueo**: no se marca `obturado` sin odontograma compatible (RN-CLI-05)
  - Migración `013_treatment_plans`
  - Tests: bloqueo por consentimiento, bloqueo por odontograma, cross-tenant
- **Dependencias**: C-10, C-11
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §treatment_plan / tooth_procedure
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CLI-05, §RN-CLI-06
  - `knowledge-base/06_funcionalidades.md` §US-034, §US-035

### [C-13] `audit-and-aaip`
- **Estado**: `[ ]` pendiente
- **Scope**: Auditoría append-only, solicitudes AAIP y copia autenticada
  - `audit_log` **append-only por trigger**; ni el owner puede modificarlo (RN-CMP-03)
  - Registro de READ/CREATE/UPDATE/EXPORT/SIGN + `justificacion` para soporte
  - Endpoints de auditoría filtrables (US-043)
  - `access_request` (Ley 25.326) con verificación de identidad y **plazo parametrizado** (no hardcodeado — PQ-03)
  - Copia autenticada de HC: job → PDF con sello + hash → S3 inmutable (US-041, plazo en PQ-02)
  - Exportación asíncrona con audit (RN-CMP-07)
  - Migración `014_audit_aaip`
  - Tests: UPDATE/DELETE de audit_log fallan, export genera audit, identidad verificada antes de entregar
- **Dependencias**: C-09, C-10
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/12_historia_clinical_y_compliance.md` §Auditoría, §Copia autenticada, §Solicitudes de acceso
  - `knowledge-base/04_modelo_de_datos.md` §audit_log, §access_request
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CMP-03, §RN-CMP-06, §RN-CMP-07
  - `knowledge-base/07_flujos_principales.md` §Flujo 5

---

## FASE 4 — Caja y Facturación

### [C-14] `cash-settlements`
- **Estado**: `[ ]` pendiente
- **Scope**: Caja diaria y liquidación a profesionales
  - Modelos `cash_session`, `cash_movement`, `settlement`, `payout`
  - `POST /cash-sessions`, `/movements`, `/close`, `GET /reconciliation`
  - `unique(tenant_id) where estado='abierta'` (RN-CJ-01)
  - Cierre calcula `diferencia` **no editable**; ≠ 0 exige nota (RN-CJ-02)
  - `settlement` con `porcentaje_aplicado` **congelado** (RN-CJ-04)
  - Detección de "facturado sin caja" en conciliación (RN-CJ-06)
  - Migración `015_cash`
  - Tests: doble sesión abierta rechazada, diferencia no editable, porcentaje no se recalcula, aislamiento
- **Dependencias**: C-07, C-12
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Caja
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Caja y Liquidaciones
  - `knowledge-base/06_funcionalidades.md` §US-050 a §US-053

### [C-15] `invoicing-core`
- **Estado**: `[ ]` pendiente
- **Scope**: Comprobantes internos, cálculo de impuestos e idempotencia
  - Modelos `invoice`, `invoice_item`, `arca_response`, `invoice_rejection`
  - Máquina de estados `BORRADOR → PENDIENTE → EMITIDO / RECHAZADO / ANULADO` (RN-ARCA-01)
  - Cálculo decimal exacto con alícuota por ítem + `CHECK (total = subtotal + impuestos)` (RN-EX-08)
  - `idempotency_key` + `unique(tenant_id, idempotency_key)` (RN-ARCA-02)
  - `unique(tenant_id, tipo, serie, numero) where numero is not null` (RN-ARCA-07)
  - `POST /invoices`, `GET /invoices/:id`, anulación con motivo (RN-EX-07)
  - **Emisión asíncrona**: la UI responde en <400ms, el comprobante queda `PENDIENTE` (RN-ARCA-03)
  - Migración `016_invoicing`
  - Tests: idempotencia (2 emisiones → 1 comprobante), CHECK de totales, estado inmutable post-EMITIDO
- **Dependencias**: C-14
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/11_facturacion_arca.md` §Modelo de datos, §Cálculo de impuestos, §Idempotencia
  - `knowledge-base/04_modelo_de_datos.md` §Facturación
  - `knowledge-base/05_reglas_de_negocio.md` §RN-ARCA-01 a §RN-ARCA-03, §RN-EX-08
  - `knowledge-base/07_flujos_principales.md` §Flujo 4

### [C-17] `arca-emission`
- **Estado**: `[ ]` pendiente
- **Scope**: Emisión real ante ARCA (la pieza de mayor riesgo del proyecto)
  - Cliente **WSAA** con cache Redis + lock + cifrado del token
  - Cliente **WSFE**: serializar request, firmar con **X.509 del tenant**, parsear response
  - Worker `arca-emit` + `arca-retry` con Outbox y circuit breaker
  - **Traductor de errores ARCA → `invoice_rejection.sugerencia`** (`corregir`/`anular`/`esperar`/`soporte`)
  - Rechazo determinístico **no se reintenta** (RN-ARCA-06); transitorio reintenta con misma key
  - Token expirado → re-obtener + reintentar una vez (misma key)
  - PDF del comprobante (CAE, barcode, QR) vía ReportLab/WeasyPrint
  - Guarda `request_hash` + `respuesta_xml` completo (RN-ARCA-08)
  - Tests contra **homologación** de ARCA (nunca producción): idempotencia, rechazo, transitorio, cert vencido
- **Dependencias**: C-15, C-16
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/11_facturacion_arca.md` §4 Emisión, §5 Registro forense, §Manejo de rechazos, §Circuit breaker
  - `knowledge-base/05_reglas_de_negocio.md` §RN-ARCA-04 a §RN-ARCA-10
  - `knowledge-base/07_flujos_principales.md` §Flujo 4
  - `knowledge-base/08_arquitectura_propuesta.md` §Estrategia de despliegue (staging = homologación)

---

## FASE 5 — Comunicación

### [C-19] `comms-flows`
- **Estado**: `[ ]` pendiente
- **Scope**: Flujos de comunicación del turno
  - Confirmación automática con link de un solo uso (US-070)
  - Recordatorios 24h/2h — **solo si el turno sigue pendiente/confirmado** (RN-COM-07)
  - Oferta de lista de espera (US-024) y aviso "documento disponible" (US-072)
  - Opt-in explícito antes del primer envío (RN-COM-06) + baja de no-esenciales (RN-COM-05)
  - Templates seed: confirmación, recordatorio 24h, recordatorio 2h, cancelación, reagendado, lista de espera
  - Tests: no se envía recordatorio de turno cancelado, opt-in requerido, dedupe por webhook
- **Dependencias**: C-18, C-07
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-070 a §US-073
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Comunicación
  - `knowledge-base/04_modelo_de_datos.md` §Comunicación

---

## FASE 6 — Portal del Paciente

### [C-20] `patient-portal`
- **Estado**: `[ ]` pendiente
- **Scope**: Portal del paciente y reserva self-service
  - Autenticación por **OTP a teléfono verificado** (RN-AU-06); email no alcanza
  - `GET /paciente/reservar`: disponibilidad real, sin datos de otros pacientes
  - Links de un solo uso: confirmar/cancelar turno, firmar consentimiento
  - Portal: próximos turnos, historial, documentos entregados, actualización de contacto
  - Baja de comunicaciones no esenciales (RN-COM-05)
  - Rate limiting estricto en reserva pública y OTP
  - Tests: OTP correcto/incorrecto/lockout, paciente no accede a datos ajenos, link expira
- **Dependencias**: C-07, C-12, C-18
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-020 a §US-024
  - `knowledge-base/05_reglas_de_negocio.md` §RN-AU-06, §RN-CMP-04, §RN-COM-05
  - `knowledge-base/03_actores_y_roles.md` §Rutas públicas
  - `knowledge-base/07_flujos_principales.md` §Flujo 5

---

## FASE 7 — Migración y Reportes

### [C-21] `data-migration`
- **Estado**: `[ ]` pendiente
- **Scope**: Importación desde el sistema anterior del cliente
  - `POST /migrations/upload` (CSV/XLSX) + job de preview con progreso
  - Mapeo de columnas configurable
  - **Reporte de duplicados por DNI + nombre**; nada se importa sin confirmación (RN-EX-02)
  - `POST /migrations/:id/commit` idempotente por lote
  - Import de turnos históricos sin bloquear agenda futura ni afectar liquidaciones (RN-CJ-04)
  - Reasignación de `numero_historia_clinica` en clash **sin reciclar** (RN-CLI-01)
  - Tests: archivo con duplicados, import interrumpido no duplica, HCE preservado
- **Dependencias**: C-06, C-07
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/07_flujos_principales.md` §Flujo 6
  - `knowledge-base/06_funcionalidades.md` §US-080 a §US-082
  - `knowledge-base/05_reglas_de_negocio.md` §RN-CLI-01, §RN-CJ-04, §RN-EX-02

### [C-22] `reports`
- **Estado**: `[ ]` pendiente
- **Scope**: Reportes de gestión (post-MVP)
  - Rentabilidad del mes: facturado, cobrado, pendiente, por profesional (US-090)
  - Utilización del **sillón** — métrica que ningún competidor expone (US-091)
  - Utilización del profesional + tasa de no-show (US-092)
  - `GET /reports/revenue`, `/professional-utilization`, `/chair-utilization`, `/no-shows`
  - Exportable a XLSX; visible solo para owner/billing
  - Tests: agregados correctos contra datos seed, RBAC de solo lectura financiera
- **Dependencias**: C-07, C-14, C-15
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-090 a §US-093
  - `knowledge-base/01_vision_y_objetivos.md` §Métricas de éxito
  - `knowledge-base/03_actores_y_roles.md` §RBAC

---

## FASE 8 — Consola Interna

### [C-23] `superadmin-console`
- **Estado**: `[ ]` pendiente
- **Scope**: Consola de operación del SaaS (nosotros)
  - Gestión de tenants: alta, suspensión, reactivación (RN-TEN-06)
  - Health de integraciones: estado de certificados, tokens WSAA, colas, tasa de rechazo ARCA
  - Acceso de soporte **auditado y con justificación**; **sin lectura de historia clínica** (RN-EX-06)
  - Sesión de 4h + MFA para SuperAdmin (RN-AU-08)
  - Tests: SuperAdmin no puede leer HC de ningún tenant, acceso de soporte genera audit_log
- **Dependencias**: C-03, C-17
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §SuperAdmin, §Audit de accesos sensibles
  - `knowledge-base/05_reglas_de_negocio.md` §RN-TEN-06, §RN-AU-08, §RN-EX-06
  - `knowledge-base/12_historia_clinical_y_compliance.md` §RBAC de datos clínicos
  - `knowledge-base/11_facturacion_arca.md` §Checklist de implementación

---

## Resumen

| Métrica | Valor |
|---------|-------|
| **Total de changes** | 23 |
| **Fases** | 9 (FASE 0 a FASE 8) |
| **Sprint 1 dev — deadline 2026-10-23** | 6 changes (C-01…C-07, ruta del turno, ~11 días); META entregable: `agendar-turno-sin-solapamiento` |
| **Backlog post-deadline** | 16 changes (C-08…C-23) |
| **Changes CRITICO** | 8 (C-02, C-03, C-09, C-10, C-13, C-15, C-16, C-17) |
| **Changes ALTO** | 6 (C-04, C-07, C-11, C-14, C-18, C-23) |
| **Changes MEDIO** | 7 (C-01, C-05, C-06, C-12, C-19, C-20, C-21) |
| **Changes BAJO** | 2 (C-08, C-22) |
| **Requisitos MVP (los 10 imprescindibles)** | Todos cubiertos en FASE 1–7 |
| **Post-deadline** | C-08…C-23 (facturación priorizada tras el sprint) |
| **Archivados al 2026-11-12** | 7 (C-01…C-06 + `agendar-turno-sin-solapamiento`) — criterios 1, 2, 3 y 4 cubiertos; el 5 en las 4 pantallas sobre el backend real |

### Sprint completado — próximo paso

El sprint de la "ruta del turno" está **cerrado**: los 7 changes cuentan con los 4 gates
(propuesto, aplicado, verificado, archivado). Lo que sigue es backlog post-deadline y **no**
bloquea la entrega del TPI. El resto del scope de C-07 (consulta de disponibilidad, reprogramar,
cancelar, check-in, lista de espera, auto-`no_asistio`) se propone como change nuevo —con su
número asignado al momento de proponerlo— cuando se retome la agenda; después siguen C-08 y C-09.

### Advertencia de secuencia (1 dev)

`C-01` → `C-02` → `C-03` → `C-04` → `C-05` → `C-06` → `agendar-turno-sin-solapamiento` están
**archivados** y fueron estrictamente secuenciales: cada uno cerró con suite verde + test de
aislamiento cross-tenant + gate de escenarios. Con 1 dev no hay paralelismo: el próximo change del
backlog arranca solo cuando el anterior está archivado. El sprint del deadline (y del TPI) está
completo; si algo se recorta por tiempo, se recorta funcionalidad (lista de espera / recordatorios)
antes que tocar RLS (C-02) o auditoría base (C-03).

### Bloqueantes de negocio antes de ejecutar (no técnicos)

| ID | Pregunta | Afecta a |
|----|----------|---------|
| PQ-01 | ~~Tamaño de equipo y deadline~~ **RESUELTO** (1 dev, deadline 2026-10-23) | — |
| PQ-02 | Plazo legal de copia autenticada | C-13 |
| PQ-03 | Plazo legal de respuesta AAIP | C-13 |
| PQ-04 | Textos legales de consentimiento | C-11 |
| PQ-05 | Estado real de ARCA / certificados del cliente | C-16, C-17 |
| PQ-08 | Proveedor de email | C-18 |
| PQ-11 | Pricing de WhatsApp API | C-18, C-19 |
