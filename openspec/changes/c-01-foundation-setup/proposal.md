# Proposal

## Why

El proyecto **Gestión Odontológica PyME** (`odontologia-saas`) arranca desde un repositorio vacío: no hay backend/frontend, tooling, CI ni entorno local reproducible. Sin estos cimientos, ningún change posterior (C-02+) puede construirse ni testearse de forma consistente. C-01 deja el repositorio listo para que cada slice vertical siguiente se apoye en un sustrato verificado: instalación reproducible, lint/typecheck/build uniformes, base de datos y colas locales con `docker-compose`, y un harness de tests (pytest + Testcontainers + Playwright en el backend; Vitest en el frontend) operativo desde el primer día.

Vale la pena ahora porque C-01 es la **raíz del árbol de dependencias**: C-02 y C-03 son estrictamente secuenciales sobre él y bloquean todo lo demás. Es el único change sin dependencias y el de mayor apalancamiento.

## What Changes

- **Repositorio backend/frontend**: `backend/` (FastAPI, Python 3.12; `pyproject.toml` con `uv`/venv) + `frontend/` (React 18 + TypeScript + Vite; npm). Sin npm workspaces ni Turborepo.
- **Typing estricto en ambos lados**: `mypy` strict en `backend/` (sin `Any` en dominio) y `tsc` strict en `frontend/` (sin `any` en dominio).
- **Tooling de calidad**: `ruff` + `mypy` (backend) y ESLint + Prettier (frontend); scripts por carpeta `lint`, `typecheck`, `test`, `build`.
- **Infraestructura local**: `docker-compose.yml` con PostgreSQL 16, Redis 7, `backend`, `worker` (Celery) y `frontend`.
- **Alembic (SQLAlchemy 2.0) inicializado** en `backend/` con una migración baseline (sin modelos de negocio; los modelos son C-02).
- **Contrato de arranque del runtime**: validación de configuración al boot con `pydantic-settings` — el backend **falla al arrancar** si falta una variable de entorno requerida.
- **Endpoints de estado operativo** (sin datos de negocio): `GET /health` (liveness) y `GET /ready` (readiness con probes a Postgres + Redis).
- **Skeleton de observabilidad**: bootstrap de OpenTelemetry (Python SDK) + `sentry-sdk` con modo degradado y un contexto de correlación extensible (el `tenant_id` se incorpora en C-02).
- **Harness de tests**: pytest + pytest-asyncio + Testcontainers (Python) para el backend; Vitest para el frontend; Playwright (e2e); con un test de humo por nivel.
- **`.env.example`** documentando las variables de entorno de `knowledge-base/08_arquitectura_propuesta.md`.
- **CI (GitHub Actions)**: jobs `backend` (`ruff → mypy → pytest → build`), `frontend` (`eslint → tsc → vitest → build`), `integration` (smoke con Testcontainers) y `e2e` (Playwright smoke).
- **`.gitignore`** y baseline del repositorio (artefactos de build, `.env`, `.venv`, `node_modules`, `__pycache__`, coverage).

## Capabilities

### New Capabilities
- `platform-runtime`: contrato operativo de arranque y estado de los servicios — validación fail-fast de configuración al boot, sondas de liveness (`/health`) y readiness (`/ready`), y bootstrap de observabilidad (OTEL/Sentry) con contexto de correlación extensible.

### Modified Capabilities
<!-- Sin cambios: el proyecto no tiene capabilities existentes (openspec/specs/ vacío). -->

## Impact

- **Estructura del repositorio**: introduce `backend/` (FastAPI) + `frontend/` (React/Vite), `docker-compose.yml`, `.gitignore`, `.env.example` y `.github/workflows/`.
- **Configuración del runtime**: `backend/` valida env al arrancar (`pydantic-settings`); nuevos endpoints `GET /health` y `GET /ready` en FastAPI.
- **Tooling y CI**: nueva cadena `ruff`/`mypy` (backend) + ESLint/Prettier (frontend) y pipeline de GitHub Actions.
- **Tests**: nuevo harness pytest + Testcontainers (backend) + Vitest (frontend) + Playwright (e2e) que todos los changes posteriores reutilizan (RN-TEN-02 y strict TDD dependen de él).
- **Dependencias de runtime**: FastAPI, Pydantic v2, SQLAlchemy 2.0 + Alembic, Celery/Redis, React 18 + Vite, OpenTelemetry (Python SDK), Sentry, pytest, Testcontainers, Playwright, Vitest.
- **Fuera de alcance (explícito)**: sin modelos de negocio, multi-tenancy/RLS, autenticación, pacientes ni agenda (C-02/C-03/C-05/C-06/C-07 y siguientes). C-01 es solo scaffolding e infraestructura base.
