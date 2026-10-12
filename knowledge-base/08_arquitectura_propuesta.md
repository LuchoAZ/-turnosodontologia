# Arquitectura Propuesta

## Patrones aplicados

| Patrón | Dónde se usa | Por qué |
|---------|--------------|---------|
| **Backend/Frontend separados** | `backend/` (Python 3.12) + `frontend/` (React/Vite) | El contrato entre ambos es el **OpenAPI** de FastAPI (Pydantic); cada lado se desarrolla y testea con su toolchain (pytest / Vitest). |
| **Row Level Security (RLS)** | PostgreSQL, todas las tablas de negocio | Aislamiento multi-tenant a nivel de motor. Si un `WHERE` se olvida, la RLS igual impide el leak. Es la segunda barrera (RN-TEN-02). |
| **`SET LOCAL app.current_tenant`** | Sesión de SQLAlchemy (event listener) | Fija el tenant de la transacción actual. `LOCAL` = solo dura la transacción; si la conexión vuelve al pool, no arrastra el tenant. |
| **Defense in depth (4 capas)** | RLS + `TenantGuard` + `tenant_id NOT NULL` + tests | Ninguna capa es suficiente sola. La RLS protege de bugs de app; los tests protegen de regresiones. |
| **Outbox pattern** | Facturación ARCA, comunicaciones, migraciones | Un cambio de negocio y su evento se escriben en **la misma transacción**. Después un publisher los drena a la cola. Garantiza "si se guardó, se va a notificar". |
| **Idempotencia** | Emisión ARCA (`idempotency_key`), webhooks (`webhook_event`), jobs | Reintentos y entregas duplicadas son la norma en sistemas distribuidos. La clave idempotente + constraint único lo hacen seguro. |
| **Append-only + supersedes** | Historia clínica, odontograma, auditoría | La inmutabilidad por diseño (trigger de BD) es más fuerte que "no expongas un endpoint de borrado". Las correcciones son entradas nuevas. |
| **Trigger de inmutabilidad en BD** | `clinical_record`, `chart_entry`, `audit_log` | La inmutabilidad garantizada en el motor, no en la capa de aplicación. Ningún bug de ORM puede saltársela. |
| **Optimistic locking** | `appointment.version` | Defensa secundaria contra double-booking cuando se reservan 2 sillones a la vez (que sí es válido). |
| **RBAC + dependencias** | FastAPI: `require_auth` → `require_tenant` → `require_role` | Cadena de dependencias en orden fijo. El `tenant_id` se resuelve antes de validar el rol, para que el rol se evalúe **dentro** del tenant correcto. |
| **Schema-first con OpenAPI (Pydantic)** | DTOs de API (schemas Pydantic v2) | Los schemas del backend generan el OpenAPI; el frontend deriva tipos TypeScript. Imposible que el cliente acepte algo que el servidor rechaza. |
| **Strategy pattern** | Proveedores de comunicación (WhatsApp / email) | Agregar un canal nuevo = nueva strategy. No tocar el flujo de negocio. |
| **Circuit breaker** | Llamadas a ARCA y Meta | Si ARCA está caído, el sistema no intenta 1000 veces. Se abre el circuito, se degrada gracefully, y el job queda para reintentar. |
| **Soft delete + filter global** | Todas las entidades de negocio | `deleted_at` + query filter global de SQLAlchemy. Evita "borré sin querer" y permite auditoría. |
| **Jobs idempotentes + dead-letter** | Celery (Redis): emisión, recordatorios, PDFs, migraciones | Un job que falla N veces va a `dead-letter`, no se reintenta infinito. Y reejecutar un job es seguro. |
| **Moneda minorista (numeric)** | Montos | `numeric(14,2)`, nunca `float`. El redondeo de impuestos es explícito (RN-EX-08). |
| **Feature flags por tenant** | Módulos que se activan por cliente | Permite activar un módulo nuevo en un solo cliente antes de generalizar. tabla `feature_flag` por tenant. |

## Estructura de directorios

