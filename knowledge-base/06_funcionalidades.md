# Funcionalidades

Organizadas por **épica** y **historia de usuario** (`US-NNN`). Cada US tiene criterios de
aceptación (CA) y las reglas de negocio que la gobiernan.

**Estado**: v0.1 = MVP. Las épicas marcadas `[FUERA v0.1]` están designed pero no se construyen
en el MVP (ver [`01_vision_y_objetivos.md`](01_vision_y_objetivos.md) § Fuera de alcance).

| # | Épica | US | Prioridad MVP | Riesgo |
|---|-------|----|--------------|--------|
| E1 | Tenancy y onboarding | 5 | P0 — **Slice 1** | Alto |
| E2 | Agenda por sillón | 6 | P0 — **Slice 2** | Medio |
| E3 | Reserva del paciente | 5 | P0 — **Slice 3** | Medio |
| E4 | Historia clínica y odontograma | 6 | P0 — **Slice 4** | Medio |
| E5 | Consentimientos y compliance | 4 | P0 — **Slice 5** | **Alto (legal)** |
| E6 | Caja y liquidaciones | 4 | P0 — **Slice 6** | Medio |
| E7 | Facturación ARCA | 5 | P0 — **Slice 7** | **Muy alto** |
| E8 | Comunicación multicanal | 4 | P0 — **Slice 8** | Bajo |
| E9 | Migración de datos | 3 | P1 — **Slice 9** | Medio |
| E10 | Reportes y control de gestión | 4 | P1 — **Slice 10** | Bajo |

> **Orden de slices**: cada uno es demostrable end-to-end. E1→E2 habilita el primer turno real;
> E7 (ARCA) entra tarde a propósito — es la pieza de mayor riesgo y llega con el flujo de caja
> ya validado. Ver [`07_flujos_principales.md`](07_flujos_principales.md).

---

## Épica 1: Tenancy y Onboarding

### US-001 — Crear la cuenta de la clínica
**Como** owner **quiero** registrar mi clínica con mis datos fiscales **para** empezar a operar.

**CA**:
- [ ] El flujo pide CUIT y valida dígito verificador (RN-TEN-01)
- [ ] Genera `slug` único y sugiere dominio
- [ ] Crea el tenant, el user del owner y la membership `owner` en una transacción
- [ ] Exige MFA antes de dejar avanzar (RN-AU-04)

**Reglas**: RN-TEN-01, RN-TEN-04, RN-AU-04

### US-002 — Configurar mi perfil fiscal
**Como** owner **quiero** cargar mi condición de IVA y mi tipo de comprobante **para** emitir correctamente.

**CA**:
- [ ] Lista cerrada: RI, Monotributo, Monotributo Social, Responsable No Inscripto
- [ ] Determina el tipo de comprobante por defecto (A o B) y explica por qué
- [ ] Si el tipo elegido no coincide con lo que ARCA habilitó, muestra el warning

**Reglas**: RN-ARCA-10

### US-003 — Subir mi certificado fiscal
**Como** owner **quiero** subir mi certificado X.509 de producción **para** que el sistema pueda firmar comprobantes a mi nombre.

**CA**:
- [ ] Acepta `.pfx`/`.p12` + clave, o CSR generado por el sistema
- [ ] Parsea el certificado, muestra CN, emisor, serial y **fecha de vencimiento**
- [ ] Almacena certificado y clave **cifrados**, nunca en logs (RN-CMP-08)
- [ ] Programa alerta de vencimiento (30/15/7 días)
- [ ] Valida que el CUIT del certificado coincida con el del tenant; si no, bloquea

**Reglas**: RN-ARCA-09, RN-ARCA-10, RN-CMP-01

### US-004 — Verificar mi token de facturación
**Como** owner **quiero** una prueba de que mi facturación funciona **para** no descubrir un problema el día que cobro.

**CA**:
- [ ] Ejecuta un login WSAA real contra ARCA y cachea el token
- [ ] Muestra expiración y proveedor del token
- [ ] Si falla, distingue: red / certificado inválido / clave incorrecta / ARCA caído
- [ ] Resultado queda auditado

**Reglas**: RN-ARCA-04, RN-EX-04

### US-005 — Invitar a mi equipo con el rol correcto
**Como** owner **quiero** invitar a mi personal con el rol que le corresponde **para** que vea solo lo que necesita.

