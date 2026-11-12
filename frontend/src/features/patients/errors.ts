/**
 * Traducción de los `code` de `app/domain/patients/errors.py` a mensajes de UI.
 *
 * La UI nunca muestra el `message` del backend como fuente de verdad: conmuta
 * por `code` y cae al `message` de la API solo si el código es desconocido. El
 * `code` se sigue mostrando al lado para que la demo sea diagnóstica.
 */

import type { ApiError } from '@/api/http'

/**
 * `asApiError` se mudó al cliente HTTP (lo usan pacientes y agenda): se reexporta
 * para no tocar los imports de la pantalla de C-06.
 */
export { asApiError } from '@/api/http'

const PATIENT_ERROR_MESSAGES: Record<string, string> = {
  patient_not_found: 'El paciente no existe en esta clínica.',
  patient_dni_duplicado:
    'Ya hay un paciente con ese DNI en esta clínica. Buscalo en el listado en vez de darlo de alta otra vez.',
  patient_posible_duplicado:
    'Hay pacientes con datos parecidos. Revisá la lista antes de confirmar el alta.',
  invalid_request: 'Revisá los datos: hay campos inválidos o no permitidos.',
  forbidden: 'No tenés permiso para esta acción.',
}

export function patientErrorMessage(error: ApiError): string {
  const known = error.code === null ? undefined : PATIENT_ERROR_MESSAGES[error.code]
  return known ?? error.message
}
