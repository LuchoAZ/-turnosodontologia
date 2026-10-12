# Decisiones y Supuestos

Registro de las decisiones tomadas durante la construcción de la KB y de los supuestos que
**todavía no** están confirmados. Una decisión que no está acá no fue tomada.

## Decisiones documentadas

### DD-01 — Posicionamiento compliance-first, no features-first

**Decisión**: el diferencial del producto es la capa normativa (ARCA, obras sociales, datos de
salud), no la cantidad de features.

**Contexto**: el relevamiento de 20 competidores dio que los 20 tienen agenda con reserva
online. Competir ahí es competir por features contra players con 20 años.

**Alternativas consideradas**: (A) compliance-first, (B) volumen/free (modelo OdontoClinIA),
(C) profundidad clínica (modelo DentalSoft / Dentalink).

**Justificación**: A es el único enfoque donde el producto es difícil de copiar (conocimiento
normativo + integración real), donde el hallazgo del research se convierte en producto, y donde
los claims de los competidores (`[A]` sin evidencia técnica) son atacables. B te mete en
guerra de precio contra un free ya posicionado y contra el cero real (Excel). C es un feature
war contra los más fuertes, con riesgo regulatorio agregado (CDSS).

**Trade-offs aceptados**: ciclos de venta largos; el cliente tiene que saber lo que busca;
ARCA queda como dependencia crítica del value prop.

---

### DD-02 — Segmento: clínica PyME de 3 a 10 sillones, multiprofesional

**Decisión**: el cliente inicial es la clínica PyME multiprofesional con 3 a 10 sillones.

**Contexto**: el mercado argentino tiene tres segmentos muy distintos y no son el mismo producto.

**Alternativas consideradas**: (a) consultorio de 1–2 sillones, (b) clínica PyME 3–10
sillones multiprofesional, (c) cadenas multi-sucursal.

**Justificación**: en (b) el sillón como entidad, el periodontograma y la liquidación por
profesional **se pagan solos**. En (a) el problema real es el precio ($9k–$30k) y compites contra
Excel y sistemas gratis. En (c) compites contra Bilog con 20 años de incumbencia y contra un
requisito de control centralizado que no justifica el MVP.

**Trade-offs aceptados**: dejamos el mayor número de clientes (los consultorios chicos) para
un mercado con mejor disposición a pagar. El pricing en pesos compensa parte de eso.

---

### DD-03 — Alcance MVP: los 10 imprescindibles, sin obras sociales

**Decisión**: el MVP incluye las 10 capacidades imprescindibles. **Obras sociales queda fuera**,
explícitamente.

**Contexto**: había tres opciones de alcance; la alternativa (c) sumaba nomencladores por
convenio.

**Alternativas consideradas**: (a) los 10 tal cual, (b) 5 de 10 con compliance en fase 2,
(c) los 10 + obra social.

**Justificación**: (a) es coherente con DD-01: si el compliance entra en fase 2, no hay
diferencial. (b) reducía el riesgo de plazo pero dejaba 3 de 5 vacíos sin cubrir. (c) agregaba
~2 meses por el nomenclador, y el research muestra que **ningún competidor resuelve obra social
de punta a punta** — el hueco sigue existiendo en v0.2 sin perder nada por excluirlo ahora.

**Mitigación del riesgo de plazo**: la entrega es por **vertical slices** demostrables, no por
capas. Si hay que recortar, se recorta el último slice, no el compliance.

**Trade-offs aceptados**: ~2 meses más hasta tener el producto completo; el cliente de los
primeros meses no tiene obra social, lo cual reduce el segmento atendible en el corto plazo.

---

### DD-04 — Stack: Python (FastAPI) + React/Vite (REVISADO 2026-10-11)

**Decisión**: backend en **Python 3.12 + FastAPI** (SQLAlchemy 2.0 + Alembic, PostgreSQL 16 con RLS,
Redis 7 + Celery, Docker) y frontend en **React + TypeScript + Vite** (Tailwind + shadcn/ui). Reemplaza
la decisión original "TypeScript end-to-end" (Next.js + NestJS), revocada por el usuario el 2026-10-11.

**Contexto**: el stack nunca se deduce del discovery de producto; es decisión técnica pura. El usuario
fijó el stack nuevo el 2026-10-11 (back: Python / FastAPI / JWT / SQLAlchemy / PostgreSQL / Redis /
Docker; front: React / TypeScript / Vite).

