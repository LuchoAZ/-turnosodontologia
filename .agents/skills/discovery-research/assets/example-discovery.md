# Discovery — ToritoBarber

**Fecha**: 2026-09-10
**Fuentes investigadas**: 2 competidores (ver `discovery/sources/`)

## 1. Problema que resuelve

Las barberías chicas (1-3 sillas) coordinan turnos por WhatsApp/papel, lo que
genera dobles reservas y tiempo perdido confirmando manualmente cada turno.

## 2. Usuarios / roles

- **Cliente**: reserva un turno sin llamar ni escribir.
- **Barbero/dueño**: ve su agenda del día, confirma o cancela turnos.

## 3. Casos de uso

1. Como cliente, quiero ver los horarios libres de un barbero para reservar
   sin tener que preguntar por WhatsApp.
2. Como barbero, quiero ver mi agenda del día para saber cuántos clientes
   tengo y a qué hora.
3. Como cliente, quiero cancelar un turno con anticipación para liberar el
   horario.

## 4. Competidores / soluciones existentes

| Competidor | Problema que resuelve | Pricing | Diferenciadores |
|---|---|---|---|
| Calendly | Elimina el ida-y-vuelta de emails para coordinar reuniones | Free / USD 10-16 por usuario/mes | Simplicidad de setup, se integra a calendarios existentes |
| Fresha | Turnos para salones/barberías, con pagos y CRM integrado | Comisión por transacción, plan free limitado | Pensado específicamente para el rubro belleza/barbería |

**Notas**: Fresha es el competidor más directo (mismo rubro). Calendly es
genérico — sirve de referencia de UX de agendamiento, no de features de
barbería específicas.

## 5. Funcionalidades necesarias

- Reserva de turno online sin registro obligatorio del cliente.
- Vista de agenda diaria para el barbero.
- Cancelación de turno con anticipación mínima configurable.

## 6. Funcionalidades opcionales

- Recordatorio automático por WhatsApp 24hs antes.
- Pagos online (a diferencia de Fresha, no es necesario para la v1 — el pago
  sigue siendo en el local).

## 7. Reglas de negocio

- No se puede cancelar un turno con menos de 2 horas de anticipación.
- Un barbero no puede tener dos turnos superpuestos.

## 8. Integraciones

- Ninguna integración externa obligatoria para la v1 (a diferencia de Fresha,
  que integra pagos — decisión consciente de dejarlo fuera del MVP).

## 9. Restricciones

- Presupuesto acotado (proyecto de un solo dueño de barbería, no una cadena).
- Tiene que andar bien en celular — la mayoría de los clientes va a reservar
  desde el teléfono, no desde una computadora.

## 10. Riesgos

- **Supuesto sin probar**: que los clientes prefieran reservar online en vez
  de seguir mandando WhatsApp por costumbre — no está validado con usuarios
  reales todavía.
- **Riesgo**: si el barbero no actualiza su disponibilidad seguido, el sistema
  muestra horarios que en realidad no están libres.

## 11. Preguntas abiertas

- ¿Un solo barbero por ahora, o hay que soportar varios desde el día 1?
- ¿Hace falta login para el cliente, o alcanza con nombre + teléfono por turno?
