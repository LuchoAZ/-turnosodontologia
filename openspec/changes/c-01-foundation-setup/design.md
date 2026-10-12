# Design

## Context

Ver `proposal.md` para motivación y `specs/platform-runtime/spec.md` para el contrato de comportamiento. El repositorio hoy solo contiene documentación (`knowledge-base/`, `discovery/`, `CHANGES.md`) y el andamiaje de OpenSpec (`openspec/`); no hay código, ni `package.json`, ni workspaces, ni CI. `knowledge-base/08_arquitectura_propuesta.md` ya fija la estructura de directorios objetivo, el stack y la estrategia de CI; este diseño la operacionaliza para C-01 sin introducir modelos de negocio.

Restricción dominante: **strict TDD** con vertical slices y **governance MEDIO** (implementar con checkpoints y surface decisiones). Como C-01 es la raíz del árbol de dependencias, cualquier decisión de tooling acá se propaga a C-02+. Se prioriza el camino con menos piezas móviles y menos ambigüedad para 1 developer.

## Goals / Non-Goals

**Goals:**
- Dejar el repo instalable y construible con un solo comando, con lint/typecheck/build/test reproducibles.
- Habilitar el harness de tests (Vitest + Testcontainers + Playwright) para que C-02+ pueda hacer TDD real desde su primer task.
- Implementar el contrato de `platform-runtime` (validación de config, `/health`, `/ready`, observabilidad) con tests que fallan primero.
- Tener un entorno local reproducible (`docker-compose`) y un pipeline de CI que bloquee regresiones de lint/typecheck/test/build.

**Non-Goals:**
- Ningún modelo de datos de negocio ni migración con DDL (eso es C-02).
- RLS, `SET LOCAL app.current_tenant`, guards de auth/tenant/roles (C-02/C-03).
- Autenticación, sesión, MFA (C-03).
- Cualquier endpoint con datos de negocio.
- Configuración de despliegue a nube (IaC, ECS/Cloud Run): los entornos de C-01 son local + CI.

## Decisions

**D1 — Monorepo con npm workspaces + Turborepo.**
`package.json` raíz con `workspaces: ["apps/*", "packages/*"]`; `turbo.json` orquesta `lint`/`typecheck`/`build`/`test` con caché y `dependsOn` correctos (p. ej. `build` depende de `^build` para los paquetes).
- Alternativas: **Nx** (más potente pero más curva y opinado, innecesario para 1 dev), **pnpm workspaces** (excelente, pero agrega un gestor no presente en el stack y fricción en CI), **scripts npm puros** (sin caché ni grafo de tareas; se degrada al agregar paquetes).
- Por qué: Node 22 LTS ya trae npm; Turborepo da caché y orden de build sin imponer un framework.

**D2 — Un único manejador de validación de entorno: Zod.**
La validación de config al boot usa un esquema Zod por app, con `parse` que lanza y hace fallar el arranque; el mismo Zod es el lenguaje de validación end-to-end que la KB fija para DTOs (schema-first, compartido web↔api).
- Alternativas: **Joi** (la KB lo menciona como alternativa y es lo idiomático en NestJS, pero crearía dos librerías de validación en el proyecto).
- Por qué: una sola librería de validación en todo el stack evita divergencias web↔api y ya es obligatoria para C-02+.

**D3 — Runner de tests: Vitest para unit/integration; Playwright para e2e.**
Vitest en todos los paquetes (rápido, ESM-first, compatible con la config TS strict). Los tests de integración usan **Testcontainers** (Postgres 16 + Redis 7 reales, sin mocks de DB). Playwright cubre e2e de la web.
- Alternativas: **Jest** (default de NestJS; buena integración con `TestingModule`, pero runner distinto al de web y más lento en monorepo).
- Por qué: la KB 02 y el stack registry fijan Vitest + Testcontainers + Playwright. Trade-off registrado en Riesgos (integración con utilidades de testing de Nest).

**D4 — Sondas de salud con `@nestjs/terminus`.**
`/health` (liveness) y `/ready` (readiness) implementados con Terminus; la readiness registra indicadores de Postgres y Redis. La liveness no registra indicadores de dependencias.
- Alternativas: **controlador artesanal** (menos dependencias, pero reimplementa semántica y no se integra con OTEL).
- Por qué: Terminus es estándar en NestJS 11 y expone exactamente la distinción liveness/readiness que pide el spec.

**D5 — Validación de config como función pura, inyectada en el boot.**
La lógica de validación vive en una función pura `loadConfig(env) → Config` (testeable sin levantar Nest); `main.ts` la invoca al arrancar y aborta con `process.exit(1)` ante error. Esto define la costura de test principal (ver "Seams de TDD").

**D6 — Observabilidad con un bootstrap compartido y modo degradado.**
Un helper en `packages/shared` inicializa OpenTelemetry (nombre de servicio + contexto de correlación extensible) y Sentry; cada app lo invoca en su entrypoint. Si falta `OTEL_EXPORTER_OTLP_ENDPOINT` o `SENTRY_DSN`, arranca en modo degradado sin fallar (el spec lo exige para no bloquear dev/CI).
- Alternativas: inicialización duplicada por app (deriva y comportamiento divergente).
- Por qué: comportamiento uniforme y un único punto donde C-02+ agrega `tenant_id` al contexto.