**Alternativas consideradas**: (a) TypeScript end-to-end — **original, revocada**, (b) Python (FastAPI +
React) — **elegida**, (c) Node (NestJS + React).

**Justificación**: FastAPI es el framework async de referencia en Python con **OpenAPI automático**
(Pydantic v2): el contrato API se genera y el frontend consume tipos TypeScript derivados de ese
OpenAPI — elimina la misma clase de bugs de validación que daba el Zod compartido. Python tiene el
mejor ecosistema del proyecto para XML/XSD de ARCA (`lxml` + `xmlschema`), criptografía X.509
(`cryptography`), PDF (ReportLab/WeasyPrint) y colas async (Celery). React + Vite entrega un SPA
liviano con el ecosistema TS/Zod del lado cliente.

**Trade-offs aceptados**: dos lenguajes en el codebase (Python + TypeScript); el frontend pierde
SSR/server components (no los requiere: la UI interna es de gestión); el contrato front↔back es el
OpenAPI de FastAPI en lugar de un archivo Zod compartido.

---

### DD-05 — Nube, no on-prem

**Decisión**: despliegue en nube (AWS o GCP). **On-prem descartado.**

**Contexto**: era el supuesto implícito por privacidad de datos clínicos.

**Alternativas consideradas**: on-prem por clínica, nube pública, nube con aislamiento por tenant.

**Justificación**: el dato duro del research es **19 de 20 competidores son SaaS en nube**, y el
único local-first encontrado fue Odontoly (Mac-only). On-prem obliga a resolver instalador,
updates, backups y soporte por consultorio: un costo operativo enorme frente a un beneficio de
privacidad relativa que se resuelve con aislamiento fuerte por tenant y backups verificables.

**Trade-offs aceptados**: dependencia de un proveedor cloud; costo de infraestructura variable.

---

### DD-06 — Emisión ARCA asíncrona con Outbox

**Decisión**: la emisión de comprobantes **nunca** es síncrona con la request. Se encola.

**Contexto**: ARCA es un servicio externo que puede estar lento o caído. Un consultorio no puede
bloquearse porque ARCA no responda.

**Alternativas consideradas**: (a) síncrona en la request, (b) asíncrona con Outbox,
(c) asíncrona con cola sin Outbox.

**Justificación**: (a) mete la latencia y la disponibilidad de ARCA dentro del flujo clínico.
(b) garantiza que "si la factura se guardó, se va a emitir" porque el evento se escribe en la
**misma transacción** que la factura (Outbox). (c) tiene la ventana de pérdida entre el commit
y el publish a la cola.

**Trade-offs aceptados**: el comprobante no está listo al instante; se resuelve con estado
visible en vivo (`BORRADOR → PENDIENTE → EMITIDO/RECHAZADO`) y actualización por SSE.

---

### DD-07 — Multi-tenancy: `tenant_id` + RLS, no schema-por-tenant

**Decisión**: aislamiento por `tenant_id` explícito + Row Level Security de PostgreSQL.

**Contexto**: hay que elegir el modelo de aislamiento multi-tenant.

**Alternativas consideradas**: (a) schema por tenant, (b) row-level con RLS, (c) base por tenant.

**Justificación**: (a) implica migrar N veces y complexity operativa creciente — inviable para
equipos de 2–4 devs. (c) es caro y complica reportes agregados. (b) da aislamiento a nivel de
motor con una sola migración, y el performance aguanta para este volumen (una clínica PyME
= decenas de usuarios).

**Trade-offs aceptados**: todos los queries deben llevar `tenant_id` o confiar en la RLS (que se
activa sola al hacer `SET LOCAL app.current_tenant`). Por eso los tests cross-tenant son gate
obligatorio (RN-TEN-02).

---

### DD-08 — Obras sociales fuera del MVP

**Decisión**: nomencladores por convenio y liquidación a obras sociales **no** se construyen en v0.1.

**Contexto**: es la capability con mayor profundidad operativa del dominio odontológico.

**Justificaciones**: (1) el research muestra que **ningún competidor verificado lo resuelve de
punta a punta** — el hueco persiste más allá del MVP; (2) el nomenclador cambia por convenio y
por cada provincia, lo que implica un problema de **mantenimiento continuo**, no de desarrollo;
(3) agrega ~2 meses al camino al primer ingreso.

