# Flujos Principales

Cada flujo se documenta extremo a extremo, con casos de error. El orden de los flujos es el
orden de los vertical slices del MVP.

---

## Flujo 1: Alta de clínica con habilitación fiscal

**Disparador**: el owner se registra en el portal público.
**Actor**: Owner (clínica) · Soporte (nosotros, solo si el owner lo pide)

Este es el flujo más sensible del onboarding: si termina mal, la clínica no puede facturar y
el tiempo-to-first-emitido se destroys.

```
Owner            React/Vite     API           PostgreSQL     ARCA(WSAA)
  |                |             |                |              |
  |--registro---->|             |                |              |
  |                |--POST /onboarding/tenant------->|           |
  |                |             |--validar CUIT-->|           |
  |                |             |--INSERT tenant, user, membership---->|
  |                |<--201 tenant + slug-----------|              |
  |                |             |                |              |
  |--completar perfil fiscal (condicion IVA, tipo comprobante)--->  |
  |                |--POST /onboarding/fiscal----->|              |
  |                |             |--INSERT fiscal_profile--->|    |
  |                |             |                |              |
  |--subir .pfx + clave-------------------------->|              |
  |                |--POST /onboarding/certificate>|              |
  |                |             |--parse X.509, cifrar en reposo|  |
  |                |             |--validar CN/CUIT == tenant-->|   |
  |                |             |--INSERT fiscal_certificate->|  |
  |                |<--CN, serial, vencimiento-----|              |
  |                |             |                |              |
  |--verificar token de facturación----------------->|              |
  |                |--POST /fiscal/verify-token---->|              |
  |                |             |--INSERT arca_token_cache->|--WSAA login-->|
  |                |             |                |<--access_token + expires--|
  |                |<--OK: emitir en X min---------|              |
  |                |             |                |              |
  |--configurar agenda (sillones, profesionales, horarios)-------->|
  |--primer turno reservado: TIME-TO-FIRST-TURNO < 15 min-------->|
  |--primer comprobante emitido: TIME-TO-FIRST-EMITIDO < 30 min-->|
```

**Pasos clave**:
1. Registro valida CUIT (RN-TEN-01) y crea tenant + owner + membership en **una transacción**.
2. El perfil fiscal determina el tipo de comprobante por defecto.
3. El certificado se parsea, se valida que el CUIT del certificado coincida con el del tenant,
   y **se cifra en reposo**. La clave privada nunca toca un log (RN-CMP-08).
4. La verificación WSAA es una **llamada real** a ARCA: prueba que el certificado y la clave
   sirven, y cachea el token con su expiración (RN-ARCA-04).
5. Configuración de sillones y horarios.

**Casos de error**:
- CUIT inválido → error de validación en el paso 1, no se crea nada.
- Certificado con CUIT distinto al tenant → **rechazo en el paso 3** con mensaje explícito.
- Certificado vencido → se sube pero se marca `vencido`; el sistema no emite (RN-ARCA-10).
- WSAA falla por clave incorrecta → distinguir "clave mal" de "certificado mal" de "ARCA caído".
  Si ARCA está caído, el flujo **no se bloquea**: se permite seguir configurando y reintentar
  la verificación después.
- Si el owner abandona a mitad → el tenant queda en `trial`; sus jobs de facturación están
  pausados; los datos se conservan si vuelve.

---

## Flujo 2: Reservar turno (recepción)

**Disparador**: el recepcionista busca un horario.
**Actor**: Recepcionista

```
Recepcionista     React/Vite      API              PostgreSQL
   |                |              |                   |
   |--GET /availability?prof&from&to&chair----------->|
   |                |              |--leer availability_rule|
   |                |              |--excluir turnos existentes (GIST)|
   |                |              |--calcular slots + buffers--->|
   |                |<--slots libres------------------|
   |                |              |                   |
   |--POST /appointments (patient, prof, chair, inicio, dur)--->|
   |                |              |--validar solapes (RN-AG-02)  |
   |                |              |--paciente ya agendado? (RN-AG-10)|
   |                |              |--INSERT appointment (GIST garantiza unicidad)|
   |                |              |--INSERT outbox_event (recordatorio)|
   |                |<--201 turno confirmado---------| |
   |                |              |                   |
   |--confirmación automática por cola: WhatsApp/email----> | |
```

**Pasos clave**:
1. La disponibilidad se calcula leyendo `availability_rule` y **excluyendo** los turnos que ya
   existen (por profesional y por sillón) y respetando buffers (RN-AG-03).
2. Al crear, el `INSERT` del turno es rechazado por la restricción `EXCLUDE USING gist` si hay
   solape. No es una validación de app: es la base de datos (RN-AG-02). Esto elimina el
   double-booking bajo concurrencia.
3. Se inserta un `outbox_event` que dispara el recordatorio 24h/2h y la confirmación (RN-COM-01).

**Casos de error**:
- Solape detectado en el `INSERT` → 409 con el turno que ocupa el horario, para que la UI ofrezca
  alternativas. No se pierde la reserva por una carrera.
