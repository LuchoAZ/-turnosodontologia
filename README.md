# Gestión Odontológica PyME

SaaS multi-tenant de gestión para clínicas odontológicas PyME de Argentina (3–10 sillones): agenda por
profesional y por sillón/box, historia clínica legalmente defendible, caja y facturación electrónica ante
ARCA, con trazabilidad auditable de extremo a extremo.

> Repositorio raíz de la materia **Metodología de la Investigación / Trabajo Práctico**. Desarrollado por
> **1 desarrollador full-stack** (SU-01). Deadline interno del Sprint 1 dev: **2026-10-23** (SU-02);
> entrega académica del TP: **2026-11-20**.

---

## 1. Qué es el programa

El consultorio y la clínica odontológica argentina resuelven hoy sus turnos con un mosaico que no se
sostiene: una agenda que no habla con la ficha clínica, WhatsApp manual no auditable, obras sociales
liquidadas en planillas y facturación fiscal que muchas clínicas directamente no emiten.

Este sistema cubre la **capa de negocio y compliance específica del odontólogo argentino** que los 20
sistemas relevantes del mercado prometen sin evidencia técnica verificable:

- **Agenda por profesional y por sillón/box** — el sillón como unidad de capacidad bloqueable, con
  anti-solapamiento garantizado por la base de datos (RN-AG-02).
- **Facturación electrónica ARCA end-to-end** — comprobante A/B/C derivado del estado fiscal del cliente,
  token WSAA, certificado X.509 por tenant.
- **Historia clínica defendible** — inmutabilidad y copia autenticada conforme a la Ley 26.529, privacidad
  conforme a la Ley 25.326.
- **Aislamiento multi-tenant por RLS** (PostgreSQL) — cada clínica ve solo sus datos (RN-TEN-02).

El **MVP v0.1** se compone de **10 capacidades imprescindibles**: agenda por sillón, reserva online,
recordatorios por WhatsApp, ficha clínica con odontograma FDI, caja, facturación ARCA, consentimiento
informado, historia clínica inmutable, RBAC/privacidad y migración con dedupe.

## 2. Estado actual del proyecto

| Etapa | Estado |
|---|---|
| Discovery de mercado (20 competidores) | ✅ Completado (`discovery/discovery.md`) |
| Knowledge Base (13 documentos de dominio) | ✅ Completado (`knowledge-base/`) |
| Roadmap — 23 changes, Sprint 1 dev | ✅ Completado (`CHANGES.md`) |
| Skills del stack (17 project-local) + convenciones de agentes | ✅ Completado — vendorizadas en `.agents/skills/` (`AGENTS.md`, `.atl/skill-registry.md`); las 6 skills OPSX viven en `.opencode/skills/` |
| CI (GitHub Actions): lint → typecheck → unit → integration → e2e → build | ✅ Verde en `main` (5/5 jobs); gate `ci (required)` versionado (marcación en GitHub documentada en `docs/foundation.md`) |
| Change `c-01-foundation-setup` (monorepo, tests con Postgres/Redis reales, CI) | ✅ **Archivado** — 32/32 tasks |
| Change `c-02-core-models-tenancy` (modelo base, RLS fail-closed, seed de catálogos) | ✅ **Archivado** — 22/22 tasks, gate RN-TEN-02 con prueba de mutación (`docs/core-tenancy.md`) |
| Change `c-03-auth-sessions` (sesión httpOnly, login, MFA, reset, switch-tenant, guardas + e2e) | ✅ **Archivado 2026-11-10** — 54/54 tasks (`docs/auth.md`, `openspec/specs/platform-auth/`) |
| Change `c-04-rbac-permissions` (matriz de 57 permisos, guardas, equipo, auditoría, RLS) | ✅ **Archivado 2026-11-11** — 49/49 tasks (`docs/rbac.md`, `openspec/specs/platform-rbac/` y `platform-team/`) |
| Change `c-05-clinic-setup` (sillones, profesionales, especialidades, disponibilidad + pantalla) | ✅ **Archivado 2026-11-11** — 45/45 tasks; 444 back / 67 unit front / 15 e2e (`docs/clinic.md`, `openspec/specs/clinic/setup/`) |
| Change `c-06-patients` (fichas de pacientes, HCE numerada, dedupe, búsqueda + pantalla) | ✅ **Archivado 2026-11-12** — 37/37 tasks; 621 back / 96 unit front / 19 e2e (`docs/patients.md`, `openspec/specs/clinic/patients/`) |
| Skill propia `spec-scenario-review` + MCP `context7` | ✅ Integrados con evidencia (`docs/skills-mcp/`) |
| Change `agendar-turno-sin-solapamiento` (alta de turno sin solapamientos + pantalla `/turnos/nuevo`) | ✅ **Archivado 2026-11-12** — 13/13 tasks; 695 back / 128 unit front / 24 e2e (`docs/appointments.md`, `openspec/specs/agenda/appointments/`) |
| **Criterio 4 del TP (agenda y turnos)** | ✅ Cubierto por `agendar-turno-sin-solapamiento`: disponibilidad derivada, reserva con anti-solapamiento (`EXCLUDE USING gist` + RN-AG-10) y flujo front↔back verificado en e2e |

