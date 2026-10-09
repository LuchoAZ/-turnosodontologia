# Preguntas Abiertas

Registro de lo que **no** está resuelto. Nada en la KB depende de que estas respuestas sean
correctas para *escribir* la KB, pero sí para *construir* el producto.

## Inconsistencias detectadas

### IN-01 — Recuento de competidores en el research

**Research dice**: 20 competidores, con este desglose en `discovery/discovery.md`.

**Base de conocimiento dice**: 10 funcionalidades imprescindibles como MVP (coherente).

**Impacto**: bajo. Es un tema de consistencia editorial del research, no del producto.

**Resolución propuesta**: verificar/corregir el desglose del research cuando se toque. No bloquea.

---

### IN-02 — Alcance de "compliance-first" vs. timeline real

**Documento A (01_vision) dice**: el MVP es los 10 imprescindibles con compliance incluido.

**Documento B (SU-01, SU-02) dice**: equipo de 2–4 devs sin deadline.

**Impacto**: si el equipo es de 1 persona o hay deadline, "los 10 imprescindibles" puede ser
inalcanzable. DD-03 asumía que se puede entregar por slices sin recortear el compliance.

**Resolución propuesta**: confirmar equipo y plazo antes de generar el roadmap. Si hay presión
de tiempo, reordenar slices para que E7 (facturación) llegue antes y E5 (consentimientos) se
parta en dos (firmar primero, copia autenticada después).

---

### IN-03 — "Fuera de alcance" vs. "no es el eje" en IA clínica

**Documento A (06_funcionalidades) dice**: IA clínica fuera de alcance v0.1.

**Documento B (research)** menciona IA como tendencia de los competidores premium (Dentalink).

**Impacto**: bajo. Es coherente — la IA clínica es riesgo regulatorio (CDSS) y no es el
posicionamiento (DD-01). Pero si el research de campo (PQ-11) revela que las clínicas lo piden,
hay que reevaluar.

**Resolución propuesta**: mantener fuera. Si aparece demanda, es un cambio de proyecto, no una
extensión del MVP.

---

### IN-04 — Modelo de datos soporta nomencladores pero el MVP no los construye

**Documento A (04_modelo_datos)**: `price_concept` con `tenant_id NULL` para catálogo global,
"preparado para nomencladores sin migración".

**Documento B (DD-08)**: obras sociales fuera de alcance v0.1.

**Impacto**: bajo. Es una decisión deliberada (no contradicción): el schema se preparations,
la feature no se construye. Pero el equipo no debe interpretar el schema como "ya soportamos
nomencladores".

**Resolución propuesta**: ninguna. Está correctamente documentado en DD-08.

---

### IN-05 — Research dice "WhatsApp pricing argentino sin verificar"

**Research**: no se pudo verificar el pricing de la WhatsApp Business API en Argentina.

**KB (DD-11, E8)**: asume que la API oficial es viable, sin costo asociado cuantificado.

**Impacto**: medio. Si la API oficial tiene un costo por conversación significativo, el modelo
comercial (DD-09) y el costo por usuario cambian.

**Resolución propuesta**: verificar el pricing actual de Meta para Argentina antes de lanzar.
Es un input de pricing, no un bloqueador técnico.

---

## Preguntas abiertas (priorizadas)

### Prioridad ALTA — bloquean decisiones de roadmap

| # | Pregunta | Bloquea | Decisor |
|---|----------|---------|---------|
| **PQ-01** | ¿Cuál es el tamaño real del equipo (personas, roles, skill)? ¿Hay deadline? | Todo el roadmap (`CHANGES.md`); cardinalidad de changes | Product Owner |
| **PQ-02** | ¿Cuál es el plazo legal exacto para entregar copia autenticada de historia clínica? El research lo marcó `[A]`/`[NE]`. | E5, US-041 (SLA de entrega) | Legal + Tech Lead |
| **PQ-03** | ¿Cuál es el plazo legal exacto para responder un requerimiento de acceso (Ley 25.326 / AAIP)? | E5, US-042 (control de plazo) | Legal |
| **PQ-04** | ¿Las plantillas de consentimiento base están listas o necesitan redacción legal? | E5, US-040 (no se puede lanzar sin ellas) | Legal |

### Prioridad ALTA — bloquean la implementación de facturación