**Trade-offs aceptados**: el MVP atiende un subsegmento más angosto. El schema ya está
preparado (`price_concept` con `tenant_id NULL` para catálogo global) para que entrar nomencladores
no requiera migración de tabla.

---

### DD-09 — Modelo comercial: suscripción en pesos, sin packs de consumibles, sin tier gratis

**Decisión**: suscripción mensual en pesos. Sin tier gratuito. Sin venta de packs de consumibles.

**Contexto**: había que decidir modelo comercial.

**Justificaciones**: (1) el research muestra que los **packs de consumibles son de lo que más se
queja el mercado** — no es un diferenciador, es una fricción; (2) un tier gratis ya está
cubierto y bien documentado por OdontoClinIA, y entrar en esa guerra sin su base de usuarios es
perder; (3) un producto compliance-first **pide** que el cliente pague: si no paga, es porque no
va a usar la parte que justifica el precio.

**Trade-offs aceptados**: arranque más lento (sin efecto viral), y hay quelauchar el valor de
la capa normativa con un salesperson, no con un free tier.

---

### DD-10 — Auth: JWT en cookie httpOnly, no JWT en `localStorage` (REVISADO 2026-10-11)

**Decisión**: **JWT** como formato de token (access corto + refresh rotativo), servido en cookie
`httpOnly` + `Secure` + `SameSite=Lax`. El usuario fijó "JWT para autenticación" el 2026-10-11; se
mantiene el requisito de seguridad original: **el token nunca va a `localStorage`** (expuesto a XSS).

**Contexto**: había que elegir el esquema de sesión.

**Alternativas consideradas**: (a) JWT en `localStorage` — descartado, (b) sesión opaca con cookie
httpOnly — original, (c) **JWT en cookie httpOnly** — elegida.

**Justificación**: (a) expone el token a XSS — inaceptable en un sistema con datos de salud. (b) sigue
siendo válido pero no era el pedido del usuario. (c) mantiene la protección XSS de la cookie httpOnly,
respeta el formato JWT pedido y el refresh rotativo permite detectar robo de token.

**Trade-offs aceptados**: el SPA no guarda nada en localStorage; el refresh se hace con cookie
httpOnly; CSRF mitigado con `SameSite=Lax` + verificación de origen.

---

### DD-11 — WhatsApp Business Cloud API, no QR unofficial

**Decisión**: la comunicación usa la **API oficial** de WhatsApp Business (Cloud API).

**Contexto**: había que decidir cómo integrar WhatsApp.

**Alternativas consideradas**: (a) API oficial, (b) unofficial QR linking, (c) SMS.

**Justificación**: (a) es la única opción estable, con webhooks firmados y plantillas
aprobadas. (b) es frágil y se rompe con cada cambio de WhatsApp. (c) no es lo que el paciente
quiere ni lee.

**Trade-offs aceptados**: la API oficial exige onboarding por tenant (número verificado) y
plantillas pre-aprobadas por Meta, lo que agrega fricción al onboarding.

---

## Supuestos inferidos

### SU-01 — Equipo de 1 developer (VALIDADO 2026-10-09)

**Supuesto**: el equipo es de **1 developer full-stack**. Confirmado por el usuario el
2026-10-09: "Solo un dev".

**Origen**: confirmado explícitamente en sesión. Reemplaza al supuesto anterior de 2–4 devs.

**Riesgo (ya resuelto)**: con 1 dev, el alcance de los 23 changes del roadmap es inalcanzable
en el plazo. El plan se recorta a las slices que un dev full-stack pueda entregar antes del
deadline (ver SU-02).

---

### SU-02 — Deadline 2026-10-23 (VALIDADO 2026-10-09)

**Supuesto**: hay un deadline de **2 semanas a partir del 2026-10-09 → 2026-10-23**.
Confirmado por el usuario.

**Origen**: confirmado explícitamente en sesión. Reemplaza al supuesto de "sin deadline".

**Riesgo (ya resuelto)**: la priorización debe ordenarse para que algo **demostrable de punta a
punta** (vertical slice) llegue antes del deadline — con facturación como opción posterior si
el tiempo alcanza, según DD-01 (compliance-first igual aplica, pero el alcance se recorta).

---

### SU-03 — ARCA es la fuente de verdad fiscal

**Supuesto**: ARCA (ex AFIP) es la única autoridad fiscal relevante y el sistema emite contra
ella; el researchjwax no encontró evidencia de un cambio regulatorio relevante en curso.

