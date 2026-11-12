/**
 * Cliente de la agenda (change `agendar-turno-sin-solapamiento`, D5/D6).
 *
 * Un solo endpoint en v0.1: `POST /api/v1/appointments`. Los `code` de error son
 * los del catálogo estable del backend (`app/domain/agenda/appointments/errors.py`)
 * y la UI conmuta por `code`, nunca por status ni por texto.
 *
 * El `409` de solape trae `recurso`, `motivo` y `rangoEnConflicto` en el cuerpo.
 * `ApiError` conserva el `payload` crudo y `conflictOf` lo valida en runtime: el
 * cuerpo es dato externo y la pantalla no debe romperse si cambia.
 *
 * `inicio` viaja como instante RFC 3339 con offset (RN-AG-09). `fin`,
 * `duracion_min`, `estado` y `origen` **no** se envían: los deriva el servidor
 * (RN-AG-03) y el schema con `extra="forbid"` los rechaza con `422`.
 */

import { ApiError, apiFetch } from './http'

/** Catálogo code-owned del backend (`TipoPractica`); la UI no inventa valores. */
export type TipoPractica =
  | 'consulta'
  | 'control'
  | 'limpieza'
  | 'endodoncia'
  | 'extraccion'
  | 'cirugia'
  | 'periodoncia'
  | 'ortodoncia'
  | 'protesis'
  | 'implante'

export const TIPOS_PRACTICA: TipoPractica[] = [
  'consulta',
  'control',
  'limpieza',
  'endodoncia',
  'extraccion',
  'cirugia',
  'periodoncia',
  'ortodoncia',
  'protesis',
  'implante',
]

export interface AppointmentOut {
  id: string
  professional_id: string
  chair_id: string
  patient_id: string | null
  /** ISO 8601 en UTC (el backend normaliza). */
  inicio: string
  fin: string
  duracion_min: number
  buffer_previo_min: number
  buffer_posterior_min: number
  estado: string
  origen: string
  tipo_practica: TipoPractica | null
}

export interface CreateAppointmentIn {
  professional_id: string
  chair_id: string
  /** `null` = turno sin paciente identificado (RN-AG-10 no aplica). */
  patient_id?: string | null
  /** RFC 3339 con offset: lo arma `localDateTimeToInstant`. */
  inicio: string
  tipo_practica?: TipoPractica | null
}

/** Permisos que esta pantalla consulta (subconjunto de la matriz de C-04). */
export type AppointmentPermission = 'appointment.create'

/** Conflicto legible del `409`, ya validado en runtime. */
export interface AppointmentConflict {
  recurso: string | null
  motivo: string | null
  /** Extremos ISO del turno que ganó; `null` si el error no los trae. */
  inicio: string | null
  fin: string | null
}

export function createAppointment(payload: CreateAppointmentIn): Promise<AppointmentOut> {
  return apiFetch<AppointmentOut>('/appointments', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

function stringOrNull(valor: unknown): string | null {
  return typeof valor === 'string' ? valor : null
}

/**
 * Extrae el conflicto del `409` sin volver a consultar la API.
 *
 * Devuelve `null` cuando el error no es del contrato de la agenda (red caída,
 * `403`, `422`): la pantalla cae al mensaje genérico por `code`.
 */
export function conflictOf(error: unknown): AppointmentConflict | null {
  if (!(error instanceof ApiError)) return null
  const payload = error.payload
  if (typeof payload !== 'object' || payload === null) return null
  const body = payload as Record<string, unknown>

  const recurso = stringOrNull(body.recurso)
  const motivo = stringOrNull(body.motivo)
  const rango = body.rangoEnConflicto
  let inicio: string | null = null
  let fin: string | null = null
  if (typeof rango === 'object' && rango !== null) {
    const extremos = rango as Record<string, unknown>
    inicio = stringOrNull(extremos.inicio)
    fin = stringOrNull(extremos.fin)
  }

  if (recurso === null && motivo === null && inicio === null) return null
  return { recurso, motivo, inicio, fin }
}
