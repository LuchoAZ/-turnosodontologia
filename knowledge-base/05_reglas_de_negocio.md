# Reglas de Negocio

Cada regla tiene código único `RN-{DOMINIO}-{NN}` para trazabilidad desde la KB hasta el test.

| Prefijo | Dominio |
|---------|---------|
| `RN-AU` | Autenticación y acceso |
| `RN-TEN` | Tenancy y aislamiento |
| `RN-AG` | Agenda |
| `RN-CLI` | Clínica |
| `RN-ARCA` | Facturación fiscal |
| `RN-CJ` | Caja y liquidaciones |
| `RN-CMP` | Compliance |
| `RN-COM` | Comunicación |
| `RN-EX` | Excepciones globales |

---

## Dominio: Tenancy (RN-TEN)

- **RN-TEN-01** — El `cuit` de un tenant debe pasar la validación de dígito verificador módulo 11
  antes de persistirse. Un tenant sin CUIT válido no puede completar el onboarding fiscal.
  *Justificación: el CUIT es la clave de emisión ante ARCA; un CUIT inválido hace inútil toda la configuración fiscal.*

- **RN-TEN-02** — Toda tabla de negocio tiene `tenant_id NOT NULL` y Row Level Security activa.
  **Todo endpoint que toque una tabla con `tenant_id` debe tener un test que demuestre que el
  acceso cross-tenant falla.** Un endpoint sin ese test no se mergea.
  *Justificación: un solo leak cross-tenant destruye la confianza de todas las clínicas de la plataforma.*

- **RN-TEN-03** — El `tenant_id` de una operación se resuelve **exclusivamente** del token de
  sesión (membership activa). Un `tenant_id` enviado en body, query o header es ignorado.
  *Justificación: previene el acceso trivial por manipulación de request.*

- **RN-TEN-04** — Un tenant tiene **exactamente un** `owner` activo. La transferencia de
  ownership es una transacción atómica: se crea el nuevo owner y se desactiva el anterior en la
  misma transacción. No hay estado intermedio con cero owners.
  *Justificación: sin owner nadie puede administrar el tenant y el cliente queda huérfano.*

- **RN-TEN-05** — Un `user` puede tener memberships en N tenants con roles distintos. Los
  permisos se resuelven **por tenant activo**, no globalmente.
  *Justificación: un odontólogo que trabaja en dos clínicas necesita permisos diferentes en cada una.*

- **RN-TEN-06** — Un tenant en estado `suspended` no acepta escrituras ni reservas, pero sí
  permite exportar sus datos y exportar comprobantes (obligación de conservación). Sus jobs de
  ARCA se pausan, no se cancelan.

---

## Dominio: Autenticación (RN-AU)

- **RN-AU-01** — Los passwords se hashean con **Argon2id**. Argon2 o bcrypt.
  *Justificación: sin justificación de Argon2id, el más simple sigue siendo correcto.*

- **RN-AU-02** — La sesión se mantiene en cookie `httpOnly` + `Secure` + `SameSite=Lax`.
  **No hay JWT en `localStorage`** (vulnerable a XSS).

- **RN-AU-03** — El refresh token rota en cada uso. Si se reutiliza un refresh token ya
  rotado, **se revoca toda la familia de tokens** del usuario (detección de robo).
  *Justificación: patrón estándar de detección de reutilización.*

- **RN-AU-04** — MFA es **obligatorio** para los roles `owner` y `billing`.
  *Justificación: son los roles con acceso a datos financieros y a la identidad fiscal del tenant.*

- **RN-AU-05** — Tras 5 intentos fallidos de login, la cuenta entra en lockout de 15 minutos con
  backoff exponencial. Además se registra el intento en `audit_log`.

- **RN-AU-06** — El login del portal del paciente es por **OTP al teléfono** verificado, con
  vigencia de 10 minutos y máximo 5 intentos. El email **no** es factor de autenticación
  suficiente para acceder a datos de salud.
  *Justificación: la Ley 25.326 exige verificar identidad del solicitante antes de entregar datos sensibles.*

- **RN-AU-07** — El tenant activo se fija en cookie firmada por sesión. Cambiar de tenant
  requiere re-autenticación (re-emisión de sesión), no solo un header.
  *Justificación: un switch de tenant sin re-auth es un cross-tenant silencioso.*

- **RN-AU-08** — El `SuperAdmin` requiere MFA y toda su sesión tiene expiración de 4 horas
  (vs 12 h de un usuario normal) y **sesiónGrabada para acciones sensibles**.

---

## Dominio: Agenda (RN-AG)

