/**
 * Frontera de fechas del formulario de turnos (RN-AG-09).
 *
 * El `<input type="date">` y el `<input type="time">` devuelven hora de pared, sin
 * zona. La API exige un instante RFC 3339 **con offset** y normaliza a UTC, así
 * que el SPA arma el instante acá, con la zona del navegador: la del equipo que
 * agenda. El servidor nunca reinterpreta la hora de pared: si el navegador
 * estuviera en otra zona, el turno quedaría en el instante equivocado, y por eso
 * la conversión es una función pura y testeada, no un `toISOString()` suelto en
 * el componente.
 *
 * `formatInstant` hace el camino inverso para mostrar el rango del `409` en la
 * misma hora de pared que el usuario ve en el formulario.
 */

const FECHA_RE = /^(\d{4})-(\d{2})-(\d{2})$/
const HORA_RE = /^(\d{2}):(\d{2})$/

function pad(valor: number): string {
  return String(valor).padStart(2, '0')
}

/**
 * Convierte `fecha` (`YYYY-MM-DD`) + `hora` (`HH:MM`) al instante UTC equivalente
 * en la zona del navegador. Devuelve `null` si la combinación no es una fecha y
 * hora reales (el `<input>` no impide `2026-02-31`).
 */
export function localDateTimeToInstant(fecha: string, hora: string): string | null {
  const fechaMatch = FECHA_RE.exec(fecha)
  const horaMatch = HORA_RE.exec(hora)
  if (fechaMatch === null || horaMatch === null) return null

  const anio = Number(fechaMatch[1])
  const mes = Number(fechaMatch[2])
  const dia = Number(fechaMatch[3])
  const horas = Number(horaMatch[1])
  const minutos = Number(horaMatch[2])
  if (horas > 23 || minutos > 59) return null

  const local = new Date(anio, mes - 1, dia, horas, minutos, 0, 0)
  // `Date` normaliza los desbordes (31/02 → 03/03): comparar los componentes
  // detecta la fecha inexistente en vez de agendarla en otro día.
  if (
    local.getFullYear() !== anio ||
    local.getMonth() !== mes - 1 ||
    local.getDate() !== dia ||
    local.getHours() !== horas ||
    local.getMinutes() !== minutos
  ) {
    return null
  }
  return local.toISOString()
}

/** Instante ISO → `dd/mm/aaaa hh:mm` en la zona del navegador (`—` si es inválido). */
export function formatInstant(iso: string): string {
  const momento = new Date(iso)
  if (Number.isNaN(momento.getTime())) return '—'
  return (
    `${pad(momento.getDate())}/${pad(momento.getMonth() + 1)}/${momento.getFullYear()}` +
    ` ${pad(momento.getHours())}:${pad(momento.getMinutes())}`
  )
}

/** Rango legible del conflicto; si falta un extremo, `—`. */
export function formatRango(inicio: string | null, fin: string | null): string {
  if (inicio === null || fin === null) return '—'
  return `${formatInstant(inicio)} a ${formatInstant(fin)}`
}
