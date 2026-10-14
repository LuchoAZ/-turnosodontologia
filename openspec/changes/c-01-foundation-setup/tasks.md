# Tasks

## 1. Bootstrap del repositorio y tooling

- [x] 1.1 Crear `backend/pyproject.toml` (Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, pydantic-settings, `ruff`, `mypy`, `pytest`) y `frontend/package.json` (React 18 + TypeScript + Vite); verificar con `uv sync` (o `pip install -e ".[dev]"`) en `backend/` y `npm install` en `frontend/` que cada lado se resuelve sin pasos manuales ocultos.
- [x] 1.2 Configurar el tooling de calidad por lado: `ruff` + `mypy` (backend) y ESLint + Prettier (frontend), con scripts `lint`/`typecheck`/`test`/`build` por carpeta; verificar que `ruff check`/`mypy` y `npm run lint` pasan sobre el esqueleto.
- [x] 1.3 Configurar typing estricto: `mypy --strict` en `backend/` (sin `Any` en dominio) y `tsconfig` strict en `frontend/` (`strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`); verificar con `mypy app` y `npx tsc --noEmit` sobre el esqueleto sin errores.
- [x] 1.4 Crear `.gitignore` (`.venv`, `__pycache__`, `node_modules`, `dist`, `.env*` salvo `.env.example`, `coverage`, `.pytest_cache`) y verificar con `git status` que no aparecen artefactos de build.
- [x] 1.5 Crear los esqueletos de módulos: `backend/app/{core,models,schemas,domain,infra,workers}` y `frontend/src/{routes,features,shared,api}` (sin contenido inventado); verificar que cada lado importa/compila vacío.
- [x] 1.6 Configurar pytest (backend) y Vitest (frontend) con un test de humo trivial en cada lado; verificar que `pytest` y `npm test` ejecutan los humos en verde. (harness unit listo para el grupo 4)

## 2. Generar apps y conectarlas a la estructura

- [x] 2.1 Inicializar `frontend/` con `npm create vite` (React + TS + Tailwind) y alinearlo a la estructura de la KB; verificar que `npm run build` produce build.
- [x] 2.2 Inicializar `backend/` con FastAPI (`uv`/`pyproject.toml` + `app/main.py`) y alinearlo a la estructura de la KB; verificar que `uvicorn app.main:app` arranca y que `mypy`/`pytest` pasan.
- [x] 2.3 Crear el entrypoint worker `backend/app/workers` como esqueleto Celery (`celery -A app.workers worker`, sin tareas aún); verificar que el worker arranca y se detiene.
- [x] 2.4 Inicializar shadcn/ui en `frontend/` (Tailwind 4 + `components.json`); verificar que `npx shadcn@latest info` reconoce el proyecto.

## 3. Infraestructura local, entorno y migraciones

- [x] 3.1 Crear `docker-compose.yml` con PostgreSQL 16, Redis 7, `backend`, `worker` (Celery) y `frontend` (puertos, volúmenes, healthchecks); verificar que `docker compose up -d` deja los servicios en estado `healthy`.
- [x] 3.2 RED: escribir el test que falla si una variable del esquema de entorno (pydantic-settings) no está documentada en `.env.example` (guard de documentación); verificar que falla mientras `.env.example` está incompleto.
- [x] 3.3 GREEN: escribir `.env.example` documentando todas las variables de `knowledge-base/08_arquitectura_propuesta.md` (incluidas las agrupadas S3/OTEL); verificar que el guard de 3.2 pasa y que no se commitea ningún valor real.
- [x] 3.4 Inicializar Alembic (SQLAlchemy 2.0) en `backend/` (`env.py` + migración baseline vacía, sin modelos); verificar que `alembic upgrade head` aplica la baseline contra el Postgres de docker-compose.
- [x] 3.5 Configurar el helper de Testcontainers (Python; Postgres 16 + Redis 7) para tests de integración; verificar con un smoke que levanta un contenedor, conecta y lo baja (pasa localmente).

## 4. TDD del contrato `platform-runtime`

- [x] 4.1 RED: escribir los tests unitarios de `load_config(env)` que fallan — config completa, variable requerida ausente, variable inválida; verificar que `pytest` falla por estos tests nuevos.
- [x] 4.2 GREEN: implementar `load_config` con `pydantic-settings` e invocarlo en `main.py` abortando el proceso con código ≠ 0 y mensaje que nombra la variable; verificar que 4.1 pasa.
- [x] 4.3 RED: escribir el test de integración de `GET /health` (200, sin datos de negocio, y sigue 200 con una dependencia caída); verificar que el test falla.
- [x] 4.4 GREEN: implementar la liveness en FastAPI (sin probes de dependencias); verificar que 4.3 pasa.
- [x] 4.5 RED: escribir el test de integración de `GET /ready` (200 con dependencias up; 503 con un probe inyectado que falla); verificar que el test falla.
- [x] 4.6 GREEN: implementar la readiness con probes async a Postgres + Redis detrás de probes inyectables; verificar que 4.5 pasa.
- [x] 4.7 RED: escribir los tests del bootstrap de observabilidad (estado `configured`/`degraded`, tracer inicializado sin backend real, captura de errores con DSN y modo degradado sin DSN); verificar que los tests fallan.
- [x] 4.8 GREEN: implementar el bootstrap compartido (OpenTelemetry Python SDK + `sentry-sdk`) en `backend/app/infra` e invocarlo desde el entrypoint del backend; verificar que 4.7 pasa.
- [x] 4.9 Documentar en `docs/foundation.md` cómo correr local, los endpoints de salud y las variables de entorno; verificar que los comandos del documento corren tal cual.

## 5. Harness e2e y scripts por lado

- [x] 5.1 Configurar Playwright con un smoke test de la página base del frontend; verificar que `npx playwright test` pasa localmente.
- [x] 5.2 Agregar los scripts `test`, `test:integration` y `test:e2e` por lado (pytest en el backend; Vitest/Playwright en el frontend); verificar que cada nivel corre y reporta su resultado.

## 6. Pipeline de CI

- [x] 6.1 Crear los jobs `backend` (`ruff → mypy → pytest → build`) y `frontend` (`eslint → tsc → vitest → build`) en GitHub Actions con caché de `uv`/pip y de npm; verificar que el pipeline corre en verde en un PR de prueba.
- [x] 6.2 Agregar los jobs `integration` (smoke con Testcontainers) y `e2e` (Playwright smoke); verificar que ambos quedan en verde en CI.
- [ ] 6.3 Marcar los jobs como bloqueantes de merge; verificar que un lint/typecheck/test roto hace fallar el pipeline.

## 7. Verificación de integración

- [x] 7.1 Verificar el pipeline completo `ruff → mypy / tsc → unit → integration → e2e → build` en verde sobre el PR del change.
- [x] 7.2 Verificar reproducibilidad desde cero: clonar limpio, `uv sync` (o `pip install -e ".[dev]"`) en `backend/` + `npm install` en `frontend/`, `docker compose up -d`, build y tests completan sin pasos manuales ocultos.
- [x] 7.3 Verificar que el árbol de dependencias queda desbloqueado: `GET /health` y `GET /ready` responden, la migración baseline aplica y el harness de tests está operativo para C-02.

