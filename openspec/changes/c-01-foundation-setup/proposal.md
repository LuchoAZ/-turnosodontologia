# Proposal

## Why

El proyecto **Gestión Odontológica PyME** (`odontologia-saas`) arranca desde un repositorio vacío: no hay monorepo, tooling, CI ni entorno local reproducible. Sin estos cimientos, ningún change posterior (C-02+) puede construirse ni testearse de forma consistente. C-01 deja el repositorio listo para que cada slice vertical siguiente se apoye en un sustrato verificado: instalación reproducible, lint/typecheck/build uniformes, base de datos y colas locales con `docker-compose`, y un harness de tests (Vitest + Testcontainers + Playwright) operativo desde el primer día.

Vale la pena ahora porque C-01 es la **raíz del árbol de dependencias**: C-02 y C-03 son estrictamente secuenciales sobre él y bloquean todo lo demás. Es el único change sin dependencias y el de mayor apalancamiento.

## What Changes

- **Monorepo TypeScript** con workspaces: `apps/api` (NestJS 11), `apps/web` (Next.js 15 App Router), `apps/worker` (proceso BullMQ standalone), `packages/shared`, `packages/contracts`, `packages/ui-kit`.
- **Configuración TypeScript strict end-to-end** compartida (base `tsconfig` + overrides por app/paquete), sin `any` en dominio.
- **Tooling de calidad**: ESLint + Prettier con reglas compartidas; scripts de raíz `lint`, `typecheck`, `build`, `test`.
- **Infraestructura local**: `docker-compose.yml` con PostgreSQL 16 y Redis 7 para desarrollo.
- **Prisma inicializado** en `apps/api/prisma` con `schema.prisma` mínimo y una migración placeholder (sin modelos de negocio; los modelos son C-02).
- **Contrato de arranque del runtime**: validación de configuración al boot — la app **falla al arrancar** si falta una variable de entorno requerida.
- **Endpoints de estado operativo** (sin datos de negocio): `GET /health` (liveness) y `GET /ready` (readiness, verifica dependencias requeridas).
- **Skeleton de observabilidad**: bootstrap de OpenTelemetry + Sentry con nombre de servicio y un contexto de correlación extensible (el `tenant_id` se incorpora en C-02).
- **Harness de tests**: Vitest (unit/integration) + Testcontainers (Postgres/Redis reales) + Playwright (e2e) configurados y con un test de humo por nivel.
- **`.env.example`** documentando las variables de entorno de `knowledge-base/08_arquitectura_propuesta.md`.
- **CI (GitHub Actions)**: pipeline `lint → typecheck → unit → build` con jobs paralelos para `api` y `web`.
- **`.gitignore`** y baseline del repositorio (artefactos de build, `.env`, `node_modules`, coverage).

## Capabilities

### New Capabilities
- `platform-runtime`: contrato operativo de arranque y estado de los servicios — validación fail-fast de configuración al boot, sondas de liveness (`/health`) y readiness (`/ready`), y bootstrap de observabilidad (OTEL/Sentry) con contexto de correlación extensible.

### Modified Capabilities
<!-- Sin cambios: el proyecto no tiene capabilities existentes (openspec/specs/ vacío). -->

## Impact

- **Estructura del repositorio**: introduce la raíz de workspaces, `apps/*`, `packages/*`, `docker-compose.yml`, `.gitignore`, `.env.example` y `.github/workflows/`.
- **Configuración del runtime**: `apps/api` y `apps/web` pasan a validar env al arrancar; nuevos endpoints `GET /health` y `GET /ready` en la API.
- **Tooling y CI**: nueva cadena ESLint/Prettier, scripts de raíz y pipeline de GitHub Actions.
- **Tests**: nuevo harness Vitest + Testcontainers + Playwright que todos los changes posteriores reutilizan (RN-TEN-02 y strict TDD dependen de él).
- **Dependencias de runtime**: NestJS 11, Next.js 15, Prisma 6, BullMQ/Redis, OpenTelemetry, Sentry, Vitest, Testcontainers, Playwright.
- **Fuera de alcance (explícito)**: sin modelos de negocio, multi-tenancy/RLS, autenticación, pacientes ni agenda (C-02/C-03/C-05/C-06/C-07 y siguientes). C-01 es solo scaffolding e infraestructura base.
