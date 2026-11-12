/**
 * Constantes de presentación de la pantalla `/clinica`.
 *
 * Viven fuera de `@/api/clinic` a propósito: los tests mockean ese módulo, y un
 * módulo mockeado deja vacías sus exportaciones no funcionales. Las
 * especialidades **no** están acá: se leen de `GET /clinic/specialties` porque
 * cada tenant puede tener las suyas.
 */

import type { ChairTipo } from '@/api/clinic'

export interface SelectOption<T extends string> {
  value: T
  label: string
}

/** Valores del enum `chair_tipo` del backend, con su etiqueta de UI. */
export const CHAIR_TYPE_OPTIONS: readonly SelectOption<ChairTipo>[] = [
  { value: 'consultorio', label: 'Consultorio' },
  { value: 'rx', label: 'Rayos X' },
  { value: 'cirugia', label: 'Cirugía' },
  { value: 'higiene', label: 'Higiene' },
  { value: 'otro', label: 'Otro' },
]

export function chairTypeLabel(tipo: ChairTipo): string {
  return CHAIR_TYPE_OPTIONS.find((option) => option.value === tipo)?.label ?? tipo
}

/**
 * `dia_semana` (smallint 0-6) sigue `EXTRACT(DOW)` de Postgres: 0 = domingo.
 * El contrato se documenta en `docs/clinic.md`; C-07 (agenda) lo reutiliza para
 * generar slots, así que no se inventa un mapeo distinto en la UI.
 */
export const DAY_OPTIONS: readonly { value: number; label: string }[] = [
  { value: 0, label: 'Domingo' },
  { value: 1, label: 'Lunes' },
  { value: 2, label: 'Martes' },
  { value: 3, label: 'Miércoles' },
  { value: 4, label: 'Jueves' },
  { value: 5, label: 'Viernes' },
  { value: 6, label: 'Sábado' },
]

export function dayLabel(diaSemana: number): string {
  return DAY_OPTIONS.find((option) => option.value === diaSemana)?.label ?? String(diaSemana)
}

/** `HH:MM:SS` de la API → `HH:MM` de la UI. */
export function hhmm(value: string): string {
  return value.slice(0, 5)
}
