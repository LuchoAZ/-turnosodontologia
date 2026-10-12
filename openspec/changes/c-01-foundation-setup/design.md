# Design

## Context

Ver `proposal.md` para motivación y `specs/platform-runtime/spec.md` para el contrato de comportamiento. El repositorio hoy solo contiene documentación (`knowledge-base/`, `discovery/`, `CHANGES.md`) y el andamiaje de OpenSpec (`openspec/`); no hay código, ni `pyproject.toml`/`package.json`, ni carpetas `backend/`/`frontend/`, ni CI. `knowledge-base/08_arquitectura_propuesta.md` ya fija la estructura de directorios objetivo, el stack y la estrategia de CI; este diseño la operacionaliza para C-01 sin introducir modelos de negocio.

Restricción dominante: **strict TDD** con vertical slices y **governance MEDIO** (implementar con checkpoints y surface decisiones). Como C-01 es la raíz del árbol de dependencias, cualquier decisión de tooling acá se propaga a C-02+. Se prioriza el camino con menos piezas móviles y menos ambigüedad para 1 developer.

## Goals / Non-Goals

**Goals:**
- Dejar el repo instalable y construible con un solo comando, con lint/typecheck/build/test reproducibles.
- Habilitar el harness de tests (pytest + Testcontainers en el backend; Vitest en el frontend; Playwright para e2e) para que C-02+ pueda hacer TDD real desde su primer task.
- Implementar el contrato de `platform-runtime` (validación de config, `/health`, `/ready`, observabilidad) con tests que fallan primero.
- Tener un entorno local reproducible (`docker-compose`) y un pipeline de CI que bloquee regresiones de lint/typecheck/test/build.

**Non-Goals:**
- Ningún modelo de datos de negocio ni migración con DDL (eso es C-02).
- RLS, `SET LOCAL app.current_tenant`, guards de auth/tenant/roles (C-02/C-03).
- Autenticación, sesión, MFA (C-03).
- Cualquier endpoint con datos de negocio.
- Configuración de despliegue a nube (IaC, ECS/Cloud Run): los entornos de C-01 son local + CI.

## Decisions

**D1 — Estructura `backend/` + `frontend/`, sin monorepo tooling.**
Dos carpetas independientes: `backend/` (Python 3.12 + FastAPI, gestionado con `pyproject.toml` + `uv`/venv) y `frontend/` (React + TypeScript + Vite, gestionado con npm). No hay npm workspaces ni Turborepo: cada lado tiene su propio toolchain y sus scripts; `docker-compose.yml` orquesta la infraestructura local.
- Alternativas: **monorepo con npm workspaces + Turborepo** (irrelevante con dos lenguajes y dos gestores distintos: Turborepo solo orquesta JS), **Nx** (más curva y opinado, innecesario para 1 dev), **pnpm workspaces** (no aplica al backend Python).
- Por qué: con Python y TypeScript no hay un grafo de tareas compartido; la separación por carpeta es el camino con menos piezas móviles.

**D2 — Validación de entorno por lado: pydantic-settings (backend) + Zod (frontend).**
El backend valida su configuración al boot con una clase `Settings` de `pydantic-settings` que lanza al parsear y hace fallar el arranque. El frontend, si valida variables de build, lo hace con Zod (solo cliente).
- Alternativas: un único lenguaje de validación end-to-end (ya no aplica: el contrato de datos entre front y back es el OpenAPI de FastAPI, no un esquema Zod compartido).
- Por qué: cada runtime usa su librería idiomática; `pydantic-settings` es el estándar de config tipada en FastAPI.

**D3 — Runners de tests por lado: pytest (backend) y Vitest (frontend); Playwright para e2e.**
pytest + pytest-asyncio corren unit e integration del backend; los tests de integración usan **Testcontainers (Python)** con Postgres 16 + Redis 7 reales (sin mocks de DB). Vitest cubre el frontend. Playwright cubre e2e.
- Alternativas: **Jest** (no aplica: el backend es Python), **un solo runner** (imposible con dos lenguajes).
- Por qué: cada lado usa su runner idiomático; la KB 02 y el stack registry fijan pytest/Vitest/Playwright.

**D4 — Sondas de salud con probes asíncronos en FastAPI.**
`/health` (liveness) y `/ready` (readiness) son endpoints FastAPI; la readiness ejecuta probes asíncronos a Postgres y Redis. La liveness no toca dependencias.
- Alternativas: **dependencia de health de terceros** (innecesaria: el contrato es trivial con FastAPI).
- Por qué: el contrato HTTP no cambia (mismos `/health` y `/ready`); solo cambia la implementación (ya no `@nestjs/terminus`), con probes inyectables para testear el `503`.

**D5 — Validación de config como función/clase testeable, inyectada en el boot.**
La lógica vive en `load_config(env) → Config` (clase `pydantic-settings`) testeable sin levantar FastAPI; `main.py` la invoca al arrancar y aborta el proceso ante error. Define la costura de test principal (ver "Seams de TDD").

**D6 — Observabilidad con un bootstrap compartido y modo degradado.**
Un módulo en `backend/app/infra` inicializa OpenTelemetry (Python SDK: nombre de servicio + contexto de correlación extensible) y `sentry-sdk`; el entrypoint lo invoca. Si falta `OTEL_EXPORTER_OTLP_ENDPOINT` o `SENTRY_DSN`, arranca en modo degradado sin fallar (el spec lo exige para no bloquear dev/CI).
- Alternativas: inicialización duplicada por entrypoint (deriva y comportamiento divergente).
- Por qué: comportamiento uniforme y un único punto donde C-02+ agrega `tenant_id` al contexto.

