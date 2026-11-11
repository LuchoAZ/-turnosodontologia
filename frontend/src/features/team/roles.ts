/**
 * Roles asignables desde la UI de Equipo y sus etiquetas.
 *
 * Vive fuera de `@/api/team` a propósito: son constantes de presentación y los
 * tests del cliente API las mockean (`vi.mock`), así que un módulo mockeado las
 * dejaría vacías. `owner` no está: solo se obtiene por transferencia atómica, y
 * `patient`/`external_lab` no son equipo.
 */

export const ASSIGNABLE_ROLES = [
  'clinical_admin',
  'professional',
  'assistant',
  'front_desk',
  'billing',
  'accountant',
] as const

export type AssignableRole = (typeof ASSIGNABLE_ROLES)[number]

/** Etiqueta de UI por rol; el valor del `<select>` sigue siendo el código. */
export const ROLE_LABELS: Record<AssignableRole, string> = {
  clinical_admin: 'Administrativo/a clínico/a',
  professional: 'Profesional',
  assistant: 'Asistente',
  front_desk: 'Recepción',
  billing: 'Facturación',
  accountant: 'Contador/a',
}