**Entregable del TP (META)**: el change `agendar-turno-sin-solapamiento` (archivado) — crear un turno
evitando solapamientos por profesional y por sillón/box, con reglas de negocio verificables
(RN-AG-01/02/03/09/10), API + formulario `/turnos/nuevo` y evidencia de tests de punta a punta.

### Ruta del Sprint 1 dev

```
C-01 foundation-setup     ✅ archivado   monorepo + tests con Postgres/Redis reales + CI
  → C-02 core-models-tenancy  ✅ archivado   modelos SQLAlchemy + RLS fail-closed + seed
  → C-03 auth-sessions        ✅ archivado   sesión httpOnly + MFA + tenant del token
  → C-04 rbac-permissions     ✅ archivado   matriz de permisos + equipo + auditoría
  → C-05 clinic-setup         ✅ archivado   sillones + profesionales + disponibilidad + pantalla
  → C-06 patients             ✅ archivado   fichas + HCE numerada + dedupe + pantalla
  → ★ agendar-turno-sin-solapamiento   ✅ archivado   alta de turno sin solapamientos + /turnos/nuevo
```

C-04 no figuraba en el Sprint 1 original: se adelantó porque la rúbrica del TP exige el criterio de
**autenticación y permisos** con acceso autorizado y rechazo de accesos inválidos, y porque la agenda
necesita la frontera de permisos ya cerrada. C-05 y C-06 entregan el criterio 2 (modelos y
persistencia) con las entidades operativas de la clínica —sillones, profesionales, disponibilidad y
fichas de pacientes con historia clínica numerada—, sus migraciones y el gate cross-tenant.

## 3. Stack tecnológico

| Capa | Tecnología | Versión mínima |
|------|-----------|----------------|
| Lenguaje backend | Python | 3.12 (type hints estrictos con mypy, sin `Any` en dominio) |
| Framework backend | FastAPI | latest (async nativo, OpenAPI automático) |
| ORM | SQLAlchemy 2.0 + Alembic | 2.0 (migraciones versionadas) |
| Validación | Pydantic v2 + pydantic-settings | 2.0 — **el contrato front↔back es el OpenAPI de FastAPI (Pydantic v2)** |
| Base de datos | PostgreSQL | 16 (RLS nativo por tenant) |
| Colas / cache | Redis + Celery | 7 / 5 |
| Object storage | S3-compatible | — |
| XML | `lxml` + `xmlschema` (esquemas XSD ARCA) | latest |
| Crypto | `cryptography` | latest (X.509 por tenant) |
| PDF | ReportLab / WeasyPrint | latest |
| Frontend | React + TypeScript + Vite | 18 / 5 / 6 |
| UI | Tailwind CSS + shadcn/ui | 4 / latest |
| Formularios | React Hook Form + Zod | latest (validación solo en el cliente) |
| Auth | JWT (access + refresh rotativo) en cookie httpOnly | — (DD-10 revisada, no JWT en localStorage) |
| Cliente HTTP (back) | httpx | latest |
| Observabilidad | OpenTelemetry (Python SDK) + Sentry | latest (modo degradado) |
| Tests | pytest + Testcontainers + Playwright (back/e2e); Vitest (front) | latest (Postgres real, no mocks de DB) |
| Contenedores | Docker + docker-compose | — |

**Arquitectura**: repositorio con `backend/` (Python) + `frontend/` (React/Vite) y `docker-compose`,
contrato **OpenAPI** entre ambos (el backend FastAPI genera el schema; el frontend deriva los tipos
TypeScript). **Vertical slices** (cada change entrega API + UI de su capacidad), nunca construcción por capas.

## 4. Estructura del repositorio

