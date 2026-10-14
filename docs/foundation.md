# Foundation — cómo correr, sondas de salud y variables de entorno

Este documento describe el sustrato que entrega el change `c-01-foundation-setup`: cómo
levantar el backend y el frontend en local, el contrato de las sondas de salud y las
variables de entorno que el runtime valida al arrancar.

## Requisitos

| Herramienta | Versión | Para qué |
|-------------|---------|----------|
| Python | 3.12 | backend (gestionado con `uv`) |
| uv | latest | instalar/ejecutar el backend |
| Node.js + npm | 18+ | frontend (Vite) |
| Docker + docker compose | latest | stack local y tests de integración (Testcontainers) |

## Backend (FastAPI)

```powershell
cd backend
uv sync
```

El runtime **valida toda la configuración al arrancar**. Creá tu `.env` a partir de la
plantilla y levantá la API:

```powershell
Copy-Item ..\.env.example ..\.env
uv run --env-file ../.env uvicorn app.main:app --reload
```

Si falta o es inválida una variable requerida, el proceso **no arranca**: termina con
código de salida ≠ 0 y un mensaje que nombra la variable ofensora.

### Calidad y tests (backend)

```powershell
uv run ruff check .
uv run mypy app
uv run pytest
```

Los tests unitarios del contrato `platform-runtime` corren **sin Docker** (las sondas de
readiness se testean con fakes inyectados). El smoke de integración con Testcontainers
vive en `tests/integration/` y se salta automáticamente si Docker no está disponible:

```powershell
uv run pytest tests/integration
```

## Frontend (React + Vite)

```powershell
cd frontend
npm install
npm run dev      # servidor de desarrollo
npm run build    # typecheck (tsc -b) + build de producción
npm run lint
npm test         # vitest
```

## Infraestructura local (docker compose)

El stack local (PostgreSQL 16, Redis 7, `backend`, `worker` Celery y `frontend`)
se levanta con un solo comando. **Requiere un archivo `.env` en la raíz** — docker
compose lo monta vía `env_file` — creado a partir de la plantilla:

```powershell
Copy-Item .env.example .env      # una sola vez por checkout
docker compose up -d --build
docker compose ps                # postgres/redis -> healthy; backend/worker/frontend -> up
```

Con el stack arriba: `http://localhost:8000/health`, `http://localhost:8000/ready`
y el frontend en `http://localhost:5173`. Los `Dockerfile` de `backend/` y `frontend/`
son multi-stage; el backend instala sus dependencias en `/opt/venv` para que el
bind-mount de `./backend` no tape el virtualenv, y el frontend usa un volumen
anónimo para `node_modules`.

> **Reproducibilidad (clon limpio)**: el flujo completo es `uv sync` (backend) +
> `npm install` (frontend) + `Copy-Item .env.example .env` + `docker compose up -d --build`
> + `uv run pytest` / `npm test`. Sin el `.env` el compose falla con
> `env file ... not found`; ese es el único paso previo y queda documentado acá.

## Sondas de salud

El backend expone dos endpoints operativos (sin datos de negocio):

| Endpoint | Tipo | Respuesta |
|----------|------|-----------|
| `GET /health` | liveness | `200 {"status":"ok"}` — solo refleja el proceso; **no** consulta dependencias |
| `GET /ready` | readiness | `200 {"status":"ready"}` con dependencias alcanzables; `503 {"status":"unavailable","unavailable":[...]}` si alguna falla |

Ejemplos (con la API en `:8000`):

```powershell
curl.exe http://127.0.0.1:8000/health
# 200 {"status":"ok"}

curl.exe http://127.0.0.1:8000/ready
# Postgres + Redis arriba: 200 {"status":"ready"}
# dependencia caída:      503 {"status":"unavailable","unavailable":["postgres"]}
```

`/health` responde `200` aunque Postgres/Redis estén caídos (liveness); es `/ready` la que
verifica las dependencias mediante probes async detrás de interfaces inyectables.

## Observabilidad

El bootstrap compartido (`backend/app/infra/observability.py`) inicializa OpenTelemetry
(traza distribuida con nombre de servicio) y Sentry (captura de errores) en **modo
degradado**: el servicio arranca igual cuando el exportador o el DSN no están configurados.

| Variable | Sin configurar | Con configurar |
|----------|----------------|----------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | tracing `degraded` | tracing `configured` |
| `SENTRY_DSN` | error tracking `degraded` | error tracking `configured` |

## Variables de entorno

Fuente de verdad del dominio: `knowledge-base/08_arquitectura_propuesta.md`. La plantilla
completa está en `.env.example`; el esquema tipado (y qué es requerido) vive en
`backend/app/config.py`.

**Requeridas** (sin valor por defecto, el boot falla si faltan):

| Variable | Descripción |
|----------|-------------|
| `ENVIRONMENT` | `local` · `development` · `test` · `staging` · `production` |
| `DATABASE_URL` | URL de PostgreSQL |
| `REDIS_URL` | URL de Redis |
| `SESSION_SECRET` | secreto de sesión |
| `JWT_REFRESH_SECRET` | secreto de refresh de JWT |

**Opcionales en C-01** (default `None` o valor fijo): `SERVICE_NAME`,
`DEFAULT_TENANT_TIMEZONE`, `APPLY_TO_ALL_ORIGINS`, `DIRECT_URL`, `KMS_MASTER_KEY_ID`,
`ARCA_WSDL_PROD_URL`, `ARCA_WSDL_TEST_URL`, `ARCA_CERT_STORE_PASSPHRASE`,
`WHATSAPP_API_TOKEN`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`,
`EMAIL_PROVIDER_API_KEY`, `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
`OTEL_EXPORTER_OTLP_ENDPOINT`, `SENTRY_DSN`, `SIGNING_PROVIDER_URL`, `SIGNING_PROVIDER_KEY`.

> Nunca se commitea un valor real: `.env` está ignorado por `.gitignore`; sólo se versiona
> `.env.example`. Un test (`tests/unit/test_env_example_guard.py`) falla si una variable del
> esquema no está documentada en la plantilla.
