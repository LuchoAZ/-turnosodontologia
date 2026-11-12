import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as appointmentsApi from '@/api/appointments'
import type { AppointmentOut } from '@/api/appointments'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import * as clinicApi from '@/api/clinic'
import { ApiError } from '@/api/http'
import * as patientsApi from '@/api/patients'
import type { PatientOut } from '@/api/patients'
import { AuthProvider } from '@/features/auth/AuthProvider'
import NewAppointmentPage from './NewAppointmentPage'
import { localDateTimeToInstant } from './datetime'

vi.mock('@/api/auth')
vi.mock('@/api/patients')
vi.mock('@/api/clinic', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/clinic')>()
  return {
    ...actual,
    listProfessionals: vi.fn(),
    listChairs: vi.fn(),
    listSpecialties: vi.fn(),
    listAvailability: vi.fn(),
  }
})
vi.mock('@/api/appointments', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/appointments')>()
  return { ...actual, createAppointment: vi.fn() }
})

const auth = vi.mocked(authApi)
const clinic = vi.mocked(clinicApi)
const patients = vi.mocked(patientsApi)
const agenda = vi.mocked(appointmentsApi)

const FECHA = '2026-11-16'
const HORA = '09:00'
const INICIO = localDateTimeToInstant(FECHA, HORA) as string
const FIN = localDateTimeToInstant(FECHA, '09:30') as string

function sessionWith(permissions: string[]): SessionOut {
  return {
    user: { id: 'u-1', email: 'desk@example.test', nombre: 'Fran', apellido: 'Recepción' },
    tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
    roles: ['front_desk'],
    permissions,
    mfa_enrolled: false,
  }
}

const PERMISOS = ['appointment.create', 'patient.read', 'professional.read', 'chair.read']

const PAULA = {
  id: 'prof-1',
  user_id: 'u-2',
  nombre: 'Paula',
  apellido: 'Profesional',
  matricula: 'MP-1',
  especialidad: { id: 'esp-1', nombre: 'Odontología general' },
  duracion_default_min: 30,
  porcentaje_liquidacion: 40,
  color_agenda: '#2563EB',
  activo: true,
}

const ANA: PatientOut = {
  id: 'pat-1',
  numero_historia_clinica: '000001',
  nombre: 'Ana',
  apellido: 'Pérez',
  dni: '30111222',
  fecha_nacimiento: null,
  sexo: null,
  telefono: '11 5555-1234',
  email: null,
  domicilio: null,
  activo: true,
  created_at: '2026-11-12T00:00:00Z',
  updated_at: '2026-11-12T00:00:00Z',
}

const CREADO: AppointmentOut = {
  id: 'apt-1',
  professional_id: 'prof-1',
  chair_id: 'chair-1',
  patient_id: 'pat-1',
  inicio: INICIO,
  fin: FIN,
  duracion_min: 30,
  buffer_previo_min: 0,
  buffer_posterior_min: 0,
  estado: 'pendiente',
  origen: 'recepcion',
  tipo_practica: null,
}