| # | Pregunta | Bloquea | Decisor |
|---|----------|---------|---------|
| **PQ-05** | ¿Cuál es el proveedor y el flujo real de emisión hoy (¿ARCA? ¿otro? ¿en qué condiciones está el cliente actual)? | E7 (todo el módulo ARCA) | Product Owner + Legal |
| **PQ-06** | ¿Los certificados fiscales: el cliente los tiene listos o hay que guiarlos en el alta? | US-003 (onboarding) | Tech Lead |
| **PQ-07** | ¿Se necesita integración con un clearing o pasarela para el cobro al paciente, o el consultorio cobra en mostrador? | E6, US-051 (si hay pasarela, el flujo de caja cambia) | Product Owner |

### Prioridad MEDIA — bloquean optimizaciones, no el core

| # | Pregunta | Bloquea | Decisor |
|---|----------|---------|---------|
| **PQ-08** | ¿Qué proveedor de email transaccional se usa? (Postmark es candidato default por deliverability en AR) | E8 (fallback de confirmación) | Tech Lead |
| **PQ-09** | ¿El precio de la suscripción SaaS en pesos — qué número? (DD-09 solo define el modelo, no el monto) | Launch comercial | Product Owner + Finance |
| **PQ-10** | ¿Se cobra setup/onboarding? (DD-09 no lo define; el research sugiere que la competencia lo hace) | Modelo de ingresos | Product Owner |
| **PQ-11** | ¿Cuál es el pricing real de la WhatsApp Business API en Argentina hoy? | E8 costo por usuario, DD-09 | Product Owner |

### Prioridad BAJA — no bloquean el MVP

| # | Pregunta | Bloquea | Decisor |
|---|----------|---------|---------|
| **PQ-12** | ¿Se soporta más de un tipo de comprobante por tenant (A y B simultáneamente)? | E7, configuración de tenant | Legal + Tech Lead |
| **PQ-13** | ¿Se necesita manejo de retenciones (IVA percibido, retenciones de Ganancias) para el consultorio? | E7, cálculo de impuestos | Legal + Accountant |
| **PQ-14** | ¿Se necesita exportación a formato contable (CSV con la estructura del contador del cliente)? | E10, US-090 | Product Owner |
| **PQ-15** | ¿Cuándo entra el laboratorio externo (pedido de trabajo simple ya está en alcance parcial; integración completa no)? | Roadmap post-MVP | Product Owner |
| **PQ-16** | ¿Se necesita versioning de plantillas de consentimiento por especialidad? | E5 (más complejo que una versión global) | Legal |

---

## Preguntas de discovery que siguen abiertas (de `discovery/discovery.md`)

Estas son las preguntas P1–P5 del research que **no fueron respondidas** y que se arrastran:

| # | Pregunta original | Estado en KB | Impacto en la KB |
|---|-------------------|--------------|------------------|
| **P1** | Segmento objetivo | **Resuelta por DD-02** (PyME 3–10 sillones) | Cubierta |
| **P2** | ¿Obras sociales en el MVP? | **Resuelta por DD-08** (no, fuera de alcance) | Cubierta |
| **P3** | Modelo comercial (free vs pago vs packs) | **Resuelta por DD-09** (suscripción pesos, sin packs, sin free) | Cubierta, pero el monto exacto sigue en PQ-09 |
| **P4** | ARCA primero vs. otro | **Asumida en SU-03** (ARCA es la fuente de verdad) | Supuesto, no confirmado — ver PQ-05 |
| **P5** | Riesgo regulatorio de entrar sin ARCA | **Manejado por DD-01** (compliance-first desde el día 1) | Cubierta |

**Nota**: la mayoría de las preguntas de discovery quedaron resueltas por las decisiones DD-01 a
DD-11 de la KB. Las que siguen abiertas están，现在 todas mapeadas a las PQ de arriba.

---

## Checklist antes de codificar

Antes de escribir la primera línea de código de un change, verificar:

- [ ] ¿Está la regla de negocio relevante codificada en `05_reglas_de_negocio.md`?
- [ ] ¿La entidad tiene `tenant_id` y test cross-tenant? (RN-TEN-02, gate obligatorio)
- [ ] ¿La funcionalidad está en `06_funcionalidades.md` con sus criterios de aceptación?
- [ ] ¿Hay alguna PQ de prioridad ALTA sin responder que afecte este change?
- [ ] Si toca facturación: ¿está el módulo ARCA alineado con `11_facturacion_arca.md`?
- [ ] Si toca datos de salud: ¿está el cifrado y el auditLog en el diseño?
- [ ] ¿El Supuesto relevante está en `09_decisiones_y_supuestos.md` y es válido todavía?

Si alguna respuesta es "no" o "depende", esa es una conversación pendiente antes de codificar.
