# Modelo de Datos

## Dominios

| # | Dominio | Descripción | Entidades clave |
|---|---------|-------------|-----------------|
| 1 | **Tenancy** | Organizaciones aisladas, membresías, roles, scope | `tenant`, `membership`, `role`, `permission` |
| 2 | **Configuración fiscal** | Identidad fiscal del tenant ante ARCA | `fiscal_profile`, `fiscal_certificate`, `arca_token_cache` |
| 3 | **Agenda** | Turnos, disponibilidad, sillones, bloqueos | `appointment`, `availability_rule`, `chair`, `waiting_list_entry` |
| 4 | **Clínica** | Pacientes, historia clínica, odontograma, tratamientos | `patient`, `clinical_record`, `chart_entry`, `treatment_plan`, `tooth_procedure` |
| 5 | **Facturación** | Comprobantes, ítems, estados, XML, CAE | `invoice`, `invoice_item`, `arca_response`, `invoice_rejection` |
| 6 | **Caja** | Sesiones de caja, movimientos, liquidaciones | `cash_session`, `cash_movement`, `settlement`, `payout` |
| 7 | **Compliance** | Consentimientos, solicitudes AAIP, auditoría | `consent`, `consent_signature`, `access_request`, `audit_log` |
| 8 | **Comunicación** | WhatsApp, email, plantillas, hilos | `comms_thread`, `comms_message`, `comms_template`, `webhook_event` |

> **Obras sociales / nomencladores**: dominio previsto (9) pero **fuera de alcance v0.1** (DD-08).
> El esquema de precios (`price_item`) ya queda con `price_concept` genérico para no tener que
> migrar la tabla cuando entre.

## ERD

```
                        ┌──────────────────┐
                        │      tenant      │  organización aislada
                        └────────┬─────────┘
       ┌─────────────────────────┼──────────────────────────┐
       │                         │                          │
       ▼                         ▼                          ▼
┌─────────────┐        ┌───────────────────┐        ┌──────────────┐
│  membership │        │  fiscal_profile   │        │    chair     │  UNIDAD DE
└──────┬──────┘        │  fiscal_cert.     │        │  (sillón)    │  CAPACIDAD
       │               └─────────┬─────────┘        └──────┬───────┘
       ▼                         │                         │
┌─────────────┐                 ▼                         ▼
│    user     │        ┌──────────────────┐        ┌─────────────────┐
│  (global)   │        │ arca_token_cache │        │  appointment    │
└─────────────┘        └─────────────────┘        └────────┬────────┘
                                                            │
                    ┌───────────────────────────────────────┼──────────────┐
                    │                    │                  │              │
                    ▼                    ▼                  ▼              ▼
            ┌───────────────┐    ┌──────────────┐   ┌──────────────┐  ┌───────────┐
            │  professional │    │    patient   │   │cash_movement │  │ waiting_  │
            └───────┬───────┘    └──────┬───────┘   └──────┬───────┘  │list_entry │
                    │                   │                  │          └───────────┘
                    │       ┌───────────┼───────────┐      │
                    │       ▼           ▼           ▼      ▼
                    │  ┌─────────┐ ┌──────────┐ ┌────────────┐
                    │  │  chart  │ │ clinical │ │  consent   │
                    │  │ _entry  │ │ _record  │ │ +signature │
                    │  └────┬────┘ └────┬─────┘ └────────────┘
                    │       │           │ (append-only)
                    │       │ ┌─────────▼──────────┐
                    │       │ │ treatment_plan     │
                    │       │ │ tooth_procedure    │
                    │       │ └────────────────────┘
                    │       ▼
                    │  ┌──────────────────────────────────┐
                    └─►│            invoice               │
                       │  BORRADOR→PENDIENTE→EMITIDO/     │
                       │  RECHAZADO / ANULADO              │
                       └───┬──────────────┬───────────┬───┘
                           │              │           │
                    ┌──────▼─────┐  ┌─────▼──────┐ ┌──▼─────────────┐
                    │invoice_item│  │arca_       │ │invoice_        │
                    └────────────┘  │response    │ │rejection       │
                                   └────────────┘ └────────────────┘
                                   ┌──────────┐        ┌──────────────┐
                                   │ cash_    │        │  access_     │
                                   │ session  │        │  request     │
                                   └──────────┘        └──────────────┘

  Append-only, no modificables:  clinical_record · chart_entry · audit_log · access_request
  Cross-tenant prohibited:       todo lo anterior (RLS por tenant_id)
```

