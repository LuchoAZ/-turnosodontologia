/**
 * Traducción de los `code` de `app/domain/clinic/errors.py` a mensajes de UI.
 *
 * La UI nunca muestra el `message` del backend como fuente de verdad: conmuta
 * por `code` y cae al `message` de la API solo si el código es desconocido. El
 * `code` se sigue mostrando al lado para que la demo sea diagnóstica.
 */

import type { ApiError } from '@/api/http'

const CLINIC_ERROR_MESSAGES: Record<string, string> = {
  chair_not_found: 'El sillón no existe en esta clínica.',
  chair_name_taken: 'Ya hay un sillón con ese nombre en la clínica.',
  professional_not_found: 'El profesional no existe en esta clínica.',
  professional_matricula_taken: 'Ya hay un profesional con esa matrícula.',
  specialty_not_found: 'La especialidad no está disponible en esta clínica.',
  user_not_member: 'El usuario no es miembro activo de la clínica.',
  availability_not_found: 'La regla de disponibilidad no existe en esta clínica.',
  availability_overlap: 'La ventana se superpone con otra regla del mismo día y alcance.',
  invalid_request: 'Revisá los datos: hay campos inválidos o no permitidos.',
  forbidden: 'No tenés permiso para esta acción.',
}

export function clinicErrorMessage(error: ApiError): string {
  const known = error.code === null ? undefined : CLINIC_ERROR_MESSAGES[error.code]
  return known ?? error.message
}
