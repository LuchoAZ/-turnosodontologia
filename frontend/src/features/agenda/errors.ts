/**
 * Traducción de los `code` de `app/domain/agenda/appointments/errors.py` a UI.
 *
 * Igual que en pacientes: la UI conmuta por `code` y cae al `message` del backend
 * solo si el código es desconocido. El `code` se muestra al lado para que la demo
 * sea diagnóstica. `asApiError` vive en el cliente HTTP porque ya no es exclusivo
 * de una pantalla.
 */

import type { ApiError } from '@/api/http'
import { asApiError as normalize } from '@/api/http'

const AGENDA_ERROR_MESSAGES: Record<string, string> = {
  recurso_no_encontrado:
    'El recurso no existe en esta clínica o no tenés acceso a él. Actualizá la lista y volvé a elegir.',
  recurso_inactivo: 'El recurso está inactivo y no se le pueden asignar turnos.',
  turno_solapado: 'El horario se solapa con otro turno del mismo recurso. Elegí otro horario.',
  paciente_solapado:
    'El paciente ya tiene un turno con ese profesional en ese horario. Elegí otro horario.',
  duracion_invalida:
    'La duración del turno no es válida: revisá la disponibilidad y la duración por defecto del profesional.',
  invalid_request: 'Revisá los datos: hay campos inválidos o no permitidos.',
  forbidden: 'No tenés permiso para esta acción.',
}

/** Etiqueta del recurso que devuelve el `409`; el contrato usa claves en inglés. */
const RECURSO_LABELS: Record<string, string> = {
  professional: 'profesional',
  chair: 'sillón',
  patient: 'paciente',
}

export function appointmentErrorMessage(error: ApiError): string {
  const known = error.code === null ? undefined : AGENDA_ERROR_MESSAGES[error.code]
  return known ?? error.message
}

export function recursoLabel(recurso: string | null): string | null {
  if (recurso === null) return null
  return RECURSO_LABELS[recurso] ?? recurso
}

export const asApiError = normalize