## Entidades

### Tenancy

#### `tenant`
- `id` (UUID, PK)
- `slug` (citext, unique) — subdominio: `{slug}.app.com`
- `nombre_comercial` (varchar 160)
- `cuit` (varchar 11, unique) — CUIT del tenant como entidad
- `timezone` (varchar 64, default `America/Argentina/Buenos_Aires`)
- `config` (JSONB) — flags de tenant, p.ej. `billing.can_read_clinical`
- `estado` (enum: `trial` | `active` | `suspended` | `closed`)
- `created_at`, `updated_at`
- **Constraints**: `cuit` debe validar dígito verificador (RN-TEN-01). `slug` no puede ser un
  `reserved_word` ni coincidir con rutas públicas.
- **Índices**: `unique(slug)`, `unique(cuit)`, `idx(estado)`

#### `user`
- `id` (UUID, PK) — **global**, no pertenece a un tenant
- `email` (citext, unique) — nullable: los pacientes pueden entrar solo por OTP/DNI
- `password_hash` (text, nullable) — Argon2id. Nullable porque paciente y lab pueden no tener password
- `telefono` (varchar 32, nullable) — normalizado a E.164
- `dni` (varchar 11, nullable)
- `nombre`, `apellido`
- `activo` (bool), `last_login_at`
- `mfa_secret` (text, nullable) — obligatorio para roles `owner` y `billing` (RN-AU-04)
- `created_at`, `updated_at`
- **Índices**: `unique(email)` (parcial, `where email is not null`), `idx(telefono)`, `idx(dni)`

#### `membership`
- `id` (UUID, PK)
- `tenant_id` (UUID, FK → tenant)
- `user_id` (UUID, FK → user)
- `rol` (enum: `owner` | `clinical_admin` | `professional` | `assistant` | `front_desk` | `billing`)
- `professional_id` (UUID, FK → professional, nullable) — **el vínculo rol ↔ profesional**
- `activo` (bool)
- **Constraints**: `unique(tenant_id, user_id, rol)`. Un tenant tiene **exactamente 1** `owner` activo.
- **Índices**: `idx(tenant_id)`, `idx(user_id)`

> `membership` es la clave de que el mismo humano opere en dos clínicas con permisos distintos.
> `membership.professional_id` es lo que hace que "soy odontólogo en la clínica A" implique que
> solo veo mis turnos en la A.

### Configuración fiscal

#### `fiscal_profile`
- `id` (UUID, PK), `tenant_id` (FK)
- `razon_social` (varchar 160)
- `cuit` (varchar 11)
- `condicion_iva` (enum: `responsable_inscripto` | `monotributo` | `monotributo_social` | `responsable_no_inscripto`)
- `tipo_comprobante_default` (enum: `A` | `B`)
- `inicio_actividades` (date, nullable)
- `ruta_fiscal` (text, nullable) — URL de la vía de/admin del tenant (documental)
- `estado_habilitacion` (enum: `no_iniciado` | `en_proceso` | `habilitado` | `rechazado` | `vencido`)
- `habilitacion_emitted_at` (date, nullable)
- **Índices**: `unique(tenant_id)`