- **RN-AG-01** — Un turno reserva **dos** recursos a la vez: un `professional` y un `chair`.
  Si falta cualquiera, el turno no se crea.
  *Justificación: en una clínica el consultorio es el recurso escaso, no el profesional.*

- **RN-AG-02** — Un profesional no puede tener dos turnos solapados, y un sillón tampoco.
  Garantizado por `EXCLUDE USING gist` sobre `tstzrange`, no por validación de aplicación.
  *Justificación: la validación en aplicación tiene race conditions bajo concurrencia; la base de datos no.*

- **RN-AG-03** — La duración del turno se calcula por tipo de práctica y **hereda del
  `availability_rule`**. Si hay `buffer_previo` o `buffer_posterior`, el turno los ocupa
  además de su propia duración.
  *Justificación: los buffers son higiene y esterilización; ignorarlos genera solapamiento real.*

- **RN-AG-04** — Un turno `pendiente` que pasa su hora de inicio sin check-in se marca
  `no_asistio` automáticamente después de **grace period de 4 horas**.
  *Justificación: el no-show no marcado ensucia la agenda y las liquidaciones.*

- **RN-AG-05** — Cancelar un turno con **menos de 12 horas** de anticipación requiere
  justificación y genera una entrada en `audit_log`.
  *Justificación: permite detectar el patrón de "cancela y no viene" para cobrar según política del consultorio.*

- **RN-AG-06** — Si el `chair.tipo = 'rx'`, y existe otro sillón activo de tipo `rx` que ya
  tenga turno en ese intervalo, la reserva se rechaza. Un equipo de RX es un recurso único.

- **RN-AG-07** — La lista de espera se ofrece al paciente **en orden de prioridad y antigüedad**,
  con una ventana de respuesta explícita (`ofrecido_hasta`). Si no responde, se ofrece al
  siguiente. La oferta no reserva el turno: se agenda cuando el paciente acepta.
  *Justificación: un "bloqueo optimista" del hueco pierde el turno si el paciente no responde.*

- **RN-AG-08** — Un turno `atendido` no puede cancelarse. Si hubo atención, se emite comprobante
  o se anula con motivo (`error de carga`, `paciente no atendido`) — la razón queda registrada.

- **RN-AG-09** — Los horarios se almacenan en `timestamptz` (UTC) y se muestran en el
  `timezone` del tenant (por defecto `America/Argentina/Buenos_Aires`). Ninguna lógica de negocio
  opera sobre strings de fecha.

- **RN-AG-10** — Un paciente no puede tener dos turnos `pendiente`/`confirmado`/
  `en_curso` solapados para el mismo `professional`.

---

## Dominio: Clínica (RN-CLI)

- **RN-CLI-01** — `numero_historia_clinica` es único por tenant y se genera de forma secuencial
  **nunca reciclable**. Un paciente dado de baja (`deleted_at`) conserva su número.
  *Justificación: el número de HCE es lo que el paciente exige ver al pedir su copia y lo que cita un profesional.*

- **RN-CLI-02** — Toda entrada de odontograma usa notación **FDI** de 2 dígitos (pieza) +
  cara. Validación strict: piezas `11`–`48` (permanente) o `51`–`85` (deciduo).
  Sistema de nomenclatura único para todo el sistema.

- **RN-CLI-03** — El odontograma es **append-only**. Una corrección crea una nueva entrada con
  `supersedes_id`. El estado actual de una pieza es el de la entrada no superseded más reciente.
  *Justificación: coherente con RN-CMP-02 y necesario para defender el charting ante un reclamo.*

- **RN-CLI-04** — Profundidad de bolsa > 5 mm en 2+ sitios de una pieza, o sangrado > 30%,
 → una `alerta_clinica` visible en la pantalla de atención. **Esto es heurística de UX, no un
  diagnóstico ni una recomendación terapéutica.**

- **RN-CLI-05** — Un procedimiento solo puede pasar a `realizado` si la pieza tiene odontograma
  en estado compatible (p.ej. no se puede marcar "obturado" sin que exista la entrada de
  odontograma o esté justificado).

- **RN-CLI-06** — Los procedimientos que requieren consentimiento informado obligatorio
  (según `consent_template.obligatorio_para`) **bloquean** el paso a `realizado` si el paciente
  no tiene el consentimiento `firmado` y vigente.

- **RN-CLI-07** — Un profesional solo puede escribir historia clínica y odontograma de turnos
  que le pertenecen (`appointment.professional_id`), salvo que tenga rol `clinical_admin` o
  `owner`.

---

## Dominio: Facturación (RN-ARCA)

> Detalle operativo completo en [`11_facturacion_arca.md`](11_facturacion_arca.md).