**Origen**: research competitivo; la mayoría de los competidores integrations fiscal apuntan a
AFIP/ARCA.

**Riesgo si es falso**: si hay un cambio normativo relevante no documentado, el módulo de
facturación necesita rediseño.

**Cómo validar**: revisar la documentación oficial de ARCA vigente antes de implementar E7
(`11_facturacion_arca.md`).

---

### SU-04 — El research decompetencia es representativo

**Supuesto**: los 20 sistemas analizados son representativos del mercado argentino relevante
para el segmento elegido (clínica PyME 3–10 sillones).

**Origen**: research con 27 fuentes; cubrió players/free, paid, LatAm e internacionales.

**Riesgo si es falso**: puede haber un competidor local relevante no capturado (ej. un software
muy regional). Mitiga: el research fue exhaustivo en número de fuentes.

**Cómo validar**: entrevistas con 3–5 clínicas del segmento antes de launched comercial.

---

### SU-05 — Los precios de referencia son aceptables como seed

**Supuesto**: un catálogo base de ~80 conceptos odontológicos con precios de referencia en ARS
es un punto de partida razonable para que una clínica opere el primer día.

**Origen**: conocimiento general del dominio + precios del research.

**Riesgo si es falso**: precios mal calibrados hacen que el cliente desconfíe del sistema en
la primera semana (crítico para retención). Mitigado por RN-EX-05: el sistema marca los precios
no confirmados como "sin precio confirmado" y nunca cobra con ellos.

**Cómo validar**: cargar los precios reales de las 3 clínicas piloto antes de la primera emisión.

---

### SU-06 — Mercado Pago para el cobro de la suscripción del SaaS

**Supuesto**: el billing del SaaS (no del paciente al consultorio) se puede resolver con
Mercado Pago en v0.2.

**Origen**: es el medio de pago dominante en Argentina para SMBs.

**Riesgo si es falso**: menor — es una decisión que se puede tomar más adelante sin afectar la
KB ni la arquitectura (billing del SaaS es un módulo aparte del billing al paciente).

**Cómo validar**: elegir proveedor de billing al momento de implementar la facturación del SaaS.

---

### SU-07 — Los templates de consentimientos necesitan revisión legal

**Supuesto**: los consentimientos base que se seedearán (atención general, procedimiento
invasivo, etc.) **no** pueden escribirse solo desde el conocimiento del producto; requieren
revisión de un abogado.

**Origen**: los textos de consentimiento tienen contenido legal específico por especialidad y
jurisdicción.

**Riesgo si es falso**: un texto de consentimiento mal redactado es un problema legal directo.

**Cómo validar**: revisión legal antes de activar E5 en producción. Está registrado como PQ-05
en `10_preguntas_abiertas.md`.

---

### SU-08 — Los plazos legales del research se marcan como verificados

**Supuesto**: los plazos que el research marcó como verificados (copia autenticada, plazos de
solicitud AAIP) son correctos. Los marcados como `[A]` o `[NE]` **no** se toman como verdad.

**Origen**: research competitivo, con distinción explícita entre `[C]`, `[A]` y `[NE]`.

**Riesgo si es falso**: un plazo mal implementado puede ser un incumplimiento legal. Mitigado:
todos los plazos están parametrizados en el código, no hardcodeados, y registrados como
preguntas abiertas (PQ-02, PQ-03).

**Cómo validar**: verificación legal de los plazos antes de implementar E5.

---

### SU-09 — El research de competencia no tiene claims de ARCA verificables en la competencia

**Supuesto**: ningún competidor tiene integración de ARCA verificable públicamente, lo que
significa que nuestro sistema **no tiene una ventaja competitivevia integración fiscal probada**
sino solo la tenemos si la construimos bien.

**Origen**: research: los claims "100% integrado con AFIP" de los competidores son `[A]`
(afirmaciones comerciales) sin evidencia técnica pública.

**Riesgo si es falso**: si algún competidor tiene ARCA integrado y probado, nuestra ventaja se
reduce. Pero incluso si lo tienen, el research muestra que ninguno lo combina con la capa de
compliance completa (nomencladores + datos de salud +copy autenticada).

**Cómo validar**: preguntar a un competidor directamente (si hay acceso a demo) o buscar
documentación técnica pública de su API.
