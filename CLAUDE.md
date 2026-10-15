# Gestión Odontológica PyME — Instrucciones para Agentes

> Este archivo (y su copia `CLAUDE.md`) es lo PRIMERO que todo agente lee al entrar al repo.
> Generado a partir de `knowledge-base/` y `CHANGES.md`. No editar a mano sin re-sincronizar ambos archivos.

---

## Stack Tecnológico

**Decisión DD-04 (revisada 2026-10-11) — Python (FastAPI) + React/Vite.** Fuente: [knowledge-base/02_descripcion_general.md](knowledge-base/02_descripcion_general.md)

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

---

## Base de Conocimiento

La fuente de verdad del dominio vive en `knowledge-base/`. **Leé el archivo relevante ANTES de implementar.**

| Archivo | Cuándo leerlo |
|---------|---------------|
| [01_vision_y_objetivos.md](knowledge-base/01_vision_y_objetivos.md) | Propósito, alcance v0.1, fuera de alcance |
| [02_descripcion_general.md](knowledge-base/02_descripcion_general.md) | Stack, arquitectura multi-tenant, superficie REST |
| [03_actores_y_roles.md](knowledge-base/03_actores_y_roles.md) | 9 actores, RBAC, rutas públicas |
| [04_modelo_de_datos.md](knowledge-base/04_modelo_de_datos.md) | Entidades, ERD, aislamiento por tenant, seed |
| [05_reglas_de_negocio.md](knowledge-base/05_reglas_de_negocio.md) | Reglas codificadas (RN-XX) — incluye RN-TEN-02 |
| [06_funcionalidades.md](knowledge-base/06_funcionalidades.md) | Historias de usuario con criterios de aceptación |
| [07_flujos_principales.md](knowledge-base/07_flujos_principales.md) | Flujos E2E con casos de error |
| [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md) | Patrones, estructura, seguridad, env vars |
| [09_decisiones_y_supuestos.md](knowledge-base/09_decisiones_y_supuestos.md) | Decisiones DD y supuestos SU (SU-01: 1 dev, SU-02: deadline 2026-10-23) |
| [10_preguntas_abiertas.md](knowledge-base/10_preguntas_abiertas.md) | ⚠️ Inconsistencias y preguntas a resolver ANTES de codear |
| [11_facturacion_arca.md](knowledge-base/11_facturacion_arca.md) | Extra — ARCA: WSAA, X.509 por tenant, idempotencia |
| [12_historia_clinical_y_compliance.md](knowledge-base/12_historia_clinical_y_compliance.md) | Extra — Ley 26.529, Ley 25.326 + AAIP, inmutabilidad |

> ⚠️ Resolver las preguntas de prioridad **Alta** de `10_preguntas_abiertas.md` antes de arrancar un change que toque su dominio.

---

## Skills Disponibles

Fuente de verdad: `.atl/skill-registry.md` (**versionado** en el repo; generado por `skill-registry`). Las skills resueltas para este proyecto están **vendorizadas en `.agents/skills/`** (project-local): viajan con el repo. Las copias globales (`~/.config/opencode/skills/`, `~/.agents/skills/`) quedan como origen upstream.

| Agente | Rol | Skills que carga |
|--------|-----|------------------|
| **sdd-orchestrator** | Coordinador primario — delega vía `task`, nunca ejecuta inline | active-orchestrator, agents-md-generator, discovery-research, find-skills, kb-creator, roadmap-generator, skill-creator, skill-registry, web-scraper + openspec-{explore,propose,apply,archive,update,sync} |
| **Backend Core** | FastAPI / SQLAlchemy / Postgres — vertical slices API | tdd, supabase-postgres-best-practices (las skills Python/FastAPI se instalarán al tocar el backend) |
| **Frontend** | React + Vite + shadcn/ui — vertical slices UI | vercel-react-best-practices, shadcn, tdd, playwright-cli |
| **QA / E2E** | Gates de integración y aislamiento | playwright-cli, tdd, supabase-postgres-best-practices |

Cargá la skill correspondiente al contexto ANTES de escribir código.

> Los compact rules de cada skill los resuelve el orquestador desde `.atl/skill-registry.md` (versionado en el repo). Las skills viven en `.agents/skills/` (project-local). Esta tabla solo mapea skill→rol.