#### `fiscal_certificate`
- `id` (UUID, PK), `tenant_id` (FK)
- `alias` (varchar 80) — p.ej. "producción"
- `tipo` (enum: `produccion` | `produccion_web_service`)
- `certificado_pem` (text) — **cifrado en reposo**
- `clave_pem` (text) — **cifrado en reposo, nunca en logs**
- `certificado_vence_en` (date)
- `serial_number` (varchar 64)
- `subject_cn` (varchar 160)
- `estado` (enum: `activo` | `vencido` | `revocado`)
- **Constraints**: no se pueden tener 2 certificados `produccion` activos para el mismo tenant.
- **Índices**: `idx(tenant_id, tipo)`, `idx(certificado_vence_en)` — para alertas de vencimiento

#### `arca_token_cache`
- `id` (UUID, PK), `tenant_id` (FK)
- `servicio` (varchar 40) — `wsfe`, `wsaa`
- `access_token` (text) — **cifrado**
- `expires_at` (timestamptz)
- `obtenido_at` (timestamptz)
- **Constraints**: `unique(tenant_id, servicio)`. Refresh con 30 min de margen.

### Agenda

#### `chair` — SILLÓN (unidad de capacidad)
- `id` (UUID, PK), `tenant_id` (FK)
- `nombre` (varchar 60) — "Sillón 1", "SillónPrincipal", "RX"
- `tipo` (enum: `consultorio` | `rx` | `cirugia` | `higiene` | `otro`)
- `activo` (bool)
- `ubicacion` (varchar 120, nullable)
- `equipamiento` (JSONB) — p.ej. `{ "intraoral_camera": true }`
- **Índices**: `unique(tenant_id, nombre)`

> **RN-AG-06**: si `tipo = 'rx'` y hay otra silla activa que también sea `rx`, se rechaza el turno.
> Esto es lo que ningún competidor modela bien según el relevamiento.

#### `professional`
- `id` (UUID, PK), `tenant_id` (FK)
- `user_id` (UUID, FK → user, nullable) — puede no tener login (p.ej. profesional externo)
- `nombre`, `apellido`
- `matricula` (varchar 32) — **única por tenant**
- `especialidad_id` (FK → specialty)
- `porcentaje_liquidacion` (numeric(5,2)) — 0–100. Se congela por liquidación (RN-CJ-04)
- `duracion_default_min` (int, default 30)
- `color_agenda` (varchar 7)
- `activo` (bool)
- **Índices**: `unique(tenant_id, matricula)`

#### `specialty`
- `id` (UUID, PK), `tenant_id` (FK nullable → `NULL` = catálogo global)
- `nombre` (varchar 80), `duracion_default_min` (int)
- **Índices**: `unique(nombre) where tenant_id is null` para el catálogo seed

#### `availability_rule`
- `id` (UUID, PK), `tenant_id` (FK)
- `professional_id` (FK, nullable → `NULL` = aplica a todos)
- `chair_id` (FK, nullable)
- `dia_semana` (smallint 0–6)
- `hora_inicio` (time), `hora_fin` (time)
- `slot_min` (int, default 30)
- `buffer_previo_min` (int, default 0), `buffer_posterior_min` (int, default 0)
- `fecha_desde` (date), `fecha_hasta` (date, nullable)
- `tipo_practica` (enum nullable) — si se define, el slot hereda su duración

#### `appointment` — TURNO
- `id` (UUID, PK), `tenant_id` (FK)
- `patient_id` (FK, nullable) — nullable = turno sin paciente identificado (placeholder)
- `professional_id` (FK)
- `chair_id` (FK)
- `inicio` (timestamptz), `fin` (timestamptz)
- `duracion_min` (int)
- `estado` (enum: `pendiente` | `confirmado` | `en_curso` | `atendido` | `cancelado` | `no_asistio` | `reprogramado`)
- `tipo_practica` (enum nullable)
- `motivo` (text)
- `origen` (enum: `recepcion` | `portal` | `whatsapp` | `api` | `importacion`)
- `creado_por` (FK → user)
- `recordatorio_24h_enviado_at`, `recordatorio_2h_enviado_at` (timestamptz, nullable)
- `cancelado_motivo` (varchar 200, nullable)
- `version` (int) — **optimistic locking** para evitar doble booking
- **Constraints**:
  - `EXCLUDE USING gist (chair_id WITH =, tstzrange(inicio, fin) WITH &&) WHERE (estado NOT IN ('cancelado','no_asistio'))` → **una silla, un turno a la vez**. Esto es la garantía dura de no double-booking.
  - Mismo `EXCLUDE` para `professional_id`.
  - `fin > inicio`