- **RN-ARCA-01** — Un comprobante `EMITIDO` es inmutable en sus campos fiscales. La única
  transición posible desde `EMITIDO` es `ANULADO` con motivo. No se permite volver a `PENDIENTE`.

- **RN-ARCA-02** — Cada intento de emisión lleva un `idempotency_key` (derivada del tenant +
  factura lógica + versión). Un reintento con la misma key **no** crea un segundo comprobante
  ante ARCA. La unicidad la garantiza `unique(tenant_id, idempotency_key)`.

- **RN-ARCA-03** — La emisión es **asíncrona** (Outbox → worker). La UI nunca espera la respuesta
  de ARCA. El comprobante nace `BORRADOR`, pasa a `PENDIENTE` al encolar, y termina en
  `EMITIDO` / `RECHAZADO`.

- **RN-ARCA-04** — El token WSAA se cachea por tenant+servicio y se refresca con **30 minutos de
  margen** sobre su expiración conocida. Nunca se solicita dos veces en paralelo para el mismo
  tenant (lock de Redis).

- **RN-ARCA-05** — El `total` del comprobante es siempre `subtotal + impuestos_total`, validado
  por `CHECK`. El desglose de alícuotas vive en los ítems.

- **RN-ARCA-06** — Un rechazo con **solución técnica** sugerible se traduce a una acción concreta
  en `invoice_rejection` (corregir / anular / esperar). El sistema nunca reintenta un rechazo
  determinístico (p.ej. CUIT del receptor inexistente) automáticamente: eso solo genera más
  rechazos.

- **RN-ARCA-07** — El número de comprobante (correlativo) es asignado **por ARCA al emitir**, no
  por el sistema. El sistema nunca "adivina" ni reserva correlativos: cada `numero` emitido es
  único y garantizado por `unique(tenant_id, tipo, serie, numero)`.

- **RN-ARCA-08** — Todo comprobante emitido guarda el `request_hash` del XML enviado y el
  `respuesta_xml` completo. Sin esto, una disputa fiscal es indefendible.
  *Justificación: es el único registro forense de qué se declaró ante el organismo.*

- **RN-ARCA-09** — La emisión usa el **certificado X.509 del tenant**, nunca uno del operador.
  El `SuperAdmin` no puede emitir comprobantes en nombre de un tenant ni solicitar tokens por él.

- **RN-ARCA-10** — Si la `fiscal_certificate` del tenant está vencida o por vencer (configurable,
  por defecto 30 días), el sistema **no emite** y notifica al owner. Un certificado vencido es la
  causa #1 de caída de facturación de un consultorio.

---

## Dominio: Caja y Liquidaciones (RN-CJ)

- **RN-CJ-01** — Un tenant tiene como máximo **una** `cash_session` abierta (`unique` parcial).
  Con 2 abiertas, el arqueo deja de ser confiable.

- **RN-CJ-02** — El cierre de caja calcula `saldo_final_sistema` y `diferencia` contra el
  `saldo_final_declarado`. **La diferencia no se puede editar**; se reporta. Un cierre con
  diferencia != 0 requiere nota.

- **RN-CJ-03** — Todo `cash_movement` está asociado a una `cash_session`. Un movimiento fuera de
  sesión abierta se rechaza.

- **RN-CJ-04** — El `porcentaje_aplicado` de una liquidación se **congela** al momento en que se
  calcula. Si el `professional.porcentaje_liquidacion` cambia después, las liquidaciones ya
  emitidas no se recalculan.

- **RN-CJ-05** — Una liquidación solo pasa a `aprobada` con un rol `owner` o `billing`. Una
  liquidación `aprobada` con monto distinto al calculado se rechaza (debe anularse y recalcularse).

- **RN-CJ-06** — Un comprobante `EMITIDO` con `forma_pago` de contado **debe** tener su
  `cash_movement` registrado, o queda en un estado "facturado sin caja" visible en la
  conciliación diaria.
  *Justificación: es la métrica de control interno que toda clínica necesita para cerrar el día.*

---

## Dominio: Compliance (RN-CMP)

> Detalle legal en [`12_historia_clinical_y_compliance.md`](12_historia_clinical_y_compliance.md).

- **RN-CMP-01** — Los datos de salud (historia clínica, odontograma, periodontograma) se almacenan
  **cifrados en reposo** y en tránsito. La clave de cifrado de cada tenant se deriva de una clave
  maestra en KMS.

- **RN-CMP-02** — `clinical_record` y `chart_entry` son **append-only por trigger de base de
  datos**: un `UPDATE` o `DELETE` lanza excepción. Las correcciones se modelan con
  `supersedes_id`.