**CA**:
- [ ] Envía invitación con expiración de 7 días
- [ ] Cada rol trae exactamente los permisos de la matriz de `03_actores_y_roles.md`
- [ ] Rechaza rol `owner` a un usuario que ya es owner de otro tenant si el negocio lo prohíbe (configurable)
- [ ] Al aceptar, crea la `membership`; el mismo user puede tener roles distintos en distintas clínicas

**Reglas**: RN-TEN-05, RN-AU-03

---

## Épica 2: Agenda por profesional y sillón

### US-010 — Cargar sillones como unidad de capacidad
**Como** owner **quiero** registrar mis sillones con su tipo **para** poder bloquear el equipo correcto.

**CA**:
- [ ] Campos: nombre, tipo (consultorio/rx/cirugía/higiene/otro), ubicación, equipamiento
- [ ] No permite 2 sillones `rx` con turno solapado (RN-AG-06)
- [ ] Puede desactivar un sillón sin perder su historial

**Reglas**: RN-AG-06, RN-EX-03

### US-011 — Configurar la disponibilidad de un profesional
**Como** dirección clínica **quiero** definir horarios por día con duración y buffers **para** que la agenda se arme sola.

**CA**:
- [ ] Configura día, hora inicio/fin, duración de slot, buffer previo y posterior
- [ ] Buffers ocupan tiempo real además del turno (RN-AG-03)
- [ ] Puede aplicar a un profesional o a toda la clínica
- [ ] Valida que `hora_fin > hora_inicio` y que los slots cierren exactamente en la ventana

**Reglas**: RN-AG-03

### US-012 — Agendar un turno
**Como** recepcionista **quiero** agendar un turno eligiendo profesional y sillón **para** reservar la capacidad real.

**CA**:
- [ ] El calendario muestra disponibilidad por profesional **y** por sillón
- [ ] No permite elegir un combo ya ocupado (RN-AG-02, garantizado por la BD)
- [ ] Calcula la duración según tipo de práctica
- [ ] Detecta conflicto si el paciente ya tiene un turno solapado (RN-AG-10)
- [ ] Permite turnos sin paciente identificado (placeholder)

**Reglas**: RN-AG-01, RN-AG-02, RN-AG-03, RN-AG-09, RN-AG-10

### US-013 — Ver la agenda del día por sillón
**Como** dirección clínica **quiero** ver la agenda como una grilla por sillón **para** detectar huecos y sobrecupos.

**CA**:
- [ ] Vista por columnas = sillones, filas = hora
- [ ] Resalta huecos aprovechables y sobrecupos
- [ ] Filtra por profesional y por estado
- [ ] Responsive: usable en tablet en el consultorio

**Reglas**: RN-AG-09

### US-014 — Mover o reprogramar un turno
**Como** recepcionista **quiero** reprogramar un turno **para** resolver cancelaciones sin perder el horario.

**CA**:
- [ ] Propone solo horarios válidos (recalcula disponibilidad)
- [ ] Guarda el turno original como `reprogramado` y crea el nuevo
- [ ] Notifica al paciente por el canal preferido
- [ ] Muestra el motivo del cambio en el historial del turno

**Reglas**: RN-AG-02, RN-COM-02

### US-015 — Usar la lista de espera para llenar huecos
**Como** recepcionista **quiero** que el sistema me avise a quién ofrecer un hueco liberado **para** no perder facturación.

**CA**:
- [ ] Al cancelar un turno, ofrece el hueco a la lista de espera ordenada por prioridad y antigüedad
- [ ] La oferta tiene ventana de respuesta explícita (RN-AG-07)
- [ ] Si el paciente no acepta, pasa al siguiente
- [ ] El hueco **no** queda bloqueado mientras espera respuesta

**Reglas**: RN-AG-07

---

## Épica 3: Reserva del paciente

### US-020 — Reservar sin que me llamen
**Como** paciente **quiero** reservar un turno a las 3am **para** no depender del horario del consultorio.

**CA**:
- [ ] Ve specialties, profesionales, y disponibilidad real (solo libre)
- [ ] No ve datos de otros pacientes ni información clínica
- [ ] Rate limit estricto por IP y teléfono
- [ ] Funciona en mobile

**Reglas**: RN-AU-06, RN-AG-02

### US-021 — Verificar que soy yo con un código
**Como** paciente **quiero** recibir un código por WhatsApp **para** que mis datos de salud no queden abiertos.

**CA**:
- [ ] OTP de 6 dígitos, vigencia 10 min, 5 intentos (RN-AU-06)
- [ ] Rate limit por número
- [ ] El email **no** alcanza para acceder a datos clínicos