- **Índices**: `idx(tenant_id, inicio)`, `idx(patient_id, inicio)`, `idx(estado)` parcial

> La exclusión con `EXCLUDE USING gist` es el mecanismo real. El `version` es defensa
> secundaria para el caso de booking de dos sillones a la vez (que sí es válido).

#### `waiting_list_entry`
- `id` (UUID, PK), `tenant_id` (FK), `patient_id` (FK)
- `professional_id` (FK, nullable → cualquiera)
- `preferencia_ventana` (JSONB) — `{ "dias": ["lun","mar"], "rango": "manana" }`
- `prioridad` (int, default 0)
- `estado` (enum: `esperando` | `ofrecido` | `convertido` | `descartado`)
- `ofrecido_hasta` (timestamptz, nullable) — el paciente tiene ventana para aceptar
- `created_at`
- **Índices**: `idx(tenant_id, estado, prioridad desc)`

### Clínica

#### `patient`
- `id` (UUID, PK), `tenant_id` (FK)
- `user_id` (FK → user, nullable)
- `dni` (varchar 11, **nullable** — muchos pacientes no lo tienen o no lo dan)
- `nombre`, `apellido`
- `fecha_nacimiento` (date, nullable)
- `sexo` (enum nullable)
- `telefono` (varchar 32)
- `email` (citext, nullable)
- `domicilio` (JSONB, nullable)
- `obra_social_id` (FK, nullable) — **fuera de alcance v0.1**, se persiste para migración futura
- `numero_historia_clinica` (varchar 20) — **generado por el tenant**, sequential
- `alergias` (text, nullable) — texto libre visible en pantalla de atención
- `alerta_clinica` (bool, default false)
- `activo` (bool)
- `deleted_at` (timestamptz, nullable) — **soft delete** (RN-EX-03)
- `created_at`, `updated_at`
- **Índices**: `unique(tenant_id, dni) where dni is not null`, `idx(tenant_id, apellido, nombre)`,
  `idx(tenant_id, telefono)`, trigram index en `(apellido, nombre)` para búsqueda

> **RN-CLI-01**: `numero_historia_clinica` es único por tenant y **nunca se recicla**, aunque el
> paciente se dé de baja. Es el número que el paciente exige ver cuando pide su copia.

#### `clinical_record` — APPEND-ONLY
- `id` (UUID, PK), `tenant_id` (FK), `patient_id` (FK)
- `appointment_id` (FK, nullable)
- `author_user_id` (FK → user)
- `author_professional_id` (FK → professional, nullable)
- `tipo` (enum: `evolucion` | `diagnostico` | `procedimiento` | `prescripcion` | `certificado` | `nota`)
- `contenido` (text) — **cifrado en reposo**
- `adjuntos` (JSONB) — refs a S3, nunca binarios
- `supersedes_id` (FK → clinical_record, nullable) — corrección sin borrar
- `superseded_at` (timestamptz, nullable)
- `created_at` (timestamptz, **default now()**, no actualizable)
- **Constraints**: `UNIQUE (tenant_id, patient_id, created_at, id)` — ayuda al orden determinista.
- **Índices**: `idx(tenant_id, patient_id, created_at desc)`
- **NO tiene `updated_at`. NO tiene `deleted_at`.** Cualquier `UPDATE` o `DELETE` es bloqueado
  por trigger de base de datos (RN-CMP-02).

