# Visión y Objetivos

## Propósito del sistema

Una plataforma SaaS multi-tenant donde **una clínica odontológica PyME de 3 a 10 sillones
administra su operación completa — agenda por profesional y sillón, historia clínica con
odontograma, caja, facturación electrónica ante ARCA y compliance de datos de salud — con la
suficiente trazabilidad normativa para defenderla ante una auditoría, un reclamo del paciente
o un requerimiento de la AAIP.**

El sistema **no** existe para ser "el más completo" ni "el más lindo". Existe porque el
relevamiento competitivo de 20 sistemas dio un resultado incómodo: **la gestión de turnos ya no
es un problema de mercado.** Los 20 competidores verificados la tienen. Lo que ninguno puede
demostrar con evidencia es cumplir la capa normativa que en Argentina es literalmente
obligatoria: facturación con comprobante A y alta de solvencia, nomencladores de obra social,
historia clínica con copia autenticada y consentimiento informado.

**Enfoque: compliance-first.** El diferencial es la actualización normativa sostenida y la
trazabilidad de datos de salud. La agenda es el medio, no el fin.

### Contexto de mercado (ver `discovery/discovery.md`, 2026-10-01)

| Hallazgo | Implicación para este producto |
|----------|--------------------------------|
| 20/20 competidores tienen agenda con reserva online | No es un diferencial; es un requisito de entrada |
| 19/20 son SaaS en nube; 1 solo local-first (Mac-only) | Nube multi-tenant es la norma, no la excepción |
| Top 3 por volumen: OdontoClinIA, DentalCore, Bilog | Segmento PYME dominado por OdontoClinIA (gratis) y Bilog (20 años) |
| Claims de ARCA "100% integrado" generalizado `[A]` sin evidencia técnica | Atacar esos claims es el eje comercial más fuerte disponible |
| OdontoClinIA aparece en ReNaPDiS `#248` (verificado) | Prueba de que el nicho regulado está vacío |
| Nadie modela el **sillón** como unidad de capacidad | Diferencial técnico concreto y de bajo costo de implementar |
| Pricing monthly: USD 15–90 (aprox.) | Hay presupuesto en la categoría, pero precio en pesos local es un hueco |

## Objetivos por actor

| Actor | Objetivo principal | Objetivos secundarios |
|-------|-------------------|----------------------|
| **Dueño de la clínica** | Saber si el negocio es rentable: cuánto factura, cuánto le corresponde a cada profesional, cuánto se pierde por turnos no facturados | Facturar sin depender de un contador externo; dormir tranquilo con el compliance de datos |
| **Dirección clínica** | tener la agenda del día bajo control y detectar sobrecupos, huecos y cancelaciones temprano | Ver carga por sillón (no solo por profesional) |
| **Odontólogo** | Registrar el trabajo en menos de 60 segundos durante la atención, sin perder el foco del paciente | Ver el odontograma de un vistazo; que la asistente complete lo administrativo |
| **Higienista / Asistente** | Cargar razonamiento y procedimientos con su propio login y sin pisar al odontólogo | Poder preparar el turno antes de que llegue el paciente |
| **Recepcionista** | Agendar, reprogramar y confirmar sin que el paciente la llame 4 veces al mismo teléfono | Que la lista de espera rellene los huecos sola |
| **Administración / Facturación** | Emitir comprobantes y cobrar sin errores de carga fiscal ni de imputación errónea | Conciliar caja del día contra lo facturado |
| **Paciente** | Sacar turno a las 3am sin llamar, y no tener que explicar su historia clínica cada vez | Recibir recordatorios y copia de su documentación |
| **Laboratorio / profesional externo** | Recibir el pedido de trabajo con los datos exactos, y sin exponerse a más datos de salud de los que necesita | — |
| **Operador del producto (nosotros)** | Que la actualización normativa la paguemos una vez y no N veces | Que el onboarding de un tenant nuevo sea automatizado y no una tarea de soporte manual |

## Alcance v0.1 (MVP)

Entregable por **vertical slices**, no por capas técnicas. Cada slice debe ser demostrable
de punta a punta. El orden propuesto está en [`06_funcionalidades.md`](06_funcionalidades.md).

