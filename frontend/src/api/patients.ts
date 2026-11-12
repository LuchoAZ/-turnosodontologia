/**
 * Cliente de la ficha demográfica del paciente (C-06, design D7/D11).
 *
 * Los `code` de error son los del catálogo estable del backend
 * (`app/domain/patients/errors.py`): la UI conmuta por `code`, nunca por status
 * ni por texto. El `tenant_id` no viaja nunca: sale de la sesión en el servidor.
 *
 * Los `409` de dedupe traen `candidatos` en el cuerpo. Como `ApiError` conserva
 * el `payload` crudo, `candidatesOf` los extrae sin volver a consultar la API.
 * Solo `patient_posible_duplicado` es confirmable; `patient_dni_duplicado` no se
 * puede vencer aunque se reenvíe `confirmar_duplicado=true`.
 */

import { ApiError, apiFetch } from './http'

export type Sexo = 'femenino' | 'masculino' | 'otro' | 'no_declara'

export interface Domicilio {
  calle?: string | null
  numero?: string | null
  localidad?: string | null
  provincia?: string | null
  codigo_postal?: string | null
}

export interface PatientOut {
  id: string
  numero_historia_clinica: string
  nombre: string
  apellido: string
  dni: string | null
  fecha_nacimiento: string | null
  sexo: Sexo | null
  telefono: string
  email: string | null
  domicilio: Domicilio | null
  activo: boolean
  created_at: string
  updated_at: string
}

export interface PatientListOut {
  patients: PatientOut[]
  total: number
}

/** Coincidencia que viaja en el `409`, sin la ficha completa. */
export interface PatientCandidate {
  id: string
  numero_historia_clinica: string
  nombre: string
  apellido: string
  dni: string | null
  telefono: string
}

export interface PatientIn {
  nombre: string
  apellido: string
  telefono: string
  dni?: string | null
  fecha_nacimiento?: string | null
  sexo?: Sexo | null
  email?: string | null
  domicilio?: Domicilio | null
  /**
   * Control del alta, no se persiste: `true` es "sí, es otra persona" y vence
   * solo el dedupe blando. Nunca viaja en una actualización.
   */
  confirmar_duplicado?: boolean
}

/** Actualización parcial: `confirmar_duplicado` no existe en el contrato de PATCH. */
export type PatientPatch = Omit<Partial<PatientIn>, 'confirmar_duplicado'>

export interface ListPatientsParams {
  q?: string
  incluir_inactivos?: boolean
  limit?: number
  offset?: number
}

/** Permisos que esta pantalla consulta (subconjunto de la matriz de C-04). */
export type PatientPermission = 'patient.read' | 'patient.create' | 'patient.update'

function buildQuery(params: ListPatientsParams): string {
  const search = new URLSearchParams()
  const termino = (params.q ?? '').trim()
  if (termino !== '') search.set('q', termino)
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  if (params.incluir_inactivos !== undefined) {
    search.set('incluir_inactivos', String(params.incluir_inactivos))
  }
  const query = search.toString()
  return query === '' ? '' : `?${query}`
}

export function listPatients(params: ListPatientsParams = {}): Promise<PatientListOut> {
  return apiFetch<PatientListOut>(`/patients${buildQuery(params)}`)
}

export function getPatient(patientId: string): Promise<PatientOut> {
  return apiFetch<PatientOut>(`/patients/${patientId}`)
}

export function createPatient(payload: PatientIn): Promise<PatientOut> {
  return apiFetch<PatientOut>('/patients', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updatePatient(patientId: string, payload: PatientPatch): Promise<PatientOut> {
  return apiFetch<PatientOut>(`/patients/${patientId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

function isCandidate(value: unknown): value is PatientCandidate {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.numero_historia_clinica === 'string' &&
    typeof candidate.nombre === 'string' &&
    typeof candidate.apellido === 'string' &&
    typeof candidate.telefono === 'string'
  )
}

/**
 * Candidatos del `409`, validados en runtime: el payload es datos externos y la
 * UI no debe romperse si el backend cambia el cuerpo.
 */
export function candidatesOf(error: unknown): PatientCandidate[] {
  if (!(error instanceof ApiError)) return []
  const payload = error.payload
  if (typeof payload !== 'object' || payload === null) return []
  const candidatos = (payload as { candidatos?: unknown }).candidatos
  if (!Array.isArray(candidatos)) return []
  return candidatos.filter(isCandidate)
}