#### `chart_entry` — Odontograma (append-only)
- `id` (UUID, PK), `tenant_id` (FK), `patient_id` (FK)
- `appointment_id` (FK, nullable)
- `pieza_fdi` (varchar 3) — notación FDI: `11`–`48` permanente, `51`–`85` deciduous
- `cara` (varchar nullable) — `M`, `O`, `D`, `V`, `I`, `MO`… (composición)
- `estado` (enum: `sano` | `caries` | `obturado` | `ausente` | `corona` | `implante` | `extraccion_indicada` | `endodoncia` | `movilidad`)
- `severidad` (smallint nullable) — 1–3 para caries/movilidad
- `nota` (varchar 400, nullable)
- `supersedes_id` (FK nullable)
- `author_user_id` (FK), `created_at`
- **Índices**: `idx(tenant_id, patient_id, created_at desc)`, `idx(tenant_id, pieza_fdi)`

#### `chart_periodontal` — Periodontograma (append-only)
- `id`, `tenant_id`, `patient_id`, `appointment_id` (FK)
- `pieza_fdi` (varchar 3)
- `profundidad_vestibular` (smallint), `profundidad_lingual` (smallint) — mm
- `movilidad` (smallint nullable) — 0–3
- `sangrado` (bool), `calculo` (bool), `retraccion` (bool)
- `measurements` (JSONB) — extensibilidad para nuevos ítems del nomenclador
- `created_at`

> **RN-CLI-04**: profundidad por pieza > 5 mm en 2+ sitios o sangrado > 30% dispara
> `alerta_clinica` en el paciente. Es heurística UX, **no** es un diagnóstico.

#### `treatment_plan` / `tooth_procedure`
- `treatment_plan`: `id`, `tenant_id`, `patient_id`, `descripcion`, `estado` (`borrador`|`aprobado`|`en_curso`|`completado`|`cancelado`), `presupuestado_total`, `created_by`, `created_at`
- `tooth_procedure`: `id`, `tenant_id`, `plan_id` (FK), `pieza_fdi`, `codigo` (varchar) — referencia al nomenclador, `cara`, `estado`, `precio_unitario`, `cantidad`, `bonificacion`, `realizado_en`

### Facturación

#### `invoice` — COMPROBANTE
- `id` (UUID, PK), `tenant_id` (FK)
- `patient_id` (FK)
- `appointment_id` (FK, nullable) — el origen habitual
- `tipo_comprobante` (enum: `A` | `B`)
- `numero` (bigint, nullable) — asignado por ARCA al emitir; **NULL mientras no se emite**
- `serie` (varchar 8, nullable)
- `fecha_emision` (timestamptz, nullable)
- `fecha_pago` (date) — el plazo va acá; ARCA exige día de pago
- `dias_credito` (smallint, default 0) — 0 = contado
- `moneda_id` (FK → currency) — `ARS` en v0.1
- `cotizacion` (numeric(14,6), default 1)
- `subtotal`, `impuestos_total`, `total` (numeric(14,2))
- `estado` (enum: `BORRADOR` | `PENDIENTE` | `EMITIDO` | `RECHAZADO` | `ANULADO`)
- `cae` (varchar 20, nullable), `cae_vence_en` (date, nullable)
- `arca_response_id` (FK nullable)
- `idempotency_key` (varchar 64, **NOT NULL**) — ver RN-ARCA-02
- `motivo_anulacion` (varchar 200, nullable)
- `fecha_anulacion` (timestamptz, nullable)
- `error_code` (varchar 40, nullable), `error_message` (text, nullable)
- `created_by` (FK → user), `created_at`, `emitted_at` (nullable)
- **Constraints**:
  - `unique(tenant_id, idempotency_key)` → **idempotencia real**
  - `unique(tenant_id, tipo_comprobante, serie, numero) where numero is not null` → **el correlativo nunca se repite**
  - `CHECK (total = subtotal + impuestos_total)`
  - `CHECK (estado = 'EMITIDO' implies cae is not null and numero is not null)`