```
.
├── AGENTS.md / CLAUDE.md        # Instrucciones para agentes (stack, reglas duras, roadmap)
├── CHANGES.md                   # Roadmap de los 23 changes + Sprint 1 dev
├── discovery/                   # Investigación de mercado (evidencia [C]/[A]/[NE])
├── knowledge-base/              # Documentación de dominio (fuente de verdad)
├── openspec/
│   ├── changes/                 # Sin changes activos (sprint cerrado)
│   │   └── archive/             # c-01 … c-06 + agendar-turno-sin-solapamiento archivados
│   └── specs/                   # platform-runtime, platform-tenancy, platform-auth, platform-rbac, platform-team, clinic/setup, clinic/patients, agenda/appointments
├── .agents/skills/              # Skills vendorizadas (metodología + dominio + `spec-scenario-review`)
├── .atl/                        # Skill registry (.atl/skill-registry.md)
├── .opencode/skills/            # Skills OPSX (openspec-*)
├── .github/workflows/           # CI (GitHub Actions)
├── docs/                        # foundation.md, core-tenancy.md, auth.md, rbac.md, clinic.md, patients.md, appointments.md, skills-mcp/, entrega/
├── backend/                     # FastAPI: app/, alembic/, tests/
├── frontend/                    # React + Vite: src/{routes,features,shared,api}
├── docker-compose.yml           # Postgres 16 + Redis 7 + backend + worker + frontend
└── .env.example                 # Variables validadas con pydantic-settings
```

## 5. Modo de uso

### 5.1 Uso actual (documentación y planificación)

```bash
# Ver los changes activos (hoy no hay ninguno: el sprint está archivado)
openspec list

# Ver las capacidades ya especificadas (la fuente de verdad post-archive)
openspec list --specs
openspec show agenda/appointments

# Validar una spec
openspec validate agenda/appointments

# Leer el dominio antes de tocar código
knowledge-base/README.md            # índice de la KB
CHANGES.md                          # roadmap y dependencias
```

### 5.2 Entorno de desarrollo (implementado con C-01)

Requisitos: **Python 3.12**, **Node.js 20+**, **Docker Desktop** (para levantar PostgreSQL 16 y Redis 7 reales).

```bash
# 1) Backend: instalar dependencias (pyproject.toml + uv o venv)
cd backend
pip install -e ".[dev]"        # o: uv sync

# 2) Frontend: instalar dependencias
cd ../frontend
npm install

# 3) Levantar la infraestructura local (Postgres 16 + Redis 7)
docker compose up -d

# 4) Configurar entorno (pydantic-settings valida al boot; falla ante variables faltantes/inválidas)
cp .env.example .env

# 5) Correr backend (FastAPI) + frontend (Vite) en modo desarrollo
cd ../backend; uvicorn app.main:app --reload   # puerto 8000
cd ../frontend; npm run dev                    # puerto 5173

# 6) Verificar salud del servicio
GET http://localhost:8000/health    # liveness
GET http://localhost:8000/ready     # readiness (Postgres + Redis)
```

### 5.3 Tests

```bash
pytest                     # backend: unit + integration (Testcontainers: Postgres 16 + Redis 7 reales)
npm test                   # frontend: unit (Vitest)
npm run test:e2e           # e2e (Playwright) contra backend real (Testcontainers + Alembic + seed)
# Si 5173 está ocupado (p. ej. por Docker Desktop): E2E_WEB_PORT=5180 npm run test:e2e
```

Última corrida completa (2026-11-12, árbol de trabajo sobre `main`): **695 tests backend** (`ruff` limpio,
`mypy app` 79 archivos), **128 unit frontend** (`tsc -b` limpio, `eslint` 0 errores) y **24 e2e Playwright**
en verde. El detalle por capa está en `docs/auth.md` § 13, `docs/rbac.md` § 10, `docs/clinic.md` § 11,
`docs/patients.md` § 11 y `docs/appointments.md` § 7.

**CI (GitHub Actions)**: `lint → typecheck → unit → integration → e2e → build` por app; todos los jobs
bloquean el merge. **Gate de merge obligatorio**: todo change que toque una tabla con `tenant_id` debe
pasar el test de aislamiento cross-tenant (RN-TEN-02).

### 5.4 Skill propia y MCP (context7)