- Paciente con turno solapado (RN-AG-10) → 409 explicando el conflicto.
- Sin `availability_rule` para ese profesional → el calendario muestra el día como bloqueado y
  sugiere configurar horarios.

---

## Flujo 3: Turno en consulta (check-in → atención → cierre)

**Disparador**: llega el paciente.
**Actor**: Recepcionista (check-in) → Profesional (atención) → Sistema (cierre)

```
Recepcionista   Odontólogo     API           PostgreSQL        Cola
   |              |            |                |               |
   |--POST /appointments/:id/checkin----->|    |               |
   |              |            |--estado='en_curso'--->|         |
   |              |            |                |               |
   |              |--autoguardado: POST /patients/:id/records-->|
   |              |            |--INSERT clinical_record (append-only, audit)|
   |              |            |--INSERT audit_log->|            |
   |              |--POST /patients/:id/chart/entries (odontograma)-->|
   |              |            |--INSERT chart_entry (append-only)---->|
   |              |            |--INSERT tooth_procedure 'realizado'-->|
   |              |            |                |               |
   |              |--POST /appointments/:id/complete------------->|
   |              |            |--estado='atendido'---->|
   |              |            |--elige emitir factura ------------> |
   |              |            |                |               |
   |              |            |        [cola → Flujo 4]         |
   |              |            |                |               |
   |<--turno cerrado, comprobante pendiente-------------------|
```

**Pasos clave**:
1. **Check-in** cambia el turno a `en_curso`. Un turno no puede pasar a `atendido` sin check-in.
2. **Autoguardado** durante la atención: cada escritura clínica crea un `clinical_record`
   append-only con autor (RN-CMP-02) y su `audit_log` (RN-CMP-03).
3. El odontograma y el periodontograma también son append-only con `supersedes_id` (RN-CLI-03).
4. **Cierre**: el turno pasa a `atendido`. Si se eligió cobrar, se encola la emisión (Flujo 4).

**Casos de error**:
- El paciente no llega → no hay check-in; a las 4h de gracia el turno pasa a `no_asistio` (RN-AG-04).
- El profesional intenta cerrar sin charting → permitido, pero queda marcado "sin odontograma"
  y aparece en el reporte de calidad de atención.
- El paciente rechaza un procedimiento que requiere consentimiento → el procedimiento queda en
  `cancelado` con motivo; no se puede marcar `realizado` (RN-CLI-06).

---

## Flujo 4: Emisión de comprobante ARCA (asíncrono)

**Disparador**: se elige cobrar al cerrar un turno, o se genera una venta desde caja.
**Actor**: Odontólogo/Recepcionista (dispara) → Worker (ejecuta)

> Detalle de ARCA, tipos de comprobante y WSAA en [`11_facturacion_arca.md`](11_facturacion_arca.md).

```
UI          API            PostgreSQL          Worker          ARCA
 |           |                |                 |              |
 |--POST /invoices (items, patient, idempotency_key)->|
 |           |                |--INSERT invoice (BORRADOR)     |
 |           |                |--INSERT outbox_event------------>|
 |<--201 { estado: PENDIENTE } (en <400ms)      |               |
 |           |                |                 |               |
 |           |                |         |--leer outbox--------------|
 |           |                |         |--invoice->PENDIENTE----> |
 |           |                |         |--obtener token WSAA------>|
 |           |                |         |<(lock Redis: un token por tenant)|
 |           |                |         |--firmar XML con X.509 del tenant-|
 |           |                |         |--enviar FE (WSFE)----------------->|
 |           |                |         |<--CAE + número-----------|
 |           |                |         |--UPDATE invoice: EMITIDO, cae, numero-|
 |           |                |         |--INSERT arca_response (request/response hash)|
 |           |                |         |               |               |
 |           |                |<--websocket/SSE: estado EMITIDO--|               |
 |<--UI muestra comprobante emitido con CAE             |               |
 |           |                |                 |               |
 |      [SI RECHAZADO]                                  |               |
 |           |                |<--UPDATE: RECHAZADO, error_code---|
 |           |                |--INSERT invoice_rejection (solución técnica)|
 |<--UI muestra acción concreta: corregir / anular / esperar------|
```

**Pasos clave**:
1. La UI **nunca** espera a ARCA. Nace `BORRADOR`, pasa a `PENDIENTE` al encolar, y el resultado
   llega por SSE/polling (RN-ARCA-03).
2. La emisión es un job con **idempotency_key**: si el worker corre dos veces (retry, dead-letter,
   re-deploy), la unicidad `unique(tenant_id, idempotency_key)` impide un segundo comprobante (RN-ARCA-02).
3. El token WSAA se obtiene una vez por tenant+servicio, cacheado con expiración y **protegido por
   un lock de Redis** para no pedirlo dos veces en paralelo (RN-ARCA-04).
4. Cada intento guarda `request_hash` y el `respuesta_xml` completo (RN-ARCA-08).

**Casos de error**:
- **Rechazo determinístico** (CUIT del receptor inexistente, comprobante con número repetido):
  NO se reintenta. Se genera `invoice_rejection` con acción sugerida (`corregir` o `anular`).
  Reintentar solo gasta cuota de ARCA (RN-ARCA-06).