**Reglas**: RN-AU-06, RN-CMP-01

### US-022 — Confirmar o cancelar mi turno
**Como** paciente **quiero** confirmar o cancelar desde un link **para** evitar llamado de confirmação.

**CA**:
- [ ] Link de un solo uso por turno
- [ ] Confirmar cambia el estado a `confirmado`
- [ ] Cancelar pide motivo y aplica la regla de anticipación si aplica (RN-AG-05)
- [ ] El link no expone datos clínicos

**Reglas**: RN-AG-05, RN-AG-08, RN-COM-07

### US-023 — Acceder a mi portal
**Como** paciente **quiero** ver mis turnos y mis documentos **para** tener todo en un lugar.

**CA**:
- [ ] Solo sus datos, resueltos por identidad verificada (OTP + DNI)
- [ ] Ve próximos turnos, historial, y copias de documentos que le entregamos
- [ ] Puede actualizar sus datos de contacto
- [ ] Puede ejercer baja de comunicaciones no esenciales

**Reglas**: RN-AU-06, RN-CMP-04, RN-COM-05

### US-024 — Aceptar un lugar en la lista de espera
**Como** paciente **quiero** saber cuando hay un lugar y tomarlo rápido **para** no esperar semanas.

**CA**:
- [ ] Recibe la oferta por su canal preferido
- [ ] Aceptar agenda el turno inmediatamente
- [ ] La ventana de expiración es visible

**Reglas**: RN-AG-07, RN-COM-02

---

## Épica 4: Historia clínica y Odontograma

### US-030 — Registrar la ficha del paciente
**Como** recepcionista **quiero** dar de alta un paciente con su número de historia clínica **para** que el equipo clínico lo encuentre.

**CA**:
- [ ] Genera `numero_historia_clinica` secuencial y no reciclable (RN-CLI-01)
- [ ] Detecta duplicados por DNI antes de crear
- [ ] Captura alergias y alertas clínicas de forma destacada
- [ ] **No** muestra ni permite escribir historia clínica

**Reglas**: RN-CLI-01, RN-CMP-04

### US-031 — Cargar la evolución clínica del turno
**Como** odontólogo **quiero** escribir la evolución durante la atención **para** no perder tiempo en el consultorio.

**CA**:
- [ ] Interfaz optimizada para tablet, pocos toques, sin popups
- [ ] Guarda con autoguardado; no depende de un botón "Guardar"
- [ ] Cada escritura crea un registro append-only (RN-CMP-02)
- [ ] Queda auditado con autor y hora

**Reglas**: RN-CMP-02, RN-CMP-03, RN-CLI-07

### US-032 — Registrar el odontograma
**Como** odontólogo **quiero** marcar el estado de cada pieza en nomenclatura FDI **para** tener el estado dental completo.

**CA**:
- [ ] Piezas FDI `11`–`48` y `51`–`85`, con validación estricta (RN-CLI-02)
- [ ] Registra estado y cara
- [ ] Cada cambio es una entrada nueva con `supersedes_id` (RN-CLI-03)
- [ ] El odontograma muestra el estado vigente y, opcionalmente, la evolución

**Reglas**: RN-CLI-02, RN-CLI-03

### US-033 — Cargar el periodontograma
**Como** odontólogo **quiero** registrar profundidades y sangrado por pieza **para** detectar periodontitis.

**CA**:
- [ ] Profundidades vestibular/lingual, movilidad, sangrado, cálculo, retracción
- [ ] Alerta visible si supera los umbrales de la heurística (RN-CLI-04), **explícitamente no es diagnóstico**
- [ ] Append-only

**Reglas**: RN-CLI-04, RN-CMP-02

### US-034 — Armar y ejecutar un plan de tratamiento
**Como** odontólogo **quiero** presupuestar un plan por piezas y ejecutarlo **para** ver qué falta y qué está facturado.

**CA**:
- [ ] Cada procedimiento tied a una pieza FDI
- [ ] Bloquea el paso a `realizado` si falta el consentimiento obligatorio (RN-CLI-06)
- [ ] Bloquea si no hay odontograma compatible (RN-CLI-05)
- [ ] El plan se convierte en ítems de factura

**Reglas**: RN-CLI-05, RN-CLI-06

### US-035 — Cargar un procedimiento delegable
**Como** higienista **quiero** registrar mi procedimiento con mi propio login **para** trabajar sin ocupar la cuenta del odontólogo.