---

## Roadmap de Changes

El plan completo está en [CHANGES.md](CHANGES.md). Resumen:

- **Total**: 23 changes en 9 fases (FASE 0 a FASE 8).
- **Sprint 1 dev** (SU-01: 1 dev, SU-02: deadline **2026-10-23**): la "ruta del turno", 6 changes secuenciales — `C-01 → C-02 → C-03 → C-05 → C-06 → C-07`. **META (entregable TP)**: change `agendar-turno-sin-solapamiento` (crear turno sin solapamientos por profesional y sillón — RN-AG-02). Sin paralelismo.
- **Backlog post-deadline**: 17 changes (C-04, C-08…C-23), facturación priorizada según DD-01.
- **Primer change**: `C-01` (foundation-setup) — ya propuesto en `openspec/changes/c-01-foundation-setup/`.

**Antes de cualquier `/opsx:propose`**: leé [CHANGES.md](CHANGES.md), identificá las dependencias del change y los archivos de "Leer antes".

---

## Reglas Duras

> Las reglas universales del harness (orquestador `sdd-orchestrator`, governance por criticidad, Strict TDD, engram, OPSX) las define la configuración de opencode (`C:\Users\L\.config\opencode\opencode.json`) y las skills del stack. El proyecto las **hereda**, no se repiten acá. Acá viven las reglas **específicas del proyecto** (stack-aware, confirmadas con el usuario) + las universales que el harness no cubre. Son contrato; romperlas es un defecto.

- **NUNCA** mergear un change que toque una tabla con `tenant_id` sin su **test de aislamiento cross-tenant** → RN-TEN-02 es gate de merge, no sugerencia: `cross-tenant leak = 0`.
- **NUNCA** resolver el `tenant_id` desde el body/query de la petición → siempre del token/sesión; abrir cada sesión de DB con `SET LOCAL app.current_tenant`; RLS activo en toda tabla de negocio (`tenant_id NOT NULL`) — DD-07.
- **NUNCA** hacer `UPDATE`/`DELETE` sobre datos de historia clínica → append-only con `supersedes_id` (Ley 26.529 arts. 12, 16, 18) — RN-CMP-02.
- **NUNCA** llamar a ARCA de forma síncrona dentro de un request → Outbox + cola Celery (Redis) con estados `BORRADOR → PENDIENTE → EMITIDO/RECHAZADO` — DD-06.
- **NUNCA** emitir un comprobante con el tipo elegido a mano → derivarlo del estado fiscal del cliente (obra social → A, monotributista → C, etc.).
- **NUNCA** guardar certificados X.509 ni claves en claro o en logs → cifrado por tenant; validar el CUIT del certificado contra el tenant; WSAA cacheado con expiración conocida.
- **NUNCA** usar `Any` en el dominio → Python con type hints estrictos (mypy strict); el contrato front↔back es el OpenAPI de FastAPI (Pydantic v2).
- **NUNCA** mockear la base de datos en flujos con RLS/tenancy → Postgres real (pytest + Testcontainers).
- **NUNCA** construir por capas → **vertical slices** (DD-03): cada change entrega API + UI de su capacidad.
- **NUNCA** buildear, commitear, amendar ni pushear sin pedido explícito del usuario → conventional commits, sin co-autoría IA.
- **NUNCA** arrancar un change sin leer `CHANGES.md` y su sección "Leer antes" → primero identificar dependencias y KB relevante.
- **NUNCA** silenciar el mínimo de compliance (RLS, sesión, auditoría base) ni bajo deadline → el sprint recorta funcionalidad (C-07), nunca compliance.

---

## Flujo de Trabajo

```
1. Leer la KB relevante (knowledge-base/)        → entender el dominio
2. Identificar el change en CHANGES.md           → respetar dependencias y Sprint 1 dev
3. /opsx:propose C-NN-nombre                     → proposal + design + specs + tasks
4. Implementar las tasks (cargando skills)       → Strict TDD + gate RN-TEN-02 + vertical slice
5. /opsx:archive C-NN-nombre                     → sync specs + cerrar el change
```

Aplicar TODAS las reglas duras en cada paso. Ante conflicto entre la KB y este archivo, las reglas duras prevalecen.