```
odontologia-saas/
├── backend/                        # Python 3.12 + FastAPI
│   ├── pyproject.toml              # deps + tooling (ruff, mypy, pytest)
│   ├── alembic/                    # migraciones versionadas (SQLAlchemy)
│   │   ├── versions/
│   │   └── env.py
│   ├── app/
│   │   ├── main.py                 # FastAPI app + OpenAPI (/docs)
│   │   ├── config.py               # pydantic-settings (validación de env)
│   │   ├── db.py                   # engine, sesiones, event SET LOCAL tenant
│   │   ├── core/                   # dependencias: require_auth, require_tenant, require_role
│   │   ├── models/                 # SQLAlchemy models (ver 04) + RLS
│   │   ├── schemas/                # Pydantic DTOs (contrato OpenAPI)
│   │   ├── domain/                 # slices verticales
│   │   │   ├── auth/
│   │   │   ├── tenancy/            # tenant, membership, roles
│   │   │   ├── onboarding/         # flujo 1
│   │   │   ├── agenda/             # appointment, availability, chair, waitinglist
│   │   │   ├── patients/
│   │   │   ├── clinical/           # records, chart, periodontograma, planes
│   │   │   ├── consents/
│   │   │   ├── compliance/         # access_request, audit_log
│   │   │   ├── cash/               # cash_session, movements, settlements
│   │   │   ├── invoicing/          # factura interna, itms, estados
│   │   │   ├── arca/               # ⚠ módulo de riesgo: WSAA + FE
│   │   │   │   ├── wsaa.py
│   │   │   │   ├── fe.py
│   │   │   │   ├── token_cache.py      # Redis lock
│   │   │   │   ├── certificate.py      # X.509 parse/sign (cryptography)
│   │   │   │   ├── error_translator.py # código ARCA → acción
│   │   │   │   └── circuit_breaker.py
│   │   │   ├── comms/              # whatsapp strategy, email strategy, outbox
│   │   │   ├── migrations/
│   │   │   ├── reports/
│   │   │   └── public/             # rutas públicas + portal
│   │   ├── infra/                  # repos, outbox publisher, s3, redis, kms
│   │   └── workers/                # tareas Celery
│   │       ├── arca_emit.py
│   │       ├── arca_retry.py
│   │       ├── comms_outbound.py
│   │       ├── reminders.py
│   │       ├── pdf.py              # comprobantes, copias (ReportLab/WeasyPrint)
│   │       └── migration.py
│   └── tests/                      # pytest + Testcontainers (Postgres+Redis)
│       ├── unit/
│       └── integration/
│
├── frontend/                       # React + TypeScript + Vite (puerto 5173)
│   └── src/
│       ├── routes/                 # React Router: login, internal, portal, public
│       ├── features/               # por dominio: agenda/, patients/, clinical/...
│       ├── shared/                 # componentes, hooks, lib
│       └── api/                    # cliente y tipos generados desde el OpenAPI
│
├── docker-compose.yml              # postgres + redis + backend + worker + frontend
├── knowledge-base/                 # esta KB
├── discovery/                      # research competitivo
└── openspec/                       # cambios OpenSpec
```

**Por qué `backend/app/workers` separado como entrypoint Celery**: la emisión ARCA y la generación
de PDFs consumen CPU y memoria; no deben competir con el pool de conexiones del API. Escalar el
worker no escala el API. El worker corre la misma app (mismo repo de modelos/outbox) con un
entrypoint distinto (`celery -A app.workers worker`).

## Seguridad

### Autenticación
- **Esquema**: sesión con cookie `httpOnly` + refresh rotativo (RN-AU-02, RN-AU-03).
  **No JWT en `localStorage`.**
- **Passwords**: Argon2id (RN-AU-01).
- **MFA**: obligatorio para `owner` y `billing` (RN-AU-04).
- **Pacientes**: OTP a teléfono verificado (RN-AU-06).
- **Tokens de un solo uso** para links públicos (confirmar turno, firmar consentimiento).

### Autorización
- **Cadena de dependencias** obligatoria y en orden: `require_auth` → `require_tenant` → `require_role` → `require_idempotency` (FastAPI `Depends`).
- **`tenant_id` siempre del token**, nunca del request (RN-TEN-03).
- **Matriz RBAC** centralizada (ver `03_actores_y_roles.md`), declarada como constantes, aplicada por la dependencia `require_role("owner")`.
- **Fronteras duras** codificadas: recepcionista no lee historia clínica; SuperAdmin no lee
  clínica; laboratorio no ve historia clínica (RN-CMP-04, RN-EX-06).

### Aislamiento (defense in depth)
1. `tenant_id NOT NULL` en todas las tablas de negocio.
2. **RLS** de PostgreSQL con `SET LOCAL app.current_tenant`.
3. `TenantGuard` resuelve el tenant del token.
4. **Tests cross-tenant obligatorios** para todo endpoint (RN-TEN-02). `cross-tenant leak = 0`.

### Datos sensibles
- **Cifrado en reposo**: historia clínica, odontograma, contenido de `clinical_record`
  (RN-CMP-01). Clave por tenant derivada de clave maestra en KMS.
- **Cifrado específico** para: `clave_pem` de certificados fiscales, `access_token` WSAA,
  contenido clínico.
- **En tránsito**: TLS 1.3 a todos los servicios; mTLS a ARCA si aplica.
- **Logs sanitizados**: un test automatizado falla el build si un dato clínico o una clave
  aparece en un log (RN-CMP-08). No es una convención, es un test.

### Validación de input
- **Pydantic v2 en el borde**: cada DTO de entrada se valida con el schema Pydantic antes de tocar
  la lógica. Un DTO no validado = rejection temprano con 422. El schema genera el OpenAPI que
  consume el frontend.