**CA**:
- [ ] Puede crear entradas de odontograma y procedimientos dentro de su scope
- [ ] **No** puede finalizar un odontograma ni cerrar una evolución (RN-CLI-07)
- [ ] Todo queda con su authorship real

**Reglas**: RN-CLI-07, RN-CMP-03

---

## Épica 5: Consentimientos y Compliance

### US-040 — Firmar consentimiento informado
**Como** paciente **quiero** firmar digitalmente antes de un procedimiento **para** que quede constancia de que acepté.

**CA**:
- [ ] Plantilla versionada; se congela la versión al firmar (RN-CMP-05)
- [ ] Firma con evidencia: timestamp, IP, user agent, hash del documento
- [ ] Genera PDF archivado en S3, inmutable
- [ ] Un link público firmado permite firmar sin login

**Reglas**: RN-CMP-05, RN-EX-04

### US-041 — Entregar copia autenticada de mi historia clínica
**Como** paciente **quiero** pedir y recibir copia de mi documentación **para** llevarla a otro profesional.

**CA**:
- [ ] Paciente solicita desde el portal o por canal presencial
- [ ] Se verifica identidad antes de entregar (RN-AU-06)
- [ ] Se genera PDF legible y gratuito con sello de autenticidad y hash
- [ ] Queda registro de entrega en `audit_log`
- [ ] Cumplimiento del plazo legal de entrega — **el plazo exacto está en PQ-02, sin confirmar**

**Reglas**: RN-CMP-03, RN-CMP-06, RN-AU-06

### US-042 — Atender un requerimiento de la AAIP
**Como** owner **quiero** responder a un requerimiento de acceso a datos **para** cumplir la Ley 25.326.

**CA**:
- [ ] Registro de la solicitud con DNI del solicitante y fecha
- [ ] Flujo: recibida → en verificación → en proceso → atendida / denegada
- [ ] Controla el plazo legal (configurable; valor a confirmar)
- [ ] Entrega la copia por canal seguro
- [ ] Todo queda en `audit_log`

**Reglas**: RN-CMP-06

### US-043 — Auditar quién accedió a qué dato sensible
**Como** owner **quiero** ver quién leyó la historia clínica de un paciente **para** tener trazabilidad real.

**CA**:
- [ ] `audit_log` append-only, no editable por nadie (RN-CMP-03)
- [ ] Registra lectura, escritura, exportación y firma
- [ ] Filtra por paciente, usuario, recurso y rango de fechas
- [ ] El SuperAdmin puede auditar pero no leer la clínica (RN-CMP-04)

**Reglas**: RN-CMP-03, RN-CMP-04, RN-EX-06

---

## Épica 6: Caja y Liquidaciones

### US-050 — Abrir y cerrar la caja del día
**Como** administración **quiero** abrir caja al empezar y cerrar al terminar **para** saber si el día cuadró.

**CA**:
- [ ] Una sola sesión abierta por tenant (RN-CJ-01)
- [ ] Registra ingresos, egresos y traspasos con medio de pago
- [ ] El cierre muestra saldo sistema vs declarado y calcula la diferencia (RN-CJ-02)
- [ ] La diferencia no se puede editar; una diferencia ≠ 0 exige nota
- [ ] Al cerrar, muestra los comprobantes emitidos sin movimiento de caja (RN-CJ-06)

**Reglas**: RN-CJ-01, RN-CJ-02, RN-CJ-03, RN-CJ-06

### US-051 — Registrar el cobro en mostrador
**Como** recepcionista **quiero** registrar un cobro al patient's turno **para** cerrar la caja del día.

**CA**:
- [ ] Todo movimiento queda en una sesión abierta (RN-CJ-03)
- [ ] Se puede vincular a un comprobante y a un turno
- [ ] Permite medios de pago múltiples en una misma atención

**Reglas**: RN-CJ-03, RN-EX-05

### US-052 — Calcular la liquidación de un profesional
**Como** owner **quiero** calcular cuánto le corresponde a cada profesional del período **para** pagar sin discutir.

**CA**:
- [ ] Toma los ítems facturados del período atribuidos a ese profesional
- [ ] Congela el porcentaje aplicado al momento del cálculo (RN-CJ-04)
- [ ] Muestra el detalle ítem por ítem
- [ ] No se recalcula si el porcentaje del profesional cambia después

**Reglas**: RN-CJ-04, RN-EX-08

### US-053 — Aprobar y pagar liquidaciones
**Como** owner **quiero** aprobar y registrar el pago de una liquidación **para** tener el comprobante del pago al profesional.