- [ ] **Alta de clínica y onboarding fiscal** — alta del tenant, configuración fiscal, carga de certificado X.509, validación de token WSAA
- [ ] **Agenda por profesional y sillón** — con duración por tipo de práctica, buffers, y el sillón como unidad de capacidad bloqueable
- [ ] **Reserva 24/7 del paciente** — portal web + WhatsApp API oficial, con lista de espera que rellena huecos cancelados
- [ ] **Ficha del paciente con odontograma FDI y periodontograma** — charting por pieza, con historial de versiones
- [ ] **Consentimiento informado con firma** — plantilla versionada, firma y evidencia de aceptación
- [ ] **Historia clínica inmutable + copia autenticada** — append-only, con procedimiento de entrega documentado
- [ ] **Caja, señas y liquidación por profesional** — sesión de caja con arqueo, y liquidación por profesional con porcentajes
- [ ] **Facturación ARCA end-to-end** — comprobante electrónico desde la propia UI, con idempotencia y manejo de rechazos
- [ ] **RBAC + Ley 25.326 / AAIP** — aislamiento por tenant, roles, y flujo de respuesta a requerimiento de acceso
- [ ] **Migración con deduplicación** — importación desde Excel/CSV del sistema anterior, con detección de duplicados por DNI + nombre

## Fuera de alcance

Explícitamente **no** en v0.1, con justificación:

- **Obras sociales y nomencladores** — el mayor costo operativo recurrente y ~2 meses de plazo
  adicionales. Ningún competidor lo resuelve de punta a punta, así que el hueco sigue
  existiendo en v0.2. Decisión DD-08.
- **Radiología / imágenes DICOM** — el relevamiento lo marca como una de las 4 brechas
  grandes, pero requiere PACS y es un proyecto en sí mismo. v0.2/v0.3.
- **Laboratorio y UNITY (integración con línea de escaneo)** — solo el pedido de trabajo simple. v0.3.
- **Hardware de consultorio** — integraciones con sillón, lámpara, etc. Fuera por decisión.
- **Tier gratis / packs de consumibles** — decisión comercial DD-09.
- **App móvil nativa** — web responsive primero.
- **Multi-país** — ARCA/AFIP argentino es el único esquema fiscal soportado. LatAm queda
  como expansión futura, no como diseño anticipado.
- **Facturadores A/B/C:** solo **A y B** en v0.1. C y M fuera de alcance.
- **IA clínica / análisis de radiografía** — riesgo regulatorio alto (CDSS) y no es el eje.

## Métricas de éxito

### Producto / negocio

| Métrica | Meta v0.1 | Por qué importa |
|---------|-----------|-----------------|
| **Time-to-first-emitido** | < 30 min desde alta de tenant hasta el primer comprobante | Si tarda más, el onboarding es un ticket de soporte por clínica |
| Time-to-first-turno agendado | < 15 min desde alta | idem |
| Consultorías PyME ya generando turnos | ≥ 3 de referencia al cierre | valida el segmento elegido |
| Holes de agenda rellenados desde lista de espera | ≥ 15% | valida el RN-AG de lista de espera |
| % pacientes que reservan sin llamar | ≥ 60% | valida el canal self-service |

### Técnicas / de riesgo

| Métrica | Meta | Por qué importa |
|---------|------|-----------------|
| Comprobantes emitidos sin intervención manual | ≥ 99% | mide la madurez de la integración ARCA |
| Rechazos de ARCA por error de código nuestro | 0 | los rechazos por datos del receptor son inevitables |
| Cumplimiento de SLA de copia autenticada | 100% | requisito legal, no negociable |
| Auditorías de acceso a datos sensibles registradas | 100% | requisito legal + defensa en litigio |
| Cross-tenant leak (hallazgos, objetivo) | **0** | la métrica que, si falla, mata el negocio |

### Anti-métricas (se miden activamente para evitar)

- **Horas de soporte por clínica al mes.** Si supera 2 h/clínica, el producto está mal
  diseñado y el modelo de suscripción en pesos no cierra.
- **Claims de compliance publicados sin verificación.** Cero. El posicionamiento se gana por
  lo que se puede probar, no por lo que se promete (ver `discovery/discovery.md`).

## Principios de producto

1. **Compliance antes que features.** Una función que no se puede auditar no entra.
2. **Un verbo por rol.** Si un actor necesita tres verbos, probablemente son dos roles.
3. **El sillón es la unidad de capacidad.** Si la agenda no puede bloquear el sillón, no
   cumple su función en una clínica con más de un sillón.
4. **Sin dato de salud sin motivo.** Cada lectura de historia clínica queda auditada.
5. **Nada se borra físicamente en historia clínica.** Solo se anota.
6. **Si una norma cambia, la actualizamos nosotros, no el cliente.**
