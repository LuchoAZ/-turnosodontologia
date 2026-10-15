# Gestión Odontológica PyME

SaaS multi-tenant de gestión para clínicas odontológicas PyME de Argentina (3–10 sillones): agenda por
profesional y por sillón/box, historia clínica legalmente defendible, caja y facturación electrónica ante
ARCA, con trazabilidad auditable de extremo a extremo.

> Repositorio raíz de la materia **Metodología de la Investigación / Trabajo Práctico**. Desarrollado por
> **1 desarrollador full-stack** (SU-01) con **deadline 2026-10-23** (SU-02).

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
| Skills del stack (22) y convenciones de agentes | ✅ Completado — vendorizadas en `.agents/skills/` (`AGENTS.md`, `.atl/skill-registry.md`) |
| CI (GitHub Actions): lint → typecheck → unit → integration → e2e → build | ✅ Verde en `main` (5/5 jobs) |
| Change `c-01-foundation-setup` (monorepo, tests con Postgres/Redis reales, CI) | ✅ Implementado — 31/32 tasks (falta cerrar branch protection en GitHub) |
| **Change `agendar-turno-sin-solapamiento` (ENTREGABLE TP)** | 🔜 **Pendiente — deadline 2026-10-23** |

**Entregable del TP (META)**: el change `agendar-turno-sin-solapamiento` — crear un turno evitando
solapamientos por profesional y por sillón/box, con reglas de negocio verificables (RN-AG-01/02/03/09/10),
API + formulario mínimo y evidencia de tests de punta a punta.

### Ruta del Sprint 1 dev

```
C-01 foundation-setup  ✅           monorepo + tests con Postgres/Redis reales + CI
  → C-02 core-models-tenancy       modelos SQLAlchemy + RLS + EXCLUDE (anti-solapamiento)
  → C-03 auth-sessions             sesión httpOnly + tenant del token
  → C-05 clinic-setup              profesionales, sillones y reglas de duración
  → C-06 patients                  pacientes
  → ★ agendar-turno-sin-solapamiento   ENTREGABLE — crear turno sin solapamientos
```

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
│   ├── changes/                 # Changes activos (proposal/design/tasks/specs)
│   │   ├── c-01-foundation-setup/
│   │   └── agendar-turno-sin-solapamiento/
│   └── specs/                   # Specs de capacidades (tras archive)
├── .agents/skills/              # Skills vendorizadas (metodología + dominio, 16 skills)
├── .atl/                        # Skill registry (.atl/skill-registry.md)
├── .opencode/skills/            # Skills OPSX (openspec-*)
├── .github/workflows/           # CI (GitHub Actions)
├── docs/                        # Documentación adicional (guía del proyecto, guia-del-proyecto.doc)
├── backend/                     # FastAPI: app/, alembic/, tests/
├── frontend/                    # React + Vite: src/{routes,features,shared,api}
├── docker-compose.yml           # Postgres 16 + Redis 7 + backend + worker + frontend
└── .env.example                 # Variables validadas con pydantic-settings
```

## 5. Modo de uso

### 5.1 Uso actual (documentación y planificación)

```bash
# Ver changes activos y su estado
openspec list
openspec status --change agendar-turno-sin-solapamiento

# Validar un change (propuesta + spec)
openspec validate agendar-turno-sin-solapamiento --type change --strict

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
npm run test:e2e           # e2e (Playwright) del formulario web
```

**CI (GitHub Actions)**: `lint → typecheck → unit → integration → e2e → build` por app; todos los jobs
bloquean el merge. **Gate de merge obligatorio**: todo change que toque una tabla con `tenant_id` debe
pasar el test de aislamiento cross-tenant (RN-TEN-02).

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
| `docs/guia-del-proyecto.doc` | Guía exhaustiva carpeta por carpeta (para video/defensa) |
| `discovery/discovery.md` | Recomendación final (Sección D del TP): 5 competidores para demo, 3 referencias UX, MVP sugerido |

## 8. Licencia y contexto académico

Proyecto desarrollado como trabajo práctico de la materia Metodología de la Investigación. Sin licencia
comercial definida; no distribuir sin autorización.