**Skill propia `spec-scenario-review`** (`.agents/skills/spec-scenario-review/SKILL.md`, versionada):
revisa `proposal.md`, `design.md`, `specs/**/spec.md` y `tasks.md` de un change **antes** de
implementarlo. Exige ≥3 escenarios verificables por requisito (esperado, error de negocio, borde),
cruza las reglas RN-XX contra la KB y bloquea si falta el check de tenancy (RN-TEN-02). Emite un
veredicto: `LISTO PARA APLICAR` / `FALTAN ESCENARIOS` / `BLOQUEADO`.

Evidencia de uso real:

- `docs/skills-mcp/evidencias/revision-agendar-turno.md` → `FALTAN ESCENARIOS`, 6 huecos detectados
  antes de escribir código.
- `docs/skills-mcp/evidencias/revision-agendar-turno-post-fix.md` → ciclo completo: los 6 huecos
  corregidos, 2 defectos extra encontrados en la 2.ª pasada y veredicto final `LISTO PARA APLICAR`
  (6 requisitos, 24 escenarios, 24/24 con tarea).
- `docs/skills-mcp/evidencias/revision-agendar-turno-pre-archive.md` → el mismo change ya implementado,
  como **gate pre-archive**: `LISTO PARA ARCHIVAR`, 5 defectos de redacción corregidos antes de
  congelarse en la spec principal (26 escenarios, 26/26 con test).
- `docs/skills-mcp/evidencias/revision-c-02.md` → `LISTO PARA APLICAR`, con el hueco **RN-TEN-04**
  detectado por la skill y cerrado en C-02 (índice parcial + RED verificado).
- `docs/skills-mcp/evidencias/revision-c-04.md` → 1.ª pasada `FALTAN ESCENARIOS`; `…-r2`, `…-r3` y
  `…-r4` documentan el ciclo hasta `LISTO PARA APLICAR` (12 requisitos, 61 escenarios, 49 tareas).
- `docs/skills-mcp/aplicacion.md` → informe de aplicación completo y revisión crítica.

**MCP `context7`** (documentación actualizada del stack). Configuración reproducible, en la
configuración **global** de OpenCode (`~/.config/opencode/opencode.json`):

```json
{
  "mcp": {
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp",
      "enabled": true
    }
  }
}
```

- **Requisitos**: ninguno (servidor remoto). Opcional: `CONTEXT7_API_KEY` gratuita para más rate
  limit; se referencia como `{env:CONTEXT7_API_KEY}` y **nunca** se commitea el valor.
- **Comprobar conexión**: `opencode mcp list` y, en una sesión, pedir `use context7`; deben aparecer
  `context7_resolve-library-id` y `context7_query-docs`. Si el CLI no está en el PATH, alcanza con
  verificar que `mcp.context7.enabled = true` en el JSON y que la sesión liste esas dos tools.
- **Uso**: `resolve-library-id` (nombre → ID) y `query-docs` (docs por ID). La ficha completa, la
  comparación con Playwright MCP y las consultas hechas están en `docs/skills-mcp/investigacion.md`.

## 6. Reglas de implementación (resumen)

Extraídas de `AGENTS.md` — las lee todo agente antes de tocar código:

- **Vertical slices**: cada change entrega API + UI de su capacidad; nunca construir por capas.
- **Strict TDD**: test que falla primero; Postgres/Redis reales (Testcontainers), nunca mocks de DB.
- **Aislamiento multi-tenant**: `tenant_id` siempre del token/sesión, nunca del body; RLS activa en toda
  tabla de negocio; sin test cross-tenant no se mergea.
- **Historia clínica**: append-only con `supersedes_id` (Ley 26.529); nunca `UPDATE`/`DELETE`.
- **ARCA**: nunca síncrono dentro de un request → Outbox + Celery (Redis); el tipo de comprobante se deriva del
  estado fiscal del cliente; X.509 cifrado por tenant, nunca en claro ni en logs.
- **Sin `Any`** en el dominio; el contrato front↔back es el OpenAPI de FastAPI (Pydantic v2).
- **Flujo**: leer KB relevante → identificar el change en `CHANGES.md` → `/opsx:propose` →
  implementar (TDD + gates) → `/opsx:archive`.

## 7. Documentación