- **Índices**: `idx(tenant_id, estado)`, `idx(tenant_id, fecha_emision desc)`,
  `idx(patient_id)`, `idx(estado) where estado = 'PENDIENTE'` (cola de emisión)

> **RN-ARCA-01**: un comprobante `EMITIDO` **nunca** cambia de estado hacia atrás y sus campos
> fiscales son inmutables. La única transición desde `EMITIDO` es `ANULADO`.

#### `invoice_item`
- `id`, `tenant_id` (FK), `invoice_id` (FK)
- `orden` (smallint)
- `price_concept_id` (FK → price_concept)
- `descripcion` (varchar 300)
- `cantidad` (numeric(10,2))
- `precio_unitario` (numeric(14,4))
- `bonificacion` (numeric(14,4), default 0)
- `subtotal`, `impuestos` (numeric(14,2))
- `alicuota_impuesto` (numeric(6,3)) — configurable por tenant (IVA 21% / 10,5% / exento)
- `professional_id` (FK, nullable) — **necesario para liquidar por profesional**

> El desglose de impuestos vive en el ítem, no en el comprobante, porque el nomenclador
> odontológico tiene alícuotas distintas según la práctica. Consume el `total` de `invoice`
> (CHECK arriba) para que el cálculo sea consistente.

#### `arca_response`
- `id`, `tenant_id` (FK), `invoice_id` (FK)
- `request_hash` (varchar 128) — hash del XML enviado, para detectar reintentos idénticos
- `respuesta_xml` (text) — completo, sin filtrar
- `codigo` (varchar 20) — código de resultado ARCA
- `resultado` (varchar 40)
- `observaciones` (text, nullable)
- `http_status` (smallint)
- `created_at`

#### `invoice_rejection` — solución técnica
- `id`, `tenant_id` (FK), `invoice_id` (FK)
- `motivo` (enum: `rechazado_global` | `observaciones`)
- `codigo` (varchar 20), `detalle` (text)
- `accion` (enum: `corregir` | `anular` | `esperar` | `contactar_soporte`)
- `resuelto` (bool), `resuelto_at`
- `sugerencia` (text, nullable) — **qué hacer**: p.ej. "el receptor no está habilitado; usá tipo B"

### Caja

#### `cash_session`
- `id`, `tenant_id` (FK), `sucursal` (varchar 80, nullable)
- `abierta_por` (FK → user), `abierta_at` (timestamptz)
- `cerrada_por` (FK nullable), `cerrada_at` (timestamptz nullable)
- `saldo_inicial` (numeric(14,2)), `saldo_final_declarado` (numeric(14,2), nullable)
- `saldo_final_sistema` (numeric(14,2), nullable)
- `diferencia` (numeric(14,2), nullable) — **generado, no declarado**
- `estado` (enum: `abierta` | `cerrada`)
- **Constraints**: `unique(tenant_id) where estado = 'abierta'` — una sesión abierta por tenant

#### `cash_movement`
- `id`, `tenant_id` (FK), `cash_session_id` (FK)
- `tipo` (enum: `ingreso` | `egreso` | `traspaso`)
- `concepto` (varchar 200)
- `monto` (numeric(14,2))
- `medio_pago` (enum: `efectivo` | `tarjeta_debito` | `tarjeta_credito` | `transferencia` | `cheque` | `otro`)
- `invoice_id` (FK, nullable), `settlement_payout_id` (FK nullable)
- `patient_id` (FK nullable), `turno_id` (FK nullable)
- `registrado_por` (FK → user), `created_at`