- **Fallo transitorio** (timeout, 5xx, red): se reintenta con backoff exponencial, hasta N
  intentos; después queda `PENDIENTE` para intervención manual. El reintento usa la misma key.
- **Certificado vencido**: no se intenta emitir; el error es claro y accionable (RN-ARCA-10).
- **Deuda fiscal vencida del tenant**: ARCA puede impedir la emisión; se traduce a un mensaje
  accionable para el owner, no a un error técnico (RN-ARCA-06).
- El paciente fue identificado por DNI pero ARCA exige CUIT → se sugiere el tipo de comprobante
  que corresponde (B en vez de A) en `invoice_rejection.sugerencia`.

---

## Flujo 5: Copia autenticada de historia clínica (compliance)

**Disparador**: el paciente solicita su copia (portal, WhatsApp o presencial).
**Actor**: Paciente · Administración · Sistema

```
Paciente        API            PostgreSQL        S3            Cola
  |              |                |               |              |
  |--POST /compliance/access-requests (tipo=acceso, dni)-->|
  |              |                |--INSERT access_request, plazo--|
  |              |<--202: en proceso, nº de solicitud---|              |
  |              |                |               |              |
  |     [ADMIN valida identidad del solicitante]   |              |
  |--GET /patients/:id/records (solo ADMIN/billing autorizado)-->|
  |              |                |--SELECT records (append-only)->|
  |              |                |--INSERT audit_log READ------->|
  |              |                |               |              |
  |--encolar render PDF + hash de autenticidad--->|              |
  |              |                |        |--job: generar PDF con sello + hash--->|
  |              |                |        |--subir a S3 (inmutable)------------->|
  |              |                |<--UPDATE access_request: ATENDIDA, ruta copia---|
  |              |                |               |              |
  |              |                |        |--job: notificar "documento disponible"-->|
  |<--notificación con link seguro (identidad requerida para ver)->|
```

**Pasos clave**:
1. Toda solicitud se registra con DNI y fecha; se controla el plazo legal (RN-CMP-06).
2. **Se verifica la identidad del solicitante antes de entregar** (RN-AU-06) — la copia no se
   entrega solo porque alguien con el DNI la pidió.
3. La copia es un PDF legible, gratuito, con sello de autenticidad y hash (RN-CMP-06).
4. El acceso a los datos para generar la copia queda auditado (RN-CMP-03).
5. El paciente accede al link requiriendo verificación de identidad, no solo el link.

**Casos de error**:
- El solicitante no puede verificar su identidad → `access_request` queda `en_verificacion`;
  no se entrega nada. Nunca se entrega por confianza del DNI declarado.
- El paciente eliminó su ficha (`deleted_at`) → se entrega el historial completo igual (RN-EX-03).
- El PDF falla al generarse → el job reintenta; la solicitud sigue `en_proceso`; nunca se
  marca `atendida` sin copia existente.
- El plazo legal se acerca a vencer → alerta al owner para responder a tiempo (RN-CMP-06).

---

## Flujo 6: Migración desde el sistema anterior

**Disparador**: el owner sube su base al tenants.
**Actor**: Owner · Recepcionista · Sistema

```
Owner           API            PostgreSQL          Cola
  |              |                |                 |
  |--POST /migrations/upload (CSV/XLSX)-->|
  |              |                |--INSERT migration job---->|
  |              |<--202: job encolado, polling de progreso--|
  |              |                |                 |
  |              |        [worker] parsea, mapea columnas, normaliza
  |              |        [worker] detecta duplicados (DNI + nombre)
  |              |        [worker] genera reporte de preview + duplicados
  |              |                |                 |
  |              |<--GET /migrations/:id/report (duplicados a resolver)---|
  |              |                |                 |
  |--POST /migrations/:id/commit (con decisiones de dedupe)-->|
  |              |                |--importa pacientes (num HCE NO reciclable)|
  |              |                |--importa turnos históricos------>|
  |              |                |--importa odontograma si viene en la base->|
  |              |<--import completo, reporte final------------|
```

**Pasos clave**:
1. El mapeo de columnas es configurable (el sistema anterior de cada cliente tiene otro layout).
2. Se detecta duplicados por **DNI + nombre normalizado** y se deja elegir qué conservar.
   Nada se importa hasta que el owner confirma (RN-EX-02).
3. El `numero_historia_clinica` de cada paciente migrado se preserva o se reasigna de forma
   **no reciclable** (RN-CLI-01). No se recicla por el orden de importación.
4. Los turnos históricos importados no bloquean la agenda futura ni entran en las liquidaciones
   actuales (RN-CJ-04).

**Casos de error**:
- Archivo con formatos inesperados (fechas ambiguas, DNI con guiones) → el reporte de preview
  marca las filas problemáticas y el owner las corrige antes de importar. No se "limpia" a
  ciegas.
- Duplicado de número de HCE en el archivo → el sistema reasigna los clash sin reciclar los
  válidos, y lo reporta.
- Importación interrumpida → es re-ejecutable sin duplicar (idempotencia por lote).
