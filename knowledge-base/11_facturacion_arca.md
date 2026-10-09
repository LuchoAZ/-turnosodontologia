# Facturación ARCA

> **Extra de dominio** — la parte de mayor riesgo técnico y regulatorio del proyecto.
> Módulo correspondiente: `apps/api/src/modules/arca` + `apps/api/src/workers/arca-*.worker.ts`.
> Épica: E7 (`06_funcionalidades.md` US-060 a US-064). Flujo: 4 (`07_flujos_principales.md`).

> ⚠️ **Advertencia de veracidad**: este documento describe el diseño técnico esperado. **Los
> detalles normativos concretos (plazos, condiciones de habilitación, tipos de comprobante,
> códigos de error) deben verificarse contra la documentación oficial vigente de ARCA antes de
> implementar.** El research los marcó como `[A]` o `[NE]` en la mayoría de los casos, y eso
> es honesto: no se halló evidencia pública verificable. Ver PQ-05, PQ-12, PQ-13.
> **Nada de este documento es asesoramiento legal.**

---

## Qué es ARCA en este contexto

ARCA (Agencia de Recaudación y Control Aduanero) es el organismo fiscal argentino (ex AFIP para
la parte fiscal). El consultorio emite **comprobantes electrónicos** a través de un web service,
usando un **certificado digital propio del contribuyente** (el tenant, no el operador del SaaS).

**Lo que hace posible este producto**: que cada clínica emita con su propio certificado. **Lo que
lo hace difícil**: que esa integración se N veces, no una — una por tenant, con altas,
vencimientos y tokens independientes.

## Componentes

### 1. `fiscal_profile` — Identidad fiscal del tenant

```
razon_social, cuit, condicion_iva, tipo_comprobante_default, inicio_actividades,
estado_habilitacion, habilitacion_date, ruta_fiscal
```

Los tipos de comprobante relevantes en v0.1:

| Tipo | Para quién | Requisito |
|------|-----------|-----------|
| **A** | Contribuyentes con capacidad fiscal probada | Habilitación específica ante el organismo |
| **B** | Operaciones con consumidores no identificados o sin capacidad | Numeración preimpresa, **menor requisito de habilitación** |
| **C** | Operaciones al exterior (exportación de servicios) | Fuera de alcance v0.1 |
| **M** | Cooperativas | Fuera de alcance v0.1 |

> **Supuesto de diseño**: el sistema soporta **A y B**. Si un paciente no puede ser identificado
> con CUIT, se emite **B** en vez de **A**. Si el CUIT del receptor no está habilitado, ARCA
> rechaza con A → el sistema sugiere cambiar a B (`invoice_rejection.sugerencia`). **Verificar
> estos requisitos contra la documentación oficial (PQ-05).**

### 2. `fiscal_certificate` — Certificado X.509 por tenant

- Un tenant tiene (al menos) **un** certificado `produccion`.
- Contiene el certificado y la clave privada, **cifrados en reposo**, nunca en logs (RN-CMP-08).
- Se parsea al subirlo: `subject_cn`, `serial_number`, `fecha_vencimiento`.
- **El CUIT del certificado debe coincidir con el del tenant**; si no, el upload se rechaza
  (paso 3 del Flujo 1). Esto evita el error más común: subir el certificado equivocado.
- Alertas de vencimiento a **30 / 15 / 7 días** (RN-ARCA-10).
- Con el certificado vencido o por vencer (configurable), el sistema **no emite** y lo dice
  con un mensaje accionable, no con un error técnico.

> **Nunca** el SuperAdmin emite con el certificado de otro, ni solicita tokens en su nombre
> (RN-ARCA-09). La identidad fiscal es del tenant, punto.

### 3. `arca_token_cache` — Token de autenticación (WSAA)

El flujo de autenticación (WSAA) entrega un **token de acceso** que se usa para las operaciones
posteriores. Tiene una **expiración conocida**.

- Se cachea por `(tenant_id, servicio)`.
- Se refresca con **30 minutos de margen** sobre la expiración (RN-ARCA-04).
- **Lock de Redis**: dos requests concurrentes al token del mismo tenant no lo piden dos veces.
- El token se guarda **cifrado**.