| Recurso | Contenido |
|---|---|
| `knowledge-base/01_vision_y_objetivos.md` | Propósito, alcance v0.1, fuera de alcance |
| `knowledge-base/02_descripcion_general.md` | Stack, arquitectura multi-tenant, superficie REST |
| `knowledge-base/04_modelo_de_datos.md` | Entidades, ERD, aislamiento por tenant |
| `knowledge-base/05_reglas_de_negocio.md` | Reglas codificadas (RN-XX, incl. RN-TEN-02) |
| `knowledge-base/11_facturacion_arca.md` | ARCA: WSAA, X.509 por tenant, idempotencia |
| `knowledge-base/12_historia_clinical_y_compliance.md` | Ley 26.529, Ley 25.326 + AAIP |
| `CHANGES.md` | Roadmap completo y dependencias |
| `.atl/skill-registry.md` | Registro de skills (metodología + dominio, vendorizadas en `.agents/skills/`) |
| `docs/foundation.md` | Cómo correr, sondas de salud, variables de entorno y CI/branch protection |
| `docs/core-tenancy.md` | Modelo base, políticas RLS, rol de app, seed y prueba de mutación |
| `docs/auth.md` | Sesión httpOnly, contrato de los 10 endpoints de auth, lockout, MFA, reset, switch-tenant, proxy de Vite y orquestación del e2e (con salidas reales) |
| `docs/rbac.md` | Matriz de 57 permisos, `SessionOut.permissions[]`, guarda `require_permission`, contrato de los 5 endpoints de equipo, transferencia de ownership, auditoría, pantalla de Equipo y gate cross-tenant |
| `docs/clinic.md` | Sillones, profesionales, especialidades y disponibilidad: modelo, 11 endpoints, `ClinicErrorCode`, validaciones, RLS con prueba de mutación, pantalla `/clinica`, demo y e2e |
| `docs/patients.md` | Ficha demográfica del paciente: modelo `patient` + `patient_counter`, 4 endpoints, regla de HCE (sin `MAX+1`, sin huecos, 7 dígitos), dedupe duro por DNI y blando por nombre/teléfono, búsqueda normalizada, frontera clínica (PQ-17), RLS con prueba de mutación, pantalla `/pacientes`, demo y e2e |
| `docs/skills-mcp/investigacion.md` | Ficha de investigación: skill propia + comparación y elección de MCP |
| `docs/skills-mcp/aplicacion.md` | Informe de aplicación, evidencias y revisión crítica |
| `docs/skills-mcp/evidencias/revision-agendar-turno.md` | Revisión `FALTAN ESCENARIOS` del entregable (6 huecos) |
| `docs/skills-mcp/evidencias/revision-agendar-turno-post-fix.md` | Re-revisión y veredicto final `LISTO PARA APLICAR` (24/24 escenarios con tarea) |
| `docs/skills-mcp/evidencias/revision-c-02.md` | Revisión `LISTO PARA APLICAR` de C-02 (RN-TEN-04 cerrado) |
| `docs/skills-mcp/evidencias/revision-c-04*.md` | Ciclo de revisión de C-04: `FALTAN ESCENARIOS` → `r4 LISTO PARA APLICAR` |
| `docs/skills-mcp/evidencias/revision-c-05-pre-apply.md` | Gate de escenarios de C-05 antes de implementar (10 req./44 escenarios) |
| `docs/skills-mcp/evidencias/revision-c-05-pre-archive.md` | Gate de escenarios de C-05 antes de archivar, con cobertura y tenancy |
| `docs/skills-mcp/evidencias/gate-rls-c-05.md` | Prueba de mutación de RLS de C-05 (sin política el gate falla) |
| `docs/skills-mcp/evidencias/revision-c-06-pre-apply.md` | Gate de escenarios de C-06 antes de implementar (11 req./57 escenarios, 17 huecos cerrados) |
| `docs/skills-mcp/evidencias/revision-c-06-pre-archive.md` | Gate pre-archive de C-06: los 57 escenarios mapeados a tests ejecutados (189 back / 35 front), tenancy con mutación |
| `docs/skills-mcp/evidencias/gate-rls-c-06.md` | Prueba de mutación de RLS de C-06 sobre `patient` y `patient_counter` |
| `docs/entrega/guion-video.md` | Guion del video de defensa (9–10 min, con comandos y tomas de respaldo) |
| `docs/entrega/resumen-entrega.txt` | Resumen ejecutivo de la entrega y checklist de evidencias |
| `discovery/discovery.md` | Recomendación final (Sección D del TP): 5 competidores para demo, 3 referencias UX, MVP sugerido |

## 8. Licencia y contexto académico

Proyecto desarrollado como trabajo práctico de la materia Metodología de la Investigación. Sin licencia
comercial definida; no distribuir sin autorización.