**CA**:
- [ ] Solo `owner` o `billing` aprueban (RN-CJ-05)
- [ ] No se puede aprobar con monto distinto al calculado
- [ ] Registrar el pago genera un egreso en caja

**Reglas**: RN-CJ-05, RN-CJ-03

---

## Épica 7: Facturación ARCA

### US-060 — Emitir un comprobante desde la consulta
**Como** odontólogo **quiero** emitir el comprobante al terminar el turno **para** no tener que volver a cargar nada.

**CA**:
- [ ] Toma los ítems del plan de tratamiento realizado + conceptos sueltos
- [ ] Precarga datos del receptor desde la ficha del paciente
- [ ] La UI responde en < 400 ms aunque ARCA tarde (RN-ARCA-03)
- [ ] Muestra el estado en vivo: pendiente → emitido / rechazado
- [ ] Nunca emite bajo identidad del operador (RN-ARCA-09)

**Reglas**: RN-ARCA-03, RN-ARCA-09, RN-EX-05

### US-061 — Ver el resultado de la emisión
**Como** administración **quiero** ver por qué un comprobante fue rechazado **para** corregirlo y no perder la venta.

**CA**:
- [ ] Traduce el código de ARCA a una acción concreta: corregir / anular / esperar / contactar soporte (RN-ARCA-06)
- [ ] Nunca reintenta automáticamente un rechazo determinístico
- [ ] Muestra el PDF y el XML tal como se enviaron y como se recibieron (RN-ARCA-08)
- [ ] Permite reimprimir el comprobante

**Reglas**: RN-ARCA-06, RN-ARCA-08

### US-062 — Reintentar una emisión fallida
**Como** administración **quiero** reintentar una emisión que falló por un problema transitorio **para** no perder la facturación.

**CA**:
- [ ] Reintento con la **misma** `idempotency_key`: nunca genera un segundo comprobante (RN-ARCA-02)
- [ ] Solo disponible para fallas transitorias (red, timeout, 5xx de ARCA)
- [ ] Backoff exponencial automático hasta N intentos, luego requiere intervención

**Reglas**: RN-ARCA-02, RN-ARCA-03, RN-EX-02

### US-063 — Anular un comprobante
**Como** owner **quiero** anular un comprobante mal emitido **para** corregir el error.

**CA**:
- [ ] Exige motivo (RN-EX-07)
- [ ] Un turno `atendido` no se cancela; se anula el comprobante (RN-AG-08)
- [ ] Queda en `audit_log` con justificación
- [ ] Si el comprobante ya está `ANULADO`, no se anula dos veces

**Reglas**: RN-ARCA-01, RN-AG-08, RN-EX-07

### US-064 — Recibir alerta de certificado por vencer
**Como** owner **quiero** ser avisado antes de que mi certificado venza **para** no quedarme sin facturar.

**CA**:
- [ ] Alertas a 30, 15 y 7 días
- [ ] El aviso explica en un clic qué hacer para renovarlo
- [ ] Con el certificado vencido, el sistema no emite y lo dice claramente (RN-ARCA-10)

**Reglas**: RN-ARCA-10

---

## Épica 8: Comunicación Multicanal

### US-070 — Confirmar turno automáticamente
**Como** recepcionista **quiero** que el paciente confirme solo **para** reducir llamados.

**CA**:
- [ ] Envío por plantilla aprobada con link de un solo uso (RN-COM-02)
- [ ] Marca el turno `confirmado` al confirmar
- [ ] Si no responde, no reenvía en loop; escala a llamado manual

**Reglas**: RN-COM-01, RN-COM-02, RN-COM-03

### US-071 — Recordar el turno
**Como** paciente **quiero** recordatorios 24h y 2h antes **para** no llegar tarde ni perder el turno.

**CA**:
- [ ] Solo se envía si el turno sigue `pendiente`/`confirmado` (RN-COM-07)
- [ ] Respeta la baja de comunicaciones no esenciales

**Reglas**: RN-COM-01, RN-COM-05, RN-COM-07

### US-072 — Avisar que hay un documento disponible
**Como** paciente **quiero** saber que mi copia está lista **para** retirarla.

**CA**:
- [ ] Se dispara tras generar la copia autenticada
- [ ] El link no expone datos clínicos hasta que el paciente se identifica (RN-AU-06)
- [ ] Deduplicado: un mismo evento no produce dos mensajes (RN-COM-03)

**Reglas**: RN-COM-01, RN-COM-03, RN-AU-06

