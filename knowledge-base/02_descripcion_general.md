# Descripción General

## Stack tecnológico

**Decisión DD-04 — TypeScript end-to-end.** Un lenguaje, un repo, frontera de autorización
multi-tenant explícita en un solo lugar, y equipo contratable en Argentina.

| Capa | Tecnología | Versión mínima | Justificación |
|------|-----------|----------------|---------------|
| Lenguaje | TypeScript | 5.6+ | strict mode obligatorio, sin `any` en dominio |
| Runtime | Node.js | 22 LTS | LTS, soporte native de crypto para X.509 |
| Frontend | Next.js (App Router) | 15 | SSR para el portal del paciente; RSC para la UI interna |
| UI | Tailwind CSS + shadcn/ui | 4 / latest | accesible por defecto, sin lock-in visual |
| Formularios | React Hook Form + Zod | latest | **el mismo esquema Zod valida en frontend y backend** |
| Backend | NestJS | 11 | DI nativa, guards para RBAC, integración con `@nestjs/bullmq` |
| ORM | Prisma | 6 | migraciones versionadas + tipos de dominio |
| Base de datos | PostgreSQL | 16 | RLS nativo (aislamiento), JSONB para payloads ARCA |
| Colas / cache | Redis + BullMQ | 7 / 5 | jobs de ARCA, WhatsApp, notifications, idempotencia |
| Object storage | S3-compatible | — | radiografías (futuro), PDFs firmados, copias autenticadas |
| XML | `fast-xml-parser` + esquemas XSD ARCA | latest | serializar/validar contra los WSDL oficiales |
| Crypto | `node-forge` / `x509.js` | latest | **certificados X.509 por tenant**, firma, lectura de CSR |
| PDF | Playwright + PDFKit | latest | comprobantes, copias autenticadas, contratos |
| Auth | Sesión httpOnly + refresh rotativo | — | no JWT en `localStorage` (XSS) — ver DD-10 |
| Observabilidad | OpenTelemetry + Sentry | latest | trazas por tenant, errores con contexto fiscal |
| Tests | Vitest + Testcontainers + Playwright | latest | Postgres real en tests, no mocks de DB |

### Lenguajes fuera del stack

- **Python**: no. El ecosistema de IA es mejor, pero la IA se consume por HTTP como servicio
  externo; no justifica un segundo lenguaje en el codebase.
- **PHP**: no, el mercado de developers ARG lo cubre igual, pero no aporta nada al problema.

## Arquitectura general

Monorepo con 3 paquetes + 1 infra. Despliegue: **AWS o GCP, no on-prem** (DD-05).

```
┌──────────────────────────────────────────────────────────────────────┐
│  CLIENTES                                                            │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Next.js UI │  │ Next.js UI   │  │ Portal       │  │ WhatsApp   │ │
│  │ interna    │  │ (kiosk)      │  │ paciente     │  │ webhook    │ │
│  └─────┬──────┘  └──────────────┘  └──────┬───────┘  └─────┬──────┘ │
└────────┼───────────────────────────────────┼────────────────┼────────┘
         │                                   │                │
         └──────────────┬────────────────────┴────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│  API — NestJS (stateless, N réplicas)                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │ Guards   │ │ Guards   │ │ Pipes        │ │ Controllers        │ │
│  │ JWT/ses. │ │ Tenant   │ │ Zod          │ │ (REST /api/v1)     │ │
│  └──────────┘ └──────────┘ └──────────────┘ └────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Aplicación / dominio: Agenda, Clínica, Caja, Facturación     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Infra: Prisma repos, Outbox publisher, Integraciones         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└───────┬────────────────────┬─────────────────────┬──────────────────┘
        ▼                    ▼                     ▼
┌───────────────┐  ┌──────────────────┐  ┌───────────────────────────┐
│ PostgreSQL 16 │  │ Redis + BullMQ   │  │ S3 (PDFs, copias, RX)    │
│ RLS por tenant│  │ jobs diferidos   │  │ lifecycle + versionado   │
└───────────────┘  └──────────────────┘  └───────────────────────────┘
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │ ARCA         │ │ WhatsApp     │ │ Email        │
      │ WSAA + FE    │ │ Cloud API    │ │ transaccional│
      │ X.509/tenant │ │ plantillas   │ │ + bounce     │
      └──────────────┘ └──────────────┘ └──────────────┘
```

### Decisiones estructurales de alto nivel

1. **Aislamiento por tenant: RLS de PostgreSQL + `tenant_id` explícito.**
   Cada sesión de DB se abre con `SET LOCAL app.current_tenant`. La RLS es la segunda
   barrera; la aplicación nunca puede consultar datos de otro tenant ni por error.
   Alternativa descartada: schema-por-tenant (migrar N veces, complexity operativa).

2. **Facturación ARCA es asíncrona con Outbox, nunca síncrona.**
   La UI confirma el turno en <400ms y encola la emisión. El comprobante va de
   `BORRADOR → PENDIENTE → EMITIDO` o `→ RECHAZADO`. El paciente nunca espera a ARCA.
   → [`11_facturacion_arca.md`](11_facturacion_arca.md)

3. **Emisión bajo demanda del paciente, no de ARCA.**
   Nunca "el sistema emite". El comprobante representa una operación real del tenant,
   con su certificado. El token WSAA se cachea con expiración conocida (ver DD-06).