- **RN-CMP-03** — `audit_log` es **append-only** por trigger: ni el `owner` ni nadie puede
  modificarlo o borrarlo. Registra lectura/escritura de historia clínica, odontograma,
  comprobantes, exportaciones y accesos de soporte.

- **RN-CMP-04** — Ningún rol interno tiene permiso de lectura de historia clínica por defecto,
  salvo los roles clínicos. **Recepcionista nunca lee historia clínica** (frontera dura).

- **RN-CMP-05** — Un consentimiento aceptado se conserva con la **versión exacta de la plantilla**
  en el momento de la firma. Si la plantilla cambia, los consentimientos firmados siguen
  apuntando a su versión original.

- **RN-CMP-06** — Toda solicitud de acceso a datos personales (`access_request`) se registra con
  solicitante, DNI y fecha. Se atiende verificando identidad del solicitante y entregando copia
  en formato legible y gratuito.

- **RN-CMP-07** — La exportación masiva de datos de un tenant (portabilidad / salida) genera un
  `audit_log` de tipo `EXPORT` con justificación y se hace en segundo plano (job), no en el request.

- **RN-CMP-08** — Los logs de aplicación **nunca** contienen datos clínicos ni el `clave_pem` de
  certificados. El sanitizado de logs es un test automatizado (no una convención).
  *Justificación: un log con datos de salud o una clave fiscal en un agregador es una fuga.*

---

## Dominio: Comunicación (RN-COM)

- **RN-COM-01** — Los mensajes de WhatsApp y email se emiten por **cola (outbox)**, nunca en el
  request. Un fallo de comunicación **no** revierte la transacción de negocio.

- **RN-COM-02** — Los mensajes a pacientes usan **plantillas** versionadas. Un mensaje crítico
  (recordatorio, confirmación, documento disponible) va por plantilla aprobada, no por texto libre
  generado en el momento.

- **RN-COM-03** — Los webhooks entrantes se **deduplican** por `(proveedor, evento_id)`.
  Reprocesar un webhook recibido no duplica sus efectos (confirmaciones, recordatorios).

- **RN-COM-04** — La firma del webhook de Meta (`X-Hub-Signature-256`) se **verifica siempre**
  antes de procesar. Un webhook sin firma válida se rechaza.

- **RN-COM-05** — El paciente puede **darse de baja de comunicaciones no esenciales** (marketing)
  sin perder las esenciales (recordatorios de turno, documentos). Requisito de consentimiento
  Ley 25.326.

- **RN-COM-06** — El número de WhatsApp del paciente se verifica antes del primer envío (opt-in
  explícito). No se envía a un número que no haya confirmado.

- **RN-COM-07** — Los recordatorios 24h y 2h se envían solo si el turno sigue en `pendiente` o
  `confirmado`. Si ya se canceló o se atiende, no se envía.

---

## Dominio: Excepciones globales (RN-EX)

- **RN-EX-01** — Ninguna operación de negocio puede ejecutarse sin un `tenant_id` válido y una
  `membership` activa associated. No hay "operaciones globales" de escritura.

- **RN-EX-02** — Toda mutación de negocio requiere un `idempotency_key` cuando sea disparada por
  un cliente externo (webhook, portal, API key) o por un reintento.

- **RN-EX-03** — **Soft delete por defecto** en entidades de negocio (`deleted_at`). Solo las
  entidades append-only de historia clínica, auditoría y solicitudes AAIP no se borran.

- **RN-EX-04** — Toda operación que envíe datos a un proveedor externo (ARCA, Meta, email) pasa
  por un job que **captura la request y la response** en `arca_response` o logs estructurados,
  para ser replayable y auditable.

- **RN-EX-05** — Un dato precargado de catálogo global (precio, concepto) que el tenant no
  overrideó se marca como "sin precio confirmado" en los flujos que implican cobro. **El sistema
  nunca cobra con un precio no confirmado por el tenant.**

- **RN-EX-06** — Ningún dato de salud de un paciente de un tenant es accesible desde otro tenant
  bajo ninguna circunstancia, **incluyendo a través del SuperAdmin o de un job de soporte**.

- **RN-EX-07** — TodaPATCH destructive sobre datos de negocio (baja de paciente, anulación de
  comprobante) exige confirmación explícita y queda en `audit_log` con `justificacion`.

- **RN-EX-08** — Los montos monotributo / "{criterio}" / IVA se calculan con aritmética decimal
  exacta (`numeric`), nunca con `float`. Redondeo bankers' explícito en el cálculo de impuestos
  para que el total cuadre con el ítem.
