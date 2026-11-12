/**
 * Cliente de configuración clínica (C-05, design D1/D8).
 *
 * Los `code` de error son los del catálogo estable del backend
 * (`app/domain/clinic/errors.py`): la UI conmuta por `code`, nunca por status ni
 * por texto. El `tenant_id` no viaja nunca: sale de la sesión en el servidor.
 *
 * Las fechas son `YYYY-MM-DD`, las horas `HH:MM` (Pydantic acepta y devuelve
 * `HH:MM:SS`; la UI recorta al mostrar) y los `Decimal` llegan como string:
 * `porcentaje_liquidacion` se normaliza con `Number(...)` al mostrarlo.
 */

import { apiFetch } from './http'

export type ChairTipo = 'consultorio' | 'rx' | 'cirugia' | 'higiene' | 'otro'

export interface ChairOut {
  id: string
  nombre: string
  tipo: ChairTipo
  ubicacion: string | null
  equipamiento: Record<string, unknown> | null
  activo: boolean
}

export interface ChairListOut {
  chairs: ChairOut[]
}

export interface ChairIn {
  nombre: string
  tipo: ChairTipo
  ubicacion?: string | null
  equipamiento?: Record<string, unknown> | null
}

export type ChairPatch = Partial<ChairIn> & { activo?: boolean }

export interface SpecialtyOut {
  id: string
  nombre: string
}

export interface SpecialtyListOut {
  specialties: SpecialtyOut[]
}

export interface ProfessionalOut {
  id: string
  user_id: string | null
  nombre: string
  apellido: string
  matricula: string
  especialidad: SpecialtyOut
  duracion_default_min: number
  /** `Decimal` serializado por FastAPI: siempre string ("40.00"). */
  porcentaje_liquidacion: string | number
  color_agenda: string
  activo: boolean
}

export interface ProfessionalListOut {
  professionals: ProfessionalOut[]
}

export interface ProfessionalIn {
  nombre: string
  apellido: string
  matricula: string
  especialidad_id: string
  user_id?: string | null
  duracion_default_min?: number
  porcentaje_liquidacion?: number
  color_agenda?: string
}

export type ProfessionalPatch = Partial<ProfessionalIn> & { activo?: boolean }

export interface AvailabilityOut {
  id: string
  professional_id: string | null
  chair_id: string | null
  dia_semana: number
  hora_inicio: string
  hora_fin: string
  slot_min: number
  buffer_previo_min: number
  buffer_posterior_min: number
  fecha_desde: string
  fecha_hasta: string | null
  tipo_practica: string | null
}

export interface AvailabilityListOut {
  availability: AvailabilityOut[]
}

export interface AvailabilityIn {
  professional_id?: string | null
  chair_id?: string | null
  dia_semana: number
  hora_inicio: string
  hora_fin: string
  slot_min?: number
  buffer_previo_min?: number
  buffer_posterior_min?: number
  fecha_desde: string
  fecha_hasta?: string | null
  tipo_practica?: string | null
}

export type AvailabilityPatch = Partial<AvailabilityIn>

/** Permisos que esta pantalla consulta (subconjunto de la matriz de C-04). */
export type ClinicPermission =
  | 'chair.read'
  | 'chair.create'
  | 'chair.update'
  | 'chair.delete'
  | 'professional.read'
  | 'professional.create'
  | 'professional.update'

export function listChairs(): Promise<ChairListOut> {
  return apiFetch<ChairListOut>('/clinic/chairs')
}

export function createChair(payload: ChairIn): Promise<ChairOut> {
  return apiFetch<ChairOut>('/clinic/chairs', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateChair(chairId: string, payload: ChairPatch): Promise<ChairOut> {
  return apiFetch<ChairOut>(`/clinic/chairs/${chairId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

/** Baja lógica: el backend hace `activo = false`, la fila no se borra. */
export function deactivateChair(chairId: string): Promise<void> {
  return apiFetch<void>(`/clinic/chairs/${chairId}`, { method: 'DELETE' })
}

export function listProfessionals(): Promise<ProfessionalListOut> {
  return apiFetch<ProfessionalListOut>('/clinic/professionals')
}

export function createProfessional(payload: ProfessionalIn): Promise<ProfessionalOut> {
  return apiFetch<ProfessionalOut>('/clinic/professionals', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateProfessional(
  professionalId: string,
  payload: ProfessionalPatch,
): Promise<ProfessionalOut> {
  return apiFetch<ProfessionalOut>(`/clinic/professionals/${professionalId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

/**
 * Catálogo visible (globales del seed + propias del tenant). Es la única fuente
 * válida de `especialidad_id`: los UUID5 del seed no se hardcodean en la UI.
 */
export function listSpecialties(): Promise<SpecialtyListOut> {
  return apiFetch<SpecialtyListOut>('/clinic/specialties')
}

export function listAvailability(): Promise<AvailabilityListOut> {
  return apiFetch<AvailabilityListOut>('/clinic/availability')
}

export function createAvailability(payload: AvailabilityIn): Promise<AvailabilityOut> {
  return apiFetch<AvailabilityOut>('/clinic/availability', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateAvailability(
  ruleId: string,
  payload: AvailabilityPatch,
): Promise<AvailabilityOut> {
  return apiFetch<AvailabilityOut>(`/clinic/availability/${ruleId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