4. **La historia clínica es append-only.**
   Las correcciones son nuevos eventos con `supersedes_id`. No hay `UPDATE` ni `DELETE`
   sobre datos clínicos (RN-CMP-02).

5. **Comunicación es outbox también.**
   WhatsApp y email se encolan; los errores de un canal no bloquean la transacción clínica.

## Integraciones externas

| Servicio | Propósito | Tipo | Criticidad | Estado |
|---------|-----------|------|-----------|--------|
| **ARCA** (ex AFIP) — WSAA | Autenticación de la aplicación, token de acceso | SOAP/XML | **Bloqueante** | v0.1 |
| **ARCA** — FE (facturación electrónica) | Emisión de comprobantes A y B, consulta de estado | SOAP/XML | **Bloqueante** | v0.1 |
| **WhatsApp Business Cloud API** | Confirmación de turnos, recordatorios 24h/2h, recuperación de cancelaciones | REST + webhook (Meta) | Alta | v0.1 |
| **Email transaccional** | Fallback de confirmación, copias autenticadas, invoices | SMTP/API | Alta | v0.1 |
| **Object storage S3** | PDFs firmados, copias autenticadas, exportaciones, (futuro) radiografías | REST + SDK | Alta | v0.1 |
| **Mercado Pago** | Cobro de suscripción del SaaS (NO facturación al paciente) | REST | Media | v0.2 — ver SU-06 |
| **OpenTelemetry / Sentry** | Trazas y errores con contexto de tenant | OTLP | Media | v0.1 |
| **Proveedor de firma digital** | Firma de consentimientos (firma de PDF / UAI) | API | Baja | v0.2 |
| **Bioimagen / PACS** | Radiografías | DICOM | — | **Fuera de alcance v0.1** |

### Proveedor de email

**No elegido.** Debe soportar bounce handling y buena deliverability en Argentina. Candidato
default: Postmark. Registrado en [`10_preguntas_abiertas.md`](10_preguntas_abiertas.md) — PQ-08.

## API REST (superficie)

Base: `/api/v1`. Todas las rutas son tenant-scoped por el `TenantGuard`; el `tenant_id` se
resuelve del token de sesión, **nunca del body de la petición**.

### Recursos

| Grupo | Endpoints | Notas |
|-------|-----------|-------|
| **Auth** | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | refresh rotativo |
| **Onboarding** | `POST /onboarding/tenant`, `POST /onboarding/fiscal/*`, `POST /onboarding/certificate` | ver flujo 1 |
| **Agenda** | `GET/POST /appointments`, `PATCH /appointments/:id`, `POST /appointments/:id/reschedule`, `POST /appointments/:id/cancel`, `POST /appointments/:id/checkin`, `POST /appointments/:id/complete` | bloquea por sillón |
| **Disponibilidad** | `GET /availability?professionalId&from&to&chairId` | cálculo de huecos, excluye buffers |
| **Sillones** | `GET/POST /chairs`, `PATCH /chairs/:id`, `GET /chairs/:id/utilization` | **unidad de capacidad** |
| **Profesionales** | `GET/POST /professionals`, `PATCH /professionals/:id`, `POST /professionals/:id/schedule` | |
| **Pacientes** | `GET/POST /patients`, `GET /patients/:id`, `PATCH /patients/:id`, `GET /patients/:id/timeline` | timeline auditada |
| **Odontograma** | `GET /patients/:id/chart`, `POST /patients/:id/chart/entries`, `POST /patients/:id/chart/amalgamate` | versionado |
| **Historia clínica** | `GET /patients/:id/records`, `POST /patients/:id/records`, `GET /records/:id/copy` | append-only |
| **Consentimientos** | `GET /consents`, `POST /consents/:templateId/sign`, `GET /consents/:id/evidence` | |
| **Caja** | `POST /cash-sessions`, `POST /cash-sessions/:id/movements`, `POST /cash-sessions/:id/close`, `GET /cash-sessions/:id/reconciliation` | arqueo |
| **Facturación** | `POST /invoices`, `GET /invoices/:id`, `GET /invoices/:id/xml`, `POST /invoices/:id/retry`, `POST /invoices/:id/cancel`, `GET /invoices/:id/status` | asíncrono |
| **Liquidaciones** | `GET /settlements?professionalId&period`, `POST /settlements/:id/approve`, `POST /settlements/:id/pay` | |
| **Obras sociales** | — | **fuera de alcance v0.1** (DD-08) |
| **WhatsApp** | `POST /comms/messages`, `POST /comms/templates`, `GET /webhooks/whatsapp` | webhook público |
| **Migración** | `POST /migrations/upload`, `GET /migrations/:id/report`, `POST /migrations/:id/commit` | con dedupe |
| **Cumplimiento AAIP** | `POST /compliance/access-requests`, `GET /compliance/access-requests/:id`, `POST /compliance/audit-log` | flujo de datos personales |
| **Reportes** | `GET /reports/revenue`, `GET /reports/professional-utilization`, `GET /reports/chair-utilization`, `GET /reports/no-shows` | |

### Webhooks entrantes (públicos, autenticados por firma del proveedor)

| Ruta | Proveedor | Autenticación |
|------|-----------|---------------|
| `POST /webhooks/whatsapp` | Meta | Verificación de `X-Hub-Signature-256` |
| `POST /webhooks/arca/callbacks` | ARCA (si aplica) | mTLS / token |
