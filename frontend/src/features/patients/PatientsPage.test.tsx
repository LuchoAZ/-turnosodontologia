import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import { ApiError } from '@/api/http'
import * as patientsApi from '@/api/patients'
import type { PatientCandidate, PatientOut } from '@/api/patients'
import { AuthProvider } from '@/features/auth/AuthProvider'
import PatientsPage from './PatientsPage'

vi.mock('@/api/auth')
vi.mock('@/api/patients', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/patients')>()
  return {
    ...actual,
    listPatients: vi.fn(),
    getPatient: vi.fn(),
    createPatient: vi.fn(),
    updatePatient: vi.fn(),
  }
})

const auth = vi.mocked(authApi)
const api = vi.mocked(patientsApi)

function sessionWith(permissions: string[]): SessionOut {
  return {
    user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
    tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
    roles: ['owner'],
    permissions,
    mfa_enrolled: true,
  }
}

const PERMISOS_TOTALES = ['patient.read', 'patient.create', 'patient.update']

const ANA: PatientOut = {
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

const CANDIDATO: PatientCandidate = {
  id: 'p-9',
  numero_historia_clinica: '000009',
  nombre: 'Ana',
  apellido: 'Pérez',
  dni: null,
  telefono: '11 5555-1234',
}

function renderPage(permissions: string[] = PERMISOS_TOTALES) {
  auth.me.mockResolvedValue(sessionWith(permissions))
  return render(
    <MemoryRouter>
      <AuthProvider>
        <PatientsPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

/** La celda "Pérez, Ana" de la tabla; su `tr` es la fila completa. */
function cellOf(name: string | RegExp): HTMLElement {
  return screen.getByRole('cell', { name })
}

function rowOf(name: string | RegExp): HTMLElement {
  const row = cellOf(name).closest('tr')
  if (row === null) throw new Error(`No hay fila para ${name}`)
  return row
}

async function abrirAlta(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('cell', { name: /pérez, ana/i })
  await user.click(screen.getByRole('button', { name: /nuevo paciente/i }))
}

async function completarAlta(
  user: ReturnType<typeof userEvent.setup>,
  valores: { nombre: string; apellido: string; telefono: string; dni?: string },
) {
  await user.type(screen.getByLabelText(/^nombre$/i), valores.nombre)
  await user.type(screen.getByLabelText(/^apellido$/i), valores.apellido)
  await user.type(screen.getByLabelText(/^teléfono$/i), valores.telefono)
  if (valores.dni !== undefined) {
    await user.type(screen.getByLabelText(/^dni$/i), valores.dni)
  }
  await user.click(screen.getByRole('button', { name: /guardar paciente/i }))
}

beforeEach(() => {
  vi.resetAllMocks()
  api.listPatients.mockResolvedValue({ patients: [ANA], total: 1 })
  api.createPatient.mockResolvedValue({
    ...ANA,
    id: 'p-2',
    numero_historia_clinica: '000002',
    nombre: 'Beto',
    apellido: 'Gómez',
    dni: null,
    telefono: '11 4444-0000',
  })
  api.updatePatient.mockResolvedValue({ ...ANA, telefono: '11 4444-0000' })
})

describe('PatientsPage — listado y búsqueda (S11.1)', () => {
  it('lista los pacientes que devuelve el backend con su total y su HCE', async () => {
    renderPage()

    await screen.findByRole('cell', { name: /pérez, ana/i })
    expect(within(rowOf(/pérez, ana/i)).getByText('000001')).toBeInTheDocument()
    expect(within(rowOf(/pérez, ana/i)).getByText('30111222')).toBeInTheDocument()
    expect(screen.getByText(/^1 paciente$/i)).toBeInTheDocument()
  })

  it('busca con el término recortado contra el backend', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('cell', { name: /pérez, ana/i })

    await user.type(screen.getByLabelText(/buscar paciente/i), '  perez  ')
    await user.click(screen.getByRole('button', { name: /^buscar$/i }))

    await waitFor(() => expect(api.listPatients).toHaveBeenLastCalledWith({ q: 'perez' }))
  })

  it('la carga inicial no manda un q vacío', async () => {
    renderPage()

    await screen.findByRole('cell', { name: /pérez, ana/i })
    expect(api.listPatients).toHaveBeenCalledWith({ q: '' })
  })

  it('incluir inactivos viaja al backend cuando se marca', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('cell', { name: /pérez, ana/i })

    await user.click(screen.getByLabelText(/incluir dados de baja/i))
    await user.click(screen.getByRole('button', { name: /^buscar$/i }))

    await waitFor(() =>
      expect(api.listPatients).toHaveBeenLastCalledWith({ q: '', incluir_inactivos: true }),
    )
  })
})

describe('PatientsPage — permisos (S11.5)', () => {
  it('sin patient.read muestra sin permisos y no llama al backend', async () => {
    renderPage([])

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(api.listPatients).not.toHaveBeenCalled()
  })

  it('sin patient.create no renderiza el alta', async () => {
    renderPage(['patient.read'])
    await screen.findByRole('cell', { name: /pérez, ana/i })

    expect(screen.queryByRole('button', { name: /nuevo paciente/i })).not.toBeInTheDocument()
  })

  it('sin patient.update la tabla no ofrece editar', async () => {
    renderPage(['patient.read'])
    await screen.findByRole('cell', { name: /pérez, ana/i })

    expect(screen.queryByRole('button', { name: /editar/i })).not.toBeInTheDocument()
  })

  it('con patient.update cada fila ofrece editar', async () => {
    renderPage(['patient.read', 'patient.update'])
    await screen.findByRole('cell', { name: /pérez, ana/i })

    expect(screen.getByRole('button', { name: /editar/i })).toBeInTheDocument()
  })

  it('un 403 del listado se informa como falta de permisos, no como error genérico', async () => {
    api.listPatients.mockRejectedValue(new ApiError(403, 'forbidden', 'No autorizado.'))

    renderPage()

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(screen.getByText('forbidden')).toBeInTheDocument()
  })
})

describe('PatientsPage — alta (S11.2, S11.3, S11.4)', () => {
  it('crea el paciente con el backend y lo muestra con su HCE', async () => {
    const user = userEvent.setup()
    renderPage()
    await abrirAlta(user)

    await user.type(screen.getByLabelText(/^nombre$/i), 'Beto')
    await user.type(screen.getByLabelText(/^apellido$/i), 'Gómez')
    await user.type(screen.getByLabelText(/^teléfono$/i), '11 4444-0000')
    fireEvent.change(screen.getByLabelText(/fecha de nacimiento/i), {
      target: { value: '1985-03-02' },
    })
    await user.click(screen.getByRole('button', { name: /guardar paciente/i }))

    await waitFor(() =>
      expect(api.createPatient).toHaveBeenCalledWith(
        expect.objectContaining({
          nombre: 'Beto',
          apellido: 'Gómez',
          telefono: '11 4444-0000',
          fecha_nacimiento: '1985-03-02',
        }),
      ),
    )
    await screen.findByRole('cell', { name: /gómez, beto/i })
    expect(within(rowOf(/gómez, beto/i)).getByText('000002')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('valida los campos obligatorios sin llamar al backend', async () => {
    const user = userEvent.setup()
    renderPage()
    await abrirAlta(user)

    await user.click(screen.getByRole('button', { name: /guardar paciente/i }))

    expect(await screen.findByText(/completá nombre, apellido y teléfono/i)).toBeInTheDocument()
    expect(api.createPatient).not.toHaveBeenCalled()
  })

  it('el DNI duplicado se informa sin diálogo y conserva lo cargado', async () => {
    const user = userEvent.setup()
    api.createPatient.mockRejectedValue(
      new ApiError(409, 'patient_dni_duplicado', 'Ya hay un paciente con ese DNI.', null, {
        code: 'patient_dni_duplicado',
        candidatos: [CANDIDATO],
      }),
    )
    renderPage()
    await abrirAlta(user)

    await completarAlta(user, {
      nombre: 'Ana',
      apellido: 'Pérez',
      telefono: '11 5555-1234',
      dni: '30111222',
    })

    expect(await screen.findByText(/ya hay un paciente con ese dni/i)).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: /posible duplicado/i })).not.toBeInTheDocument()
    expect(screen.getByDisplayValue('Ana')).toBeInTheDocument()
    expect(screen.getByDisplayValue('30111222')).toBeInTheDocument()
  })

  it('el posible duplicado lista los candidatos y se confirma con confirmar_duplicado', async () => {
    const user = userEvent.setup()
    api.createPatient
      .mockRejectedValueOnce(
        new ApiError(409, 'patient_posible_duplicado', 'Datos parecidos.', null, {
          code: 'patient_posible_duplicado',
          candidatos: [CANDIDATO],
        }),
      )
      .mockResolvedValueOnce({
        ...ANA,
        id: 'p-3',
        numero_historia_clinica: '000003',
        nombre: 'Carla',
        apellido: 'Costa',
      })
    renderPage()
    await abrirAlta(user)

    await completarAlta(user, { nombre: 'Ana', apellido: 'Pérez', telefono: '11 5555-1234' })

    const dialogo = await screen.findByRole('dialog', { name: /posible duplicado/i })
    expect(within(dialogo).getByText(/000009/)).toBeInTheDocument()
    expect(within(dialogo).getByText(/11 5555-1234/)).toBeInTheDocument()

    await user.click(within(dialogo).getByRole('button', { name: /confirmar alta/i }))

    await waitFor(() =>
      expect(api.createPatient).toHaveBeenLastCalledWith(
        expect.objectContaining({ nombre: 'Ana', apellido: 'Pérez', confirmar_duplicado: true }),
      ),
    )
    await screen.findByRole('cell', { name: /costa, carla/i })
    expect(within(rowOf(/costa, carla/i)).getByText('000003')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('cancelar el posible duplicado no crea la ficha y conserva el formulario', async () => {
    const user = userEvent.setup()
    api.createPatient.mockRejectedValue(
      new ApiError(409, 'patient_posible_duplicado', 'Datos parecidos.', null, {
        code: 'patient_posible_duplicado',
        candidatos: [CANDIDATO],
      }),
    )
    renderPage()
    await abrirAlta(user)

    await completarAlta(user, { nombre: 'Ana', apellido: 'Pérez', telefono: '11 5555-1234' })

    const dialogo = await screen.findByRole('dialog', { name: /posible duplicado/i })
    await user.click(within(dialogo).getByRole('button', { name: /cancelar/i }))

    expect(screen.queryByRole('dialog', { name: /posible duplicado/i })).not.toBeInTheDocument()
    expect(screen.getByDisplayValue('Ana')).toBeInTheDocument()
    expect(api.createPatient).toHaveBeenCalledTimes(1)
  })

  it('rechaza un DNI con formato inválido antes de llamar al backend', async () => {
    const user = userEvent.setup()
    renderPage()
    await abrirAlta(user)

    await completarAlta(user, {
      nombre: 'Ana',
      apellido: 'Pérez',
      telefono: '11 5555-1234',
      dni: '30-111-222',
    })

    expect(await screen.findByText(/el dni debe tener entre 7 y 11 dígitos/i)).toBeInTheDocument()
    expect(api.createPatient).not.toHaveBeenCalled()
  })

  it('un 403 al crear se informa como falta de permisos', async () => {
    const user = userEvent.setup()
    api.createPatient.mockRejectedValue(new ApiError(403, 'forbidden', 'No autorizado.'))
    renderPage()
    await abrirAlta(user)

    await completarAlta(user, { nombre: 'Ana', apellido: 'Pérez', telefono: '11 5555-1234' })

    expect(await screen.findByText(/no tenés permiso para esta acción/i)).toBeInTheDocument()
  })
})

describe('PatientsPage — edición', () => {
  it('precarga la ficha y guarda los cambios con PATCH', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('cell', { name: /pérez, ana/i })

    await user.click(screen.getByRole('button', { name: /editar/i }))
    const dialogo = screen.getByRole('dialog', { name: /editar paciente/i })
    expect(within(dialogo).getByDisplayValue('Ana')).toBeInTheDocument()

    const telefono = within(dialogo).getByLabelText(/^teléfono$/i)
    await user.clear(telefono)
    await user.type(telefono, '11 4444-0000')
    await user.click(within(dialogo).getByRole('button', { name: /guardar paciente/i }))

    await waitFor(() =>
      expect(api.updatePatient).toHaveBeenCalledWith(
        'p-1',
        expect.objectContaining({ nombre: 'Ana', telefono: '11 4444-0000' }),
      ),
    )
    expect(await screen.findByText('11 4444-0000')).toBeInTheDocument()
  })
})
