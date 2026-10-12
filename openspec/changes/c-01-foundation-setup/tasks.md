# Tasks

## 1. Bootstrap del monorepo y tooling

- [ ] 1.1 Crear `package.json` raíz con npm workspaces (`apps/*`, `packages/*`) y `engines` Node 22 LTS; verificar con un `npm install` limpio en la raíz que resuelve los workspaces sin lockfiles anidados.
- [ ] 1.2 Agregar `turbo.json` con los pipelines `lint`/`typecheck`/`build`/`test` y sus `dependsOn`; verificar que `npx turbo run build` lista las tareas en el orden de dependencias esperado.
- [ ] 1.3 Crear `tsconfig.base.json` strict (`strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`) y un `tsconfig.json` por app/paquete que lo extiende; verificar con `npx tsc -p <paquete> --noEmit` sobre el esqueleto sin errores.
- [ ] 1.4 Configurar ESLint + Prettier compartidos (flat config) y scripts `lint` a nivel raíz; verificar que `npm run lint` pasa sobre el esqueleto.
- [ ] 1.5 Crear `.gitignore` (node_modules, `dist`, `.env*` salvo `.env.example`, `coverage`, `.turbo`) y verificar con `git status` que no aparecen artefactos de build.
- [ ] 1.6 Crear los paquetes esqueleto `packages/shared`, `packages/contracts`, `packages/ui-kit` (`package.json` + `tsconfig`, sin contenido inventado); verificar que cada uno se resuelve como workspace y compila vacío.
- [ ] 1.7 Configurar Vitest por paquete (config compartida) con un test de humo trivial en cada uno; verificar que `npm run test` en raíz ejecuta los humos en verde. (harness unit listo para el grupo 4)

## 2. Generar apps y conectarlas al workspace

- [ ] 2.1 Generar `apps/web` con `create-next-app` (TS, App Router, Tailwind) y plegarlo al workspace (quitar lockfile anidado, extender el tsconfig base); verificar que `npm run build --workspace apps/web` produce build.
- [ ] 2.2 Generar `apps/api` con `nest new` y plegarlo al workspace; verificar que `npm run build --workspace apps/api` y `npm run typecheck` pasan.
- [ ] 2.3 Crear `apps/worker` como esqueleto BullMQ standalone con entrypoint propio (sin jobs aún); verificar que `npm run build --workspace apps/worker` produce build.
- [ ] 2.4 Inicializar shadcn/ui en `apps/web` (Tailwind 4 + `components.json`); verificar que `npx shadcn@latest info` reconoce el proyecto.

## 3. Infraestructura local, entorno y Prisma

- [ ] 3.1 Crear `docker-compose.yml` con PostgreSQL 16 y Redis 7 (puertos, volúmenes, healthchecks); verificar que `docker compose up -d` deja ambos servicios en estado `healthy`.
- [ ] 3.2 RED: escribir el test que falla si una variable del esquema de entorno no está documentada en `.env.example` (guard de documentación); verificar que falla mientras `.env.example` está incompleto.
- [ ] 3.3 GREEN: escribir `.env.example` documentando todas las variables de `knowledge-base/08_arquitectura_propuesta.md` (incluidas las agrupadas S3/OTEL); verificar que el guard de 3.2 pasa y que no se commitea ningún valor real.
- [ ] 3.4 Inicializar Prisma en `apps/api/prisma` (`datasource` + `generator`, sin modelos) + migración baseline; verificar que `npx prisma migrate deploy` aplica la baseline contra el Postgres de docker-compose y que `npx prisma generate` funciona.
- [ ] 3.5 Configurar el helper de Testcontainers (Postgres 16 + Redis 7) para tests de integración; verificar con un smoke que levanta un contenedor, conecta y lo baja (pasa localmente).

## 4. TDD del contrato `platform-runtime`

- [ ] 4.1 RED: escribir los tests unitarios de `loadConfig(env)` que fallan — config completa, variable requerida ausente, variable inválida; verificar que `npm run test` falla por estos tests nuevos.
- [ ] 4.2 GREEN: implementar `loadConfig` con esquema Zod e invocarlo en `main.ts` abortando con código ≠ 0 y mensaje que nombra la variable; verificar que 4.1 pasa.
- [ ] 4.3 RED: escribir el test de integración de `GET /health` (200, sin datos de negocio, y sigue 200 con una dependencia caída); verificar que el test falla.
- [ ] 4.4 GREEN: implementar la liveness con `@nestjs/terminus` (sin indicadores de dependencias); verificar que 4.3 pasa.
- [ ] 4.5 RED: escribir el test de integración de `GET /ready` (200 con dependencias up; 503 con un probe inyectado que falla); verificar que el test falla.
- [ ] 4.6 GREEN: implementar la readiness con indicadores Postgres + Redis detrás de probes inyectables; verificar que 4.5 pasa.
- [ ] 4.7 RED: escribir los tests del bootstrap de observabilidad (estado `configured`/`degraded`, tracer inicializado sin backend real, captura de errores con DSN y modo degradado sin DSN); verificar que los tests fallan.
- [ ] 4.8 GREEN: implementar el bootstrap compartido (OTEL + Sentry) en `packages/shared` e invocarlo en los entrypoints de api/web/worker; verificar que 4.7 pasa.
- [ ] 4.9 Documentar en `docs/foundation.md` cómo correr local, los endpoints de salud y las variables de entorno; verificar que los comandos del documento corren tal cual.

## 5. Harness e2e y scripts de raíz

- [ ] 5.1 Configurar Playwright en `apps/web` con un smoke test de la página base; verificar que `npx playwright test` pasa localmente.
- [ ] 5.2 Agregar los scripts de raíz `test`, `test:integration` y `test:e2e` (vía Turborepo); verificar que cada nivel corre y reporta su resultado.

## 6. Pipeline de CI

- [ ] 6.1 Crear los jobs `api` y `web` en GitHub Actions (`lint → typecheck → unit → build`) con caché de npm/Turborepo; verificar que el pipeline corre en verde en un PR de prueba.
- [ ] 6.2 Agregar los jobs `integration` (smoke con Testcontainers) y `e2e` (Playwright smoke); verificar que ambos quedan en verde en CI.
- [ ] 6.3 Marcar los jobs como bloqueantes de merge; verificar que un lint/typecheck/test roto hace fallar el pipeline.

## 7. Verificación de integración

- [ ] 7.1 Verificar el pipeline completo `lint → typecheck → unit → integration → e2e → build` en verde sobre el PR del change.
- [ ] 7.2 Verificar reproducibilidad desde cero: clonar limpio, `npm install`, `docker compose up -d`, `npm run build` y `npm run test` completan sin pasos manuales ocultos.
- [ ] 7.3 Verificar que el árbol de dependencias queda desbloqueado: `GET /health` y `GET /ready` responden, la migración baseline aplica y el harness de tests está operativo para C-02.