#### `settlement` — Liquidación a profesional
- `id`, `tenant_id` (FK), `professional_id` (FK)
- `periodo_desde` (date), `periodo_hasta` (date)
- `bruto` (numeric(14,2)), `deducciones` (numeric(14,2)), `neto` (numeric(14,2))
- `porcentaje_aplicado` (numeric(5,2)) — **congelado del profesional, no recalculado** (RN-CJ-04)
- `estado` (enum: `calculada` | `aprobada` | `pagada` | `anulada`)
- `aprobada_por` (FK nullable), `aprobada_at`, `pagada_at` (nullable)
- **Constraints**: `unique(tenant_id, professional_id, periodo_desde, periodo_hasta)`
- **Índices**: `idx(tenant_id, periodo_desde)`

### Compliance

#### `consent`
- `id`, `tenant_id` (FK), `patient_id` (FK)
- `template_id` (FK → consent_template)
- `template_version` (int) — **congelado**: si cambia la plantilla, los firmados siguen apuntando a la versión vieja
- `estado` (enum: `pendiente` | `firmado` | `rechazado` | `vencido`)
- `firmado_at` (timestamptz nullable), `vence_at` (timestamptz nullable)
- `documento_ruta` (text) — PDF en S3
- **Índices**: `idx(tenant_id, patient_id, estado)`

#### `consent_template`
- `id`, `tenant_id` (FK, nullable → `NULL` = catálogo global)
- `nombre` (varchar 120), `version` (int)
- `cuerpo` (text) — con placeholders `{paciente}`, `{profesional}`, `{practica}`
- `obligatorio_para` (JSONB) — p.ej. `["extraccion","endodoncia"]`
- `activo` (bool)

#### `access_request` — Solicitud AAIP
- `id`, `tenant_id` (FK), `patient_id` (FK, nullable)
- `solicitante_nombre`, `solicitante_dni` (varchar 160, varchar 11)
- `tipo` (enum: `acceso` | `rectificacion` | `supresion` | `portabilidad`)
- `detalle` (text)
- `estado` (enum: `recibida` | `en_verificacion` | `en_proceso` | `atendida` | `denegada` | `fuera_de_plazo`)
- `recibida_at` (timestamptz), `plazo_vencimiento` (timestamptz, nullable)
- `atendida_por` (FK nullable), `atendida_at`, `respuesta_motivo` (text nullable)
- `copia_entregada_ruta` (text nullable) — PDF de la copia autenticada
- **Índices**: `idx(tenant_id, estado)`, `idx(plazo_vencimiento) where estado in (...)`

#### `audit_log` — APPEND-ONLY
- `id` (bigserial, PK)
- `tenant_id` (FK), `actor_user_id` (FK nullable), `actor_rol` (varchar)
- `recurso` (varchar 40), `recurso_id` (varchar 64)
- `patient_id` (FK nullable)
- `accion` (varchar 40) — `READ`, `CREATE`, `UPDATE`, `DELETE`, `EXPORT`, `SIGN`, `ACCESS_REQUEST`
- `campos_afectados` (text[] nullable) — para UPDATE, qué columnas
- `ip` (inet), `user_agent` (text)
- `justificacion` (text nullable) — requerida para accesos de soporte
- `created_at` (timestamptz, default now())
- **Constraints**: trigger `BEFORE UPDATE OR DELETE` que lanza excepción. Sin excepción posible.

### Comunicación

#### `comms_thread`
- `id`, `tenant_id` (FK), `patient_id` (FK)
- `canal` (enum: `whatsapp` | `email` | `sms`)
- `identificador_externo` (varchar 128) — `wa_id` de Meta, o email
- `ultimo_mensaje_at`, `estado` (enum: `abierto` | `cerrado`)

#### `comms_message`
- `id`, `tenant_id` (FK), `thread_id` (FK)
- `direccion` (enum: `outbound` | `inbound`)
- `plantilla_id` (FK nullable), `cuerpo` (text)
- `estado` (enum: `en_cola` | `enviado` | `entregado` | `leido` | `fallido`)
- `proveedor_message_id` (varchar 128, nullable)
- `error` (text nullable), `sent_at`, `delivered_at`, `read_at` (nullable)
- `appointment_id` (FK nullable)
- **Índices**: `idx(tenant_id, estado)`, `idx(proveedor_message_id)`