function renderPage(permissions: string[] = PERMISOS) {
  auth.me.mockResolvedValue(sessionWith(permissions))
  return render(
    <MemoryRouter>
      <AuthProvider>
        <NewAppointmentPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

async function completarFormulario(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByLabelText(/profesional/i)
  await user.selectOptions(screen.getByLabelText(/profesional/i), 'prof-1')
  await user.selectOptions(screen.getByLabelText(/sillón/i), 'chair-1')
  await user.selectOptions(screen.getByLabelText(/paciente/i), 'pat-1')
  fireEvent.change(screen.getByLabelText(/fecha/i), { target: { value: FECHA } })
  fireEvent.change(screen.getByLabelText(/hora/i), { target: { value: HORA } })
  await user.click(screen.getByRole('button', { name: /guardar turno/i }))
}

beforeEach(() => {
  vi.resetAllMocks()
  patients.listPatients.mockResolvedValue({ patients: [ANA], total: 1 })
  clinic.listProfessionals.mockResolvedValue({ professionals: [PAULA] })
  clinic.listChairs.mockResolvedValue({
    chairs: [
      { id: 'chair-1', nombre: 'Sillón A', tipo: 'consultorio', ubicacion: null, equipamiento: null, activo: true },
      { id: 'chair-2', nombre: 'Sillón baja', tipo: 'consultorio', ubicacion: null, equipamiento: null, activo: false },
    ],
  })
  agenda.createAppointment.mockResolvedValue(CREADO)
})

describe('NewAppointmentPage — carga de opciones', () => {
  it('pide pacientes, profesionales y sillones en paralelo', async () => {
    renderPage()

    await screen.findByLabelText(/profesional/i)
    expect(patients.listPatients).toHaveBeenCalledTimes(1)
    expect(clinic.listProfessionals).toHaveBeenCalledTimes(1)
    expect(clinic.listChairs).toHaveBeenCalledTimes(1)
  })

  it('solo ofrece profesionales y sillones activos', async () => {
    renderPage()
    await screen.findByLabelText(/sillón/i)

    const sillones = screen.getByLabelText(/sillón/i) as HTMLSelectElement
    expect(within(sillones).queryByText('Sillón baja')).not.toBeInTheDocument()
    expect(within(sillones).getByText('Sillón A')).toBeInTheDocument()
  })
})

describe('NewAppointmentPage — alta (criterio 4)', () => {
  it('crea el turno con el inicio en UTC y sin fin ni duración', async () => {
    const user = userEvent.setup()
    renderPage()
    await completarFormulario(user)

    await waitFor(() =>
      expect(agenda.createAppointment).toHaveBeenCalledWith({
        professional_id: 'prof-1',
        chair_id: 'chair-1',
        patient_id: 'pat-1',
        inicio: INICIO,
      }),
    )
    expect(INICIO.endsWith('Z')).toBe(true)
    const [llamada] = agenda.createAppointment.mock.calls
    expect(llamada).toBeDefined()
    const enviado = (llamada as unknown as [{ [clave: string]: unknown }])[0]
    expect(enviado).not.toHaveProperty('fin')
    expect(enviado).not.toHaveProperty('duracion_min')
    expect(enviado).not.toHaveProperty('estado')
  })

  it('muestra el turno creado con su fin y su duración derivados', async () => {
    const user = userEvent.setup()
    renderPage()
    await completarFormulario(user)

    const confirmacion = await screen.findByRole('status')
    expect(confirmacion).toHaveTextContent(/turno creado/i)
    expect(confirmacion).toHaveTextContent(/30 min/i)
    expect(confirmacion.textContent).toMatch(/09:00/)
    expect(confirmacion.textContent).toMatch(/09:30/)
  })

  it('sin paciente identificado manda patient_id nulo (RN-AG-10 no aplica)', async () => {
    const user = userEvent.setup()
    agenda.createAppointment.mockResolvedValue({ ...CREADO, patient_id: null })
    renderPage()
    await screen.findByLabelText(/profesional/i)
    await user.selectOptions(screen.getByLabelText(/profesional/i), 'prof-1')
    await user.selectOptions(screen.getByLabelText(/sillón/i), 'chair-1')
    fireEvent.change(screen.getByLabelText(/fecha/i), { target: { value: FECHA } })
    fireEvent.change(screen.getByLabelText(/hora/i), { target: { value: HORA } })
    await user.click(screen.getByRole('button', { name: /guardar turno/i }))

    await waitFor(() =>
      expect(agenda.createAppointment).toHaveBeenCalledWith(
        expect.objectContaining({ patient_id: null }),
      ),
    )
  })

  it('valida en el cliente y no llama a la API si faltan datos', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByLabelText(/profesional/i)

    await user.click(screen.getByRole('button', { name: /guardar turno/i }))

    // El mensaje de error se distingue del placeholder del `<option>` por el punto.
    expect(await screen.findByText(/^Elegí un profesional\.$/)).toBeInTheDocument()
    expect(screen.getByText(/^Elegí un sillón\.$/)).toBeInTheDocument()
    expect(agenda.createAppointment).not.toHaveBeenCalled()
  })

  it('rechaza una fecha inexistente antes de llamar a la API', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByLabelText(/profesional/i)
    await user.selectOptions(screen.getByLabelText(/profesional/i), 'prof-1')
    await user.selectOptions(screen.getByLabelText(/sillón/i), 'chair-1')
    fireEvent.change(screen.getByLabelText(/fecha/i), { target: { value: '2026-02-31' } })
    fireEvent.change(screen.getByLabelText(/hora/i), { target: { value: HORA } })
    await user.click(screen.getByRole('button', { name: /guardar turno/i }))

    const mensaje = await screen.findByText(
      /la fecha y hora no son válidas|elegí la fecha/i,
    )
    expect(mensaje).toBeInTheDocument()
    expect(agenda.createAppointment).not.toHaveBeenCalled()
  })
})