- **Allowlist** para campos actualizables (nunca `UPDATE` con el body entero).
- **Sanitización de strings** en contenido clínico (no se interpreta HTML; se escapa al renderizar).

### Secrets management
- **Nunca en el repo.** Secretos en AWS Secrets Manager / GCP Secret Manager.
- **Rotación**: las claves de cifrado de datos de tenants se pueden re-cifrar (key rotation)
  sin downtime: se soporta `key_version` en los datos cifrados.
- **`.env` local** solo en desarrollo, con `.env.example` documentado.

### Rate limiting
- Global por IP (`slowapi` / `limits`, backend Redis).
- **Endpoint stricter**: login, OTP, reserva pública, portal del paciente.
- **API keys de tenant** con su propio budget (RN-EX-02).

### Cabeceras de seguridad
CSP, HSTS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` en app web.
Cookies: `HttpOnly`, `Secure`, `SameSite=Lax`.

## Variables de entorno

| Variable | Descripción | Ejemplo | Sensible |
|----------|-------------|---------|----------|
| `ENVIRONMENT` | Entorno | `production` | N |
| `DATABASE_URL` | Conexión a PostgreSQL | `postgresql://user:pass@host:5432/db` | **Y** |
| `DIRECT_URL` | Conexión directa (para migraciones, sin pooler) | `postgresql://...` | **Y** |
| `REDIS_URL` | Conexión a Redis (colas, cache, locks, rate limit) | `redis://host:6379` | **Y** |
| `SESSION_SECRET` | Firma de cookies de sesión | `random-64-bytes` | **Y** |
| `JWT_REFRESH_SECRET` | Firma del refresh token | `random-64-bytes` | **Y** |
| `KMS_MASTER_KEY_ID` | Clave maestra en KMS para cifrar datos de tenants | `arn:aws:kms:...` | **Y** |
| `ARCA_WSDL_PROD_URL` | WSDL de producción de ARCA (FE) | `https://wsaa.afip...` | N |
| `ARCA_WSDL_TEST_URL` | WSDL de homologación de ARCA | `https://wsaahomo...` | N |
| `ARCA_CERT_STORE_PASSPHRASE` | Passphrase del keystore de certificados de ARCA | `secret` | **Y** |
| `WHATSAPP_API_TOKEN` | Token de la app de WhatsApp Cloud | `EAAG...` | **Y** |
| `WHATSAPP_VERIFY_TOKEN` | Token de verificación del webhook | `token` | **Y** |
| `WHATSAPP_APP_SECRET` | Secreto de la app de Meta (para firmar webhooks) | `secret` | **Y** |
| `EMAIL_PROVIDER_API_KEY` | API key del proveedor de email | `pk_...` | **Y** |
| `S3_ENDPOINT` / `S3_BUCKET` | Object storage para PDFs, copias, exportaciones | `s3://bucket` | N |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Credenciales de storage | — | **Y** |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Endpoint de OpenTelemetry | `http://otel:4318` | N |
| `SENTRY_DSN` | DSN de Sentry | `https://...` | **Y** |
| `SIGNING_PROVIDER_URL` / `_KEY` | Proveedor de firma digital (v0.2) | — | **Y** |
| `DEFAULT_TENANT_TIMEZONE` | Timezone por defecto | `America/Argentina/Buenos_Aires` | N |
| `APPLY_TO_ALL_ORIGINS` | Orígenes permitidos (CORS) | `https://app.com` | N |

> `.env.example` documenta todas. Ningún valor real se commitea. En producción, todas se
> inyectan desde el secret manager; la app **falla al arrancar** si falta una requerida
> (validación de config al boot, no en runtime).

## Estrategia de despliegue y pruebas

| Aspecto | Decisión |
|---------|----------|
| **Entornos** | local (docker-compose) · staging (homologación ARCA) · producción |
| **ARCA en staging** | Se usa **homologación** de ARCA, nunca producción. La emisión real solo en prod. |
| **CI** | ruff (lint) → mypy (typecheck) / tsc (front) → unit (pytest, Vitest) → integration (Testcontainers Postgres+Redis) → e2e (Playwright) → build |
| **Tests cross-tenant** | **Gate obligatorio**: sin test de aislamiento, no mergea (RN-TEN-02). |
| **Migraciones** | Alembic (SQLAlchemy), versionadas, con rollback documentado. RLS se aplica post-migration (script). |
| **Despliegue API** | ECS/Fargate o Cloud Run (stateless). |
| **Despliegue worker** | Mismo artefacto, entrypoint Celery distinto; escala por profundidad de cola. |
| **Monitoring** | Trazas OpenTelemetry por tenant; alertas por tasa de rechazo ARCA, latencia de cola, errores de WSAA. |
| **Backups** | PITR de PostgreSQL; bucket S3 con versionado y lifecycle. Restauración **probada** trimestralmente. |