### US-073 — Usar WhatsApp oficial, no unofficial
**Como** owner **quiero** enviar desde el número del consultorio **para** que el paciente lo reconozca.

**CA**:
- [ ] Requiere onboarding de WhatsApp Cloud API con el número propio del tenant
- [ ] Plantillas aprobadas por el tenant (RN-COM-02)
- [ ] Firma de webhook verificada siempre (RN-COM-04)
- [ ] Webhooks deduplicados (RN-COM-03)

**Reglas**: RN-COM-02, RN-COM-03, RN-COM-04

---

## Épica 9: Migración de Datos

### US-080 — Subir mi base actual
**Como** recepcionista **quiero** subir un Excel/CSV de mi sistema anterior **para** no perder mis pacientes.

**CA**:
- [ ] Acepta CSV/XLSX con mapeo de columnas configurable
- [ ] Procesa en background con progreso visible
- [ ] Nunca bloquea la UI

**Reglas**: RN-EX-02

### US-081 — Detectar duplicados antes de importar
**Como** owner **quiero** ver los duplicados antes de confirmar **para** no ensuciar la base.

**CA**:
- [ ] Detecta por DNI + nombre normalizado
- [ ] Reporta en detalle y deja elegir qué registro conservar
- [ ] Nada se importa hasta que confirmo

**Reglas**: RN-CLI-01, RN-EX-03

### US-082 — Migrar la agenda histórica
**Como** owner **quiero** conservar el historial de turnos **para** no perder el pasado clínico.

**CA**:
- [ ] Importa turnos `atendido`/`no_asistio` como históricos, sin bloquear agenda futura
- [ ] Respeta la no reciclado del número de historia clínica (RN-CLI-01)
- [ ] Los años previos no afectan el cálculo de liquidaciones actuales

**Reglas**: RN-CLI-01, RN-CJ-04

---

## Épica 10: Reportes y Control de Gestión

### US-090 — Ver la rentabilidad del mes
**Como** owner **quiero** ver facturación, costos y utilidad **para** decidir.

**CA**:
- [ ] Facturado, cobrado, pendiente de pago, por profesional
- [ ] Exportable a XLSX
- [ ] Solo `owner` y `billing` ven lo financiero

**Reglas**: RN-COM-02

### US-091 — Ver la utilización del sillón
**Como** dirección clínica **quiero** ver cuánto se usa cada sillón **para** saber si necesito ampliar espacio.

**CA**:
- [ ] Horas ocupadas vs disponibles por sillón y por día
- [ ] Resalta el cuello de botella si hay
- [ ] **Métrica que ningún competidor expone** según el relevamiento

### US-092 — Ver la utilización del profesional
**Como** owner **quiero** ver la carga de trabajo de cada profesional **para** decidir contrataciones o turnos.

**CA**:
- [ ] Horas efectivas, Turnos y no-shows por profesional y período
- [ ] Tasa de no-show (RN-AG-04)
- [ ] Incluye profesional con horas facturadas y no facturadas

**Reglas**: RN-AG-04

### US-093 — Exportar todo lo mío y poder irme
**Como** owner **quiero** exportar mis datos completos **para** no quedar atrapado en el SaaS.

**CA**:
- [ ] Exportación asíncrona con notificación (RN-CMP-07)
- [ ] Incluye pacientes, historia clínica, turnos, comprobantes y PDFs
- [ ] Formato legible y libre, sin dependencia del sistema
- [ ] Exportación auditada con justificación

**Reglas**: RN-CMP-07, RN-EX-06

---

## Fuera de alcance v0.1 (diseñadas, no construidas)

| Capacidad | US future | Por qué fuera |
|------------|-----------|---------------|
| **Obras sociales y nomencladores** | US-100+ | DD-08. Mayor costo operativo; ~2 meses de plazo |
| **Radiología / PACS DICOM** | US-110+ | Requiere un proyecto de PACS propio |
| **Laboratorio y línea de escaneo** | US-120+ | Solo el pedido simple entra en v0.1 |
| **Hardware de consultorio** | US-130+ | Fuera por decisión de producto |
| **Tier gratis / packs de consumibles** | — | DD-09 |
| **App móvil nativa** | US-140+ | Web responsive primero |
| **Multi-país fiscal** | US-150+ | ARCA/AFIP argentino es el único esquema soportado |
| **IA clínica / análisis de RX** | US-160+ | Riesgo regulatorio CDSS; no es el eje del producto |