**D7 — Prisma: schema sin modelos + migración baseline vacía.**
`apps/api/prisma/schema.prisma` con `datasource` + `generator` y **cero modelos**; una migración baseline (DDL vacío o mínimo) demuestra que el pipeline `prisma migrate` funciona en CI antes de que C-02 agregue modelos reales.
- Alternativas: no crear ninguna migración hasta C-02 (deja el pipeline sin validar en CI).
- Por qué: valida la cadena migrate/generate sin adelantar el dominio de C-02.

**D8 — CI en GitHub Actions con jobs paralelos por app + jobs de harness.**
Jobs: `api` (lint→typecheck→unit→build), `web` (lint→typecheck→unit→build), `integration` (smoke con Testcontainers Postgres+Redis) y `e2e` (Playwright smoke). Caché de npm y de Turborepo. Todos bloquean merge.
- Alternativas: un único job secuencial (más simple, mucho más lento y sin paralelismo api/web) o correr e2e fuera de CI (deja el harness sin probar).
- Por qué: 08 fija `lint → typecheck → unit → integration → e2e → build`; C-01 lo hace real con un test de humo por nivel.

**D9 — Bootstrap de apps con los CLIs oficiales, luego adaptación al monorepo.**
Generar `apps/web` con `create-next-app` (App Router, TS, Tailwind) y `apps/api` con `nest new`, y luego plegarlos al workspace (eliminar lockfiles anidados, alinear versiones, conectar al `tsconfig` base y a Turborepo).
- Alternativas: escribir todo el boilerplate a mano (más control, más error-prone y más cosas que mantener).
- Por qué: arranca desde configuraciones oficiales de Next 15 / Nest 11 y reduce el riesgo de versiones/flags incorrectos.

**D10 — TypeScript strict centralizado.**
Un `tsconfig.base.json` con `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`, etc.; cada app/paquete extiende y sólo overridea lo imprescindible (`module`/`moduleResolution`, `jsx`, `lib`). Sin `any` en dominio (regla de la KB).

### Seams de TDD (a confirmar antes de escribir tests)

Strict TDD exige acordar las costuras públicas antes del primer test. Para C-01 las costuras propuestas son:
- **Config**: `loadConfig(env) → Config` (pura; sin acceso a `process` global más allá del `env` inyectado). Casos: config completa, var ausente, var inválida.
- **Readiness**: indicador de dependencia detrás de una interfaz (probe) para inyectar un probe que falla y verificar `503` sin romper el Postgres real.
- **HTTP**: `GET /health` y `GET /ready` como contrato observable (test de integración con `supertest`).
- **Observabilidad**: bootstrap que devuelve un estado (`configured` | `degraded`) y una verificación de "tracer inicializado", sin depender de un backend real (exporter no-op en test).

## Risks / Trade-offs

- **[Vitest vs utilidades de testing de NestJS 11]** NestJS documenta Jest; `@nestjs/testing` es agnóstico, pero algunas utilidades asumen Jest. → Mitigación: usar Vitest con API compatible; si una suite específica de Nest se resiste, aislarla y evaluar Jest solo para esa suite (decisión a surfacear si ocurre).
- **[Testcontainers en CI]** Requiere Docker en el runner (disponible en GitHub `ubuntu-latest`) y puede ser lento. → Mitigación: imágenes pineadas, contenedores reutilizables entre tests, y el job de integración corre solo un smoke; si el tiempo crece, separar a job programado.
- **[Bootstrap con CLIs oficiales + workspaces]** Next/Nest generan configs y lockfiles propios que chocan al hoisting de npm workspaces. → Mitigación: borrar lockfiles anidados, fijar `engines`, y validar con un `npm install` limpio en CI.
- **[Deriva entre esquema de env y `.env.example`]** Un cambio de config podría no documentarse. → Mitigación: `.env.example` como artefacto verificado por un test que falla si una variable del esquema no está documentada.
- **[Estructura prematura]** Crear paquetes que C-02+ aún no usan. → Mitigación: crear solo los paquetes que la estructura de 08 exige; `contracts`/`ui-kit` quedan como esqueletos vacíos con `package.json` y `tsconfig`, sin contenido inventado.
- **[Alcance creep hacia features]** El andamiaje tienta a adelantar modelos o auth. → Mitigación: barrera explícita en proposal/design (Non-Goals) y tasks sin ningún item de dominio.

## Migration Plan

Greenfield: no hay datos ni sistemas en producción, así que no hay migración de datos.

1. **Bootstrap estructural** (no-TDD): workspaces, tsconfig base, tooling, ejecutar CLIs de Next/Nest, `docker-compose.yml`, `.gitignore`, `.env.example`, Prisma baseline, Turborepo. Necesario antes de poder TDD (no existe harness todavía).
2. **TDD de `platform-runtime`** (red → green → refactor), en orden: `loadConfig` → `/health` → `/ready` (con probe inyectable) → bootstrap de observabilidad (tracing y captura de errores).
3. **CI**: agregar los jobs y verificar que el pipeline verde reproduce lint/typecheck/unit/integration/e2e/build.
4. **Rollback**: no hay despliegue; revertir el cambio es `git revert` del commit del change. El andamiaje es idempotente (re-ejecutable) por diseño.

## Open Questions

- **Versiones exactas al momento de implementar**: los pins de Node/Next/Nest/Prisma/Redis y las tags de imagen Docker se fijan al ejecutar C-01 (las "latest"/"mínima" de la KB se traducen a versiones concretas). No cambia el approach ni el spec, solo los valores de pin.