#### `webhook_event` — idempotencia de webhooks
- `id` (bigserial, PK)
- `proveedor` (varchar 20), `evento_id` (varchar 128)
- `payload` (JSONB), `recibido_at`
- `procesado_at` (nullable), `resultado` (text nullable)
- **Constraints**: `unique(proveedor, evento_id)` → reprocesar un webhook no duplica efectos

### Catálogos

#### `price_concept`
- `id`, `tenant_id` (FK, nullable → `NULL` = catálogo global)
- `codigo` (varchar 32), `descripcion` (varchar 300)
- `precio_default` (numeric(14,4))
- `alicuota_impuesto` (numeric(6,3))
- `activo` (bool)
- **Índices**: `unique(tenant_id, codigo)`

> `tenant_id IS NULL` = nomenclador base global (catálogo de consultas más comunes). El tenant
> puede sobreescribir precios y códigos sin tocar el global. Esto prepara la llegada de
> nomencladores de obra social sin migración de tabla.

#### `currency`
- `id`, `codigo` (varchar 3, unique), `nombre`, `simbolo`, `decimales`

## Seed data inicial

Datos mínimos para que el sistema arranque y una clínica pueda operar el mismo día del alta.

| Tabla | Contenido | Origen |
|-------|-----------|--------|
| `role` / enum | Los 7 roles internos + `patient`, `external_lab`, `accountant` | Definidos en `03_actores_y_roles.md` |
| `currency` | `ARS` (2 decimales, `$`), `USD` (2 decimales) | Hardcodeado en migración |
| `specialty` (global) |Odontología general, Endodoncia, Periodoncia, Ortodoncia, Cirugía oral, Prótesis, Odontopediatría, Higiene, Rehabilitación oral | Catálogo base |
| `price_concept` (global) | ~80 conceptos frecuentes (consulta, limpieza, extracción simple, endodoncia unirradicular, coronal,etc.) con precios de referencia en ARS | Seed + ajuste por tenant |
| `consent_template` (global) | Consentimiento de atención general, de procedimiento invasivo, de tratamiento de conducto, de extracción, de radiografía | Requiere revisión legal → ver PQ-05 |
| `comms_template` (global) | Confirmación de turno, recordatorio 24h, recordatorio 2h, cancelación, reagendado, lista de espera: hay lugar, documento disponible | Texto editable por tenant |
| `availability_rule` | Ninguna por default | El tenant la configura |
| `provincias` / `localidades` | Catálogo ARG para dirección fiscal del paciente | Seed estático |

> **RN-EX-05**: los precios seed son **de referencia** y quedan marcados como tales. El sistema
> nunca cobra con un precio que el tenant no haya confirmado. Un `price_concept` global sin
> override explícito se muestra en el picker como "sin precio definido" en el flujo real.

## Estrategia de aislamiento multi-tenant

Implementación en 4 capas, de defense-in-depth:

| Capa | Mecanismo | Qué previene |
|------|-----------|---------------|
| 1 | `tenant_id` NOT NULL en **todas** las tablas de negocio | El error de aplicación más común |
| 2 | **Row Level Security** de PostgreSQL + `SET LOCAL app.current_tenant` en cada transacción | Un `WHERE` olvidado en un query |
| 3 | dependencia `require_tenant` de FastAPI resuelve `tenant_id` del token; **nunca del body** | Manipulación del request |
| 4 | Tests automatizados que intentan leer cross-tenant y **deben fallar** | Regresión silenciosa |

> **RN-TEN-02**: los tests de aislamiento son **obligatorios** para cualquier endpoint nuevo
> que toque una tabla con `tenant_id`. Un endpoint sin test de cross-tenant no se mergea.
> Es la métrica que, si falla, mata el negocio: `cross-tenant leak = 0`.
