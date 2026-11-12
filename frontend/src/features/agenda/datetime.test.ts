import { describe, expect, it } from 'vitest'
import { formatInstant, formatRango, localDateTimeToInstant } from './datetime'

/**
 * RN-AG-09 en el borde del cliente: el input del navegador es hora de pared y la
 * API exige un instante RFC 3339 **con offset**. Estos tests no fijan la zona del
 * runner: comprueban el round-trip (lo que se manda es exactamente la hora de
 * pared que se escribió) y los rechazos.
 */
describe('localDateTimeToInstant (RN-AG-09)', () => {
  it('convierte la hora de pared al mismo instante en UTC', () => {
    const iso = localDateTimeToInstant('2026-11-16', '09:30')

    expect(iso).not.toBeNull()
    expect(iso?.endsWith('Z')).toBe(true)
    const vuelta = new Date(iso as string)
    expect(vuelta.getFullYear()).toBe(2026)
    expect(vuelta.getMonth()).toBe(10)
    expect(vuelta.getDate()).toBe(16)
    expect(vuelta.getHours()).toBe(9)
    expect(vuelta.getMinutes()).toBe(30)
    expect(vuelta.getSeconds()).toBe(0)
  })

  it('rechaza una fecha que no existe en el calendario', () => {
    expect(localDateTimeToInstant('2026-02-31', '09:00')).toBeNull()
  })

  it.each([['25:00'], ['09:60'], ['9:00'], ['']])('rechaza la hora inválida %s', (hora) => {
    expect(localDateTimeToInstant('2026-11-16', hora)).toBeNull()
  })

  it.each([['16/11/2026'], ['2026-11'], ['']])('rechaza la fecha inválida %s', (fecha) => {
    expect(localDateTimeToInstant(fecha, '09:00')).toBeNull()
  })
})

describe('formatInstant', () => {
  it('muestra el instante en la hora de pared del navegador', () => {
    const iso = localDateTimeToInstant('2026-11-16', '09:30') as string
    expect(formatInstant(iso)).toBe('16/11/2026 09:30')
  })

  it('un instante inválido no rompe la vista', () => {
    expect(formatInstant('no-es-fecha')).toBe('—')
  })
})

describe('formatRango', () => {
  it('arma el rango legible del conflicto', () => {
    const inicio = localDateTimeToInstant('2026-11-16', '09:00') as string
    const fin = localDateTimeToInstant('2026-11-16', '09:30') as string
    expect(formatRango(inicio, fin)).toBe('16/11/2026 09:00 a 16/11/2026 09:30')
  })

  it('si falta un extremo muestra el guion', () => {
    expect(formatRango(null, null)).toBe('—')
  })
})
