import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './http'
import {
  candidatesOf,
  createPatient,
  getPatient,
  listPatients,
  updatePatient,
  type PatientCandidate,
  type PatientOut,
} from './patients'

type FetchArgs = Parameters<typeof fetch>

const fetchMock = vi.fn<(...args: FetchArgs) => Promise<Response>>()

function jsonResponse(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response
}

function callUrl(index: number): string {
  const call = fetchMock.mock.calls[index]
  if (!call) throw new Error(`no existe la llamada ${index}`)
  return String(call[0])
}

function callInit(index: number): RequestInit {
  const call = fetchMock.mock.calls[index]
  return (call?.[1] ?? {}) as RequestInit
}

const PACIENTE: PatientOut = {
  id: 'p-1',
  numero_historia_clinica: '000001',
  nombre: 'Ana',
  apellido: 'Pérez',
  dni: '30111222',
  fecha_nacimiento: '1990-05-04',
  sexo: 'femenino',
  telefono: '11 5555-1234',
  email: 'ana@example.com',
  domicilio: null,
  activo: true,
  created_at: '2026-11-12T00:00:00Z',
  updated_at: '2026-11-12T00:00:00Z',
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('listPatients', () => {
  it('sin parámetros pega al listado sin query string', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { patients: [PACIENTE], total: 1 }))

    const result = await listPatients()

    expect(result.total).toBe(1)
    expect(callUrl(0)).toBe('/api/v1/patients')
    expect(callInit(0).credentials).toBe('include')
  })

  it('recorta el q y arma la query con paginación e inactivos', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { patients: [], total: 0 }))

    await listPatients({ q: '  perez  ', limit: 10, offset: 20, incluir_inactivos: true })

    expect(callUrl(0)).toBe('/api/v1/patients?q=perez&limit=10&offset=20&incluir_inactivos=true')
  })

  it('omite el q en blanco y los parámetros indefinidos', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { patients: [], total: 0 }))

    await listPatients({ q: '   ', limit: 5 })

    expect(callUrl(0)).toBe('/api/v1/patients?limit=5')
  })
})

describe('getPatient', () => {
  it('lee una ficha por id', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, PACIENTE))

    const result = await getPatient('p-1')

    expect(result.numero_historia_clinica).toBe('000001')
    expect(callUrl(0)).toBe('/api/v1/patients/p-1')
  })
})

describe('createPatient', () => {
  it('hace POST con el body y devuelve la ficha creada', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, PACIENTE))

    const result = await createPatient({
      nombre: 'Ana',
      apellido: 'Pérez',
      telefono: '11 5555-1234',
      confirmar_duplicado: true,
    })

    expect(result.id).toBe('p-1')
    expect(callUrl(0)).toBe('/api/v1/patients')
    expect(callInit(0).method).toBe('POST')
    expect(JSON.parse(String(callInit(0).body))).toEqual({
      nombre: 'Ana',
      apellido: 'Pérez',
      telefono: '11 5555-1234',
      confirmar_duplicado: true,
    })
  })

  it('propaga el code y los candidatos del 409 blando', async () => {
    const candidatos: PatientCandidate[] = [
      {
        id: 'p-9',
        numero_historia_clinica: '000009',
        nombre: 'Ana',
        apellido: 'Pérez',
        dni: null,
        telefono: '11 5555-1234',
      },
    ]
    fetchMock.mockResolvedValueOnce(
      jsonResponse(409, {
        code: 'patient_posible_duplicado',
        message: 'Hay pacientes con datos parecidos.',
        candidatos,
      }),
    )

    const error = await createPatient({
      nombre: 'Ana',
      apellido: 'Pérez',
      telefono: '11 5555-1234',
    }).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 409, code: 'patient_posible_duplicado' })
    expect(candidatesOf(error)).toEqual(candidatos)
  })

  it('el 409 duro por DNI llega sin candidatos confirmables', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(409, {
        code: 'patient_dni_duplicado',
        message: 'Ya hay un paciente con ese DNI.',
        candidatos: [
          {
            id: 'p-9',
            numero_historia_clinica: '000009',
            nombre: 'Ana',
            apellido: 'Pérez',
            dni: '30111222',
            telefono: '11 5555-1234',
          },
        ],
      }),
    )

    const error = await createPatient({
      nombre: 'Ana',
      apellido: 'Pérez',
      telefono: '11 5555-1234',
      dni: '30111222',
      confirmar_duplicado: true,
    }).catch((caught: unknown) => caught)

    // El `409` duro trae el existente, pero la regla no se puede vencer: la UI
    // solo mira el `code` para decidir si ofrece el diálogo.
    expect(error).toMatchObject({ code: 'patient_dni_duplicado' })
    expect(candidatesOf(error)).toHaveLength(1)
  })
})

describe('updatePatient', () => {
  it('hace PATCH con solo los campos enviados', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ...PACIENTE, telefono: '11 4444-0000' }))

    const result = await updatePatient('p-1', { telefono: '11 4444-0000' })

    expect(result.telefono).toBe('11 4444-0000')
    expect(callUrl(0)).toBe('/api/v1/patients/p-1')
    expect(callInit(0).method).toBe('PATCH')
    expect(JSON.parse(String(callInit(0).body))).toEqual({ telefono: '11 4444-0000' })
  })
})

describe('candidatesOf', () => {
  it('devuelve lista vacía si el error no trae candidatos', () => {
    expect(candidatesOf(new ApiError(403, 'forbidden', 'No autorizado.'))).toEqual([])
    expect(candidatesOf(new Error('boom'))).toEqual([])
    expect(candidatesOf(null)).toEqual([])
  })
})