describe('NewAppointmentPage — errores del contrato (409/422/404)', () => {
  it('un 409 de solape muestra el recurso y el rango en conflicto', async () => {
    const user = userEvent.setup()
    agenda.createAppointment.mockRejectedValue(
      new ApiError(409, 'turno_solapado', 'El horario se solapa con otro turno.', null, {
        code: 'turno_solapado',
        recurso: 'professional',
        motivo: 'turno_solapado',
        rangoEnConflicto: { inicio: INICIO, fin: FIN },
      }),
    )
    renderPage()
    await completarFormulario(user)

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent(/se solapa con otro turno/i)
    expect(alerta).toHaveTextContent(/profesional/i)
    expect(alerta.textContent).toMatch(/09:00/)
    expect(alerta.textContent).toMatch(/09:30/)
    expect(within(alerta).getByText('turno_solapado')).toBeInTheDocument()
  })

  it('un 409 de paciente solapado tiene su propio mensaje (RN-AG-10)', async () => {
    const user = userEvent.setup()
    agenda.createAppointment.mockRejectedValue(
      new ApiError(409, 'paciente_solapado', 'El paciente ya tiene un turno.', null, {
        code: 'paciente_solapado',
        recurso: 'patient',
        motivo: 'paciente_solapado',
        rangoEnConflicto: { inicio: INICIO, fin: FIN },
      }),
    )
    renderPage()
    await completarFormulario(user)

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent(/ya tiene un turno con ese profesional/i)
    expect(alerta).toHaveTextContent(/paciente/i)
  })

  it('un 404 se informa como recurso inexistente o sin acceso', async () => {
    const user = userEvent.setup()
    agenda.createAppointment.mockRejectedValue(
      new ApiError(404, 'recurso_no_encontrado', 'No existe.', null, {
        code: 'recurso_no_encontrado',
        recurso: 'chair',
        motivo: 'recurso_no_encontrado',
      }),
    )
    renderPage()
    await completarFormulario(user)

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent(/no existe en esta clínica o no tenés acceso/i)
    expect(within(alerta).getByText('recurso_no_encontrado')).toBeInTheDocument()
  })

  it('un 422 se informa como datos inválidos sin romper el formulario', async () => {
    const user = userEvent.setup()
    agenda.createAppointment.mockRejectedValue(
      new ApiError(422, 'invalid_request', 'Petición inválida.'),
    )
    renderPage()
    await completarFormulario(user)

    expect(await screen.findByText(/revisá los datos/i)).toBeInTheDocument()
    // Los valores cargados se conservan para corregir sin volver a escribir todo.
    expect(screen.getByLabelText(/profesional/i)).toHaveValue('prof-1')
  })

  it('un 403 se informa como falta de permisos', async () => {
    const user = userEvent.setup()
    agenda.createAppointment.mockRejectedValue(new ApiError(403, 'forbidden', 'No autorizado.'))
    renderPage()
    await completarFormulario(user)

    expect(await screen.findByText(/no tenés permiso para esta acción/i)).toBeInTheDocument()
  })
})

describe('NewAppointmentPage — permisos (criterio 3)', () => {
  it('sin appointment.create muestra sin permisos y no pide las opciones', async () => {
    renderPage(['patient.read'])

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(patients.listPatients).not.toHaveBeenCalled()
    expect(clinic.listProfessionals).not.toHaveBeenCalled()
    expect(clinic.listChairs).not.toHaveBeenCalled()
  })

  it('un 403 al cargar las opciones se informa como falta de permisos', async () => {
    patients.listPatients.mockRejectedValue(new ApiError(403, 'forbidden', 'No autorizado.'))
    renderPage()

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
  })
})