> **Diseño robusto a expiración**: si una emisión falla con "token expirado" (por clock skew o
> margen insuficiente), el worker **re-obtiene el token una vez y reintenta con la misma
> `idempotency_key`**. Esto es seguro porque la idempotencia garantiza que no haya doble
> emisión (RN-ARCA-02).

### 4. Emisión (FE) — Flujo asíncrono

Ya documentado en el [Flujo 4](07_flujos_principales.md#flujo-4-emisión-de-comprobante-arca-asíncrono).
Resumen de estados:

```
BORRADOR ──encolar──> PENDIENTE ──firmar+enviar──> EMITIDO    (cae, numero, fecha_emision)
                          │                              │
                          └──fallo──> RECHAZADO          └──error──> ANULADO
                                    (error_code,                (motivo)
                                     invoice_rejection)
```

### 5. `arca_response` — Registro forense

Cada intento guarda:
- `request_hash` — hash del XML enviado (detecta reintentos idénticos)
- `respuesta_xml` — la respuesta completa, sin filtrar
- `codigo`, `resultado`, `observaciones`, `http_status`

Sin esto, una disputa fiscal es indefendible (RN-ARCA-08). El comprobante que el paciente
imprime es exactamente lo que se envió y se recibió.

---

## Modelo de datos específico

### `invoice` (extracto relevante a facturación)

```
tipo_comprobante (A|B), numero, serie,          ← asignados por ARCA al emitir
fecha_emision, fecha_pago, dias_credito,
moneda_id, cotizacion,
subtotal, impuestos_total, total,               ← CHECK: total = subtotal + impuestos_total
estado (BORRADOR|PENDIENTE|EMITIDO|RECHAZADO|ANULADO),
cae, cae_vence_en,
arca_response_id,
idempotency_key,                                 ← UNIQUE(tenant_id, idempotency_key)
error_code, error_message,
motivo_anulacion, fecha_anulacion
```

**Constraints críticos**:
- `unique(tenant_id, idempotency_key)` — la idempotencia real.
- `unique(tenant_id, tipo_comprobante, serie, numero) where numero is not null` — el correlativo
  nunca se repite (RN-ARCA-07).
- `check (estado = 'EMITIDO' implies cae is not null and numero is not null)` — no se marca
  emitido sin CAE.

### `invoice_item` (extracto)

```
orden, price_concept_id, descripcion,
cantidad, precio_unitario, bonificacion,
subtotal, impuestos, alicuota_impuesto,          ← alícuota por ítem
professional_id                                   ← para liquidar por profesional
```

> El desglose de impuestos vive en el ítem, no en el comprobante, porque el nomenclador
> odontológico tiene alícuotas distintas según la práctica (RN-EX-08).

---

## Cálculo de impuestos

**Regla dura**: aritmética decimal exacta (`numeric`), nunca `float` (RN-EX-08).

```
subtotal_item   = (cantidad × precio_unitario) − bonificacion
impuestos_item  = round(subtotal_item × alicuota, 2, half-up)
total           = Σ subtotal_item
impuestos_total = Σ impuestos_item
-- CHECK: total = subtotal_total + impuestos_total
```

- **Alícuota por ítem**, no por comprobante (cada práctica puede tener distinto IVA).
- El redondeo es explícito y determinista, para que el total del comprobante siempre cuadre con
  la suma de sus ítems (CHECK de DB).
- **Pendiente de verificación**: si el consultorio necesita retenciones (IVA percibido, Ganancias)
  → PQ-13.

---

## Idempotencia (RN-ARCA-02) — el corazón de la emisión

La emisión puede ejecutarse múltiples veces por: reintento de red, re-deploy del worker,
dead-letter reprocesada, doble clic del usuario. **Nunca debe producir dos comprobantes.**

```
idempotency_key = hash(tenant_id, factura_lógica, version)
```

- Generada al crear el `invoice` (una vez).
- Reintentos **conservan** la misma key.
- `unique(tenant_id, idempotency_key)` en DB hace imposible que dos emisiones con la misma key
  persistan.
- **Antes** de enviar a ARCA, el worker verifica si ya existe un `EMITIDO` con esa key → si sí,
  es un no-op.

> **Por qué importa**: sin idempotencia, un reintento durante una caída de red puede emitir dos
> comprobantes al mismo paciente. Eso es un problema fiscal y de confianza, no un bug menor.

---

## Manejo de rechazos

La clave del módulo ARCA es **traducir el código de rechazo a una acción concreta** para que el
usuario humano sepa qué hacer (RN-ARCA-06).

| Tipo de rechazo | Ejemplo (verificar códigos exactos) | Acción sugerida |
|-----------------|--------------------------------------|-----------------|
| **Determinístico** (no reintentar) | CUIT del receptor no existe / no habilitado | `corregir` (cambiar a tipo B) o `anular` |
| **Determinístico** | Número de comprobante repetido | `contactar_soporte` (investigar estado del correlativo) |
| **Determinístico** | Comprobante con período fiscal ya cerrado | `esperar` (o `anular`, según normativa) |
| **Determinístico** | Deuda fiscal vencida del contribuyente | `contactar_soporte` (mensaje accionable al owner) |
| **Transitorio** | Timeout / 5xx / red caída | Reintento automático con backoff exponencial |
| **Transitorio** | Token expirado (clock skew) | Re-obtener token + reintentar una vez (misma key) |
| **Configuración** | Certificado vencido | `corregir` (renovar certificado) — el mensaje dice cómo |

> **Nunca reintentamos automáticamente un rechazo determinístico** (RN-ARCA-06): solo genera más
> rechazos y desgaste de cuota. El `invoice_rejection.sugerencia` traduce el código a lenguaje
> de negocio ("el paciente no está habilitado para comprobante A; usá B").

---

## Circuit breaker

Si ARCA está caído (manytimeouts consecutivos), el **circuit breaker** se abre y el worker deja
de llamar a ARCA por un período, dejando las facturas en `PENDIENTE` con un motivo. Cuando se
recupera, el circuito se cierra y las facturas pendientes se reintentan con la misma key.

Esto evita:
- Hammering a un servicio caído (que extendería la caída).
- Que los tiempos de cola del worker se llenen de facturas que van a fallar.

---

## Depuración y staging

- **Staging usa el web service de homologación** de ARCA, **nunca producción**. La emisión real
  solo ocurre en producción (ver `08_arquitectura_propuesta.md`).
- En desarrollo local, los tests de integración usan **un mock del WSDL** o el de homologación,
  nunca producción.
- La emisión real en producción requiere un certificado real y un tenant real.

---

## Checklist de implementación (E7)

- [ ] Modelar `fiscal_profile`, `fiscal_certificate`, `arca_token_cache` (04).
- [ ] Parser de X.509: validar CN, serial, vencimiento, y match con CUIT del tenant.
- [ ] Cliente WSAA con cache Redis + lock + cifrado del token.
- [ ] Cliente FE (WSFE): serializar request, firmar con X.509, parsear response.
- [ ] Traductor de errores ARCA → `invoice_rejection.sugerencia`.
- [ ] Outbox publisher + `arca-emit.worker` con idempotencia y circuit breaker.
- [ ] PDF del comprobante (CAE visible, barcode, QR) con Playwright.
- [ ] Tests: idempotencia (dos emisiones, un comprobante), rechazo determinístico (no reintenta),
      transitorio (reintenta), token expirado (re-obtiene), certificado vencido (no emite).
- [ ] Cross-tenant tests: un tenant nunca ve el comprobante de otro (RN-TEN-02).
- [ ] Alertas de vencimiento de certificado (30/15/7 días).
- [ ] Endpoint de verificación de token (US-004).

---

## Referencias (verificar vigencia)

- Documentación oficial de ARCA para servicios de facturación electrónica y WSAA.
- Los WSDL/XSD oficiales se versionan en `packages/contracts/`.
- **Todos los códigos de error y sus significados deben extraerse del WSDL/XSD oficial**, no de
  memoria. Este documento no los fija a propósito: prefiero una tabla a construir en el código
  desde el contrato oficial (una fuente única de verdad, no comentarios desactualizados).