**D7 — SQLAlchemy 2.0 engine + baseline de Alembic vacío.**
Configurar el engine de SQLAlchemy y una migración baseline de Alembic (DDL vacío o mínimo) que demuestra que el pipeline `alembic upgrade` funciona en CI antes de que C-02 agregue modelos reales.
- Alternativas: no crear ninguna migración hasta C-02 (deja el pipeline sin validar en CI).
- Por qué: valida la cadena migrate/upgrade sin adelantar el dominio de C-02.

**D8 — CI en GitHub Actions con jobs backend, frontend, integration y e2e.**
Jobs: `backend` (`ruff`→`mypy`→`pytest`→build), `frontend` (`eslint`→`tsc`→`vitest`→build), `integration` (smoke con Testcontainers Postgres+Redis) y `e2e` (Playwright smoke). Caché de `uv`/pip y de npm. Todos bloquean merge.
- Alternativas: un único job secuencial (más lento y sin separación backend/frontend) o correr e2e fuera de CI (deja el harness sin probar).
- Por qué: 08 fija `ruff → mypy / tsc → unit → integration → e2e → build`; C-01 lo hace real con un test de humo por nivel.

**D9 — Bootstrap con tooling oficial (Vite + uv/pip), luego adaptación a la estructura.**
Generar `frontend/` con `npm create vite` (React + TS + Tailwind) e inicializar `backend/` con `uv init`/`pyproject.toml` + la plantilla FastAPI; luego alinear ambos a la estructura de directorios de `08_arquitectura_propuesta.md`.
- Alternativas: escribir todo el boilerplate a mano (más control, más error-prone y más cosas que mantener).
- Por qué: arranca desde configuraciones oficiales de Vite/FastAPI y reduce el riesgo de versiones/flags incorrectos.

**D10 — Typing estricto por lado: `mypy` strict (backend) + `tsc` strict (frontend).**
`backend/pyproject.toml` con `mypy` en modo strict (sin `Any` en dominio); `frontend/tsconfig.json` con `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`, etc. Cada lado cubre su propio dominio sin escapar del tipado.

### Seams de TDD (a confirmar antes de escribir tests)

Strict TDD exige acordar las costuras públicas antes del primer test. Para C-01 las costuras propuestas son:
- **Config**: `load_config(env) → Config` (clase `pydantic-settings`; sin acceso a `os.environ` global más allá del `env` inyectado). Casos: config completa, var ausente, var inválida.
- **Readiness**: probe de dependencia detrás de una interfaz para inyectar un probe que falla y verificar `503` sin romper el Postgres real.
- **HTTP**: `GET /health` y `GET /ready` como contrato observable (test de integración con `httpx.AsyncClient`/`TestClient`).
- **Observabilidad**: bootstrap que devuelve un estado (`configured` | `degraded`) y una verificación de "tracer inicializado", sin depender de un backend real (exporter no-op en test).

## Risks / Trade-offs

- **[pytest-asyncio y el event loop]** Los tests async de FastAPI dependen de la configuración de `asyncio_mode`/fixtures de event loop; un desajuste de versión rompe suites enteras. → Mitigación: fijar versiones de `pytest`/`pytest-asyncio` en `pyproject.toml` y usar fixtures explícitos de event loop.
- **[Testcontainers en CI]** Requiere Docker en el runner (disponible en GitHub `ubuntu-latest`) y puede ser lento. → Mitigación: imágenes pineadas, contenedores reutilizables entre tests, y el job de integración corre solo un smoke; si el tiempo crece, separar a job programado.
- **[Bootstrap con tooling oficial (Vite/uv)]** `npm create vite`/`uv init` generan configuraciones propias que hay que alinear con la estructura y los puertos de la KB. → Mitigación: fijar `engines`/`requires-python` y validar con un `npm install` + `uv sync` limpios en CI.
- **[Deriva entre esquema de env y `.env.example`]** Un cambio de config podría no documentarse. → Mitigación: `.env.example` como artefacto verificado por un test que falla si una variable del esquema no está documentada.
- **[Estructura prematura]** Crear carpetas/módulos que C-02+ aún no usan. → Mitigación: crear solo las carpetas que la estructura de 08 exige; `backend/app/*` y `frontend/src/*` quedan como esqueletos vacíos, sin contenido inventado.
- **[Alcance creep hacia features]** El andamiaje tienta a adelantar modelos o auth. → Mitigación: barrera explícita en proposal/design (Non-Goals) y tasks sin ningún item de dominio.

## Migration Plan

Greenfield: no hay datos ni sistemas en producción, así que no hay migración de datos.

1. **Bootstrap estructural** (no-TDD): estructura `backend/`+`frontend/`, tooling (`ruff`/`mypy` + ESLint/Prettier), `npm create vite` + `uv init`/plantilla FastAPI, `docker-compose.yml`, `.gitignore`, `.env.example`, baseline de Alembic. Necesario antes de poder TDD (no existe harness todavía).
2. **TDD de `platform-runtime`** (red → green → refactor), en orden: `load_config` → `/health` → `/ready` (con probe inyectable) → bootstrap de observabilidad (tracing y captura de errores).
3. **CI**: agregar los jobs y verificar que el pipeline verde reproduce lint/typecheck/unit/integration/e2e/build.
4. **Rollback**: no hay despliegue; revertir el cambio es `git revert` del commit del change. El andamiaje es idempotente (re-ejecutable) por diseño.

## Open Questions

- **Versiones exactas al momento de implementar**: los pins de Python/FastAPI/SQLAlchemy/React/Vite/Redis y las tags de imagen Docker se fijan al ejecutar C-01 (las "latest"/"mínima" de la KB se traducen a versiones concretas). No cambia el approach ni el spec, solo los valores de pin.
