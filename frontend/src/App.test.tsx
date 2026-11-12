import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import * as clinicApi from '@/api/clinic'
import { ApiError } from '@/api/http'
import * as patientsApi from '@/api/patients'
import * as teamApi from '@/api/team'
import App from './App'

vi.mock('@/api/auth')
vi.mock('@/api/clinic')
vi.mock('@/api/patients')
vi.mock('@/api/team')

const api = vi.mocked(authApi)
const clinic = vi.mocked(clinicApi)
const patients = vi.mocked(patientsApi)
const team = vi.mocked(teamApi)

const SESSION: SessionOut = {
  user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
  tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
  roles: ['professional'],
  permissions: [],
  mfa_enrolled: true,
}

beforeEach(() => {
  vi.resetAllMocks()
  team.listMembers.mockResolvedValue({ members: [] })
  clinic.listChairs.mockResolvedValue({ chairs: [] })
  clinic.listProfessionals.mockResolvedValue({ professionals: [] })
  clinic.listSpecialties.mockResolvedValue({ specialties: [] })
  clinic.listAvailability.mockResolvedValue({ availability: [] })
  patients.listPatients.mockResolvedValue({ patients: [], total: 0 })
})

describe('App', () => {
  it('sin sesión redirige de / a /login', async () => {
    api.me.mockRejectedValue(new ApiError(401, 'not_authenticated', 'No hay sesión.'))

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: /iniciar sesión/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /gestión odontológica/i })).not.toBeInTheDocument()
  })

  it('con sesión válida muestra la home', async () => {
    api.me.mockResolvedValue(SESSION)

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: /gestión odontológica/i })).toBeInTheDocument()
    expect(screen.getByText(/Clínica Demo/)).toBeInTheDocument()
  })

  it('sin team.read la ruta /equipo muestra el acceso denegado', async () => {
    api.me.mockResolvedValue(SESSION)

    render(
      <MemoryRouter initialEntries={['/equipo']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(team.listMembers).not.toHaveBeenCalled()
  })

  it('con team.read la ruta /equipo renderiza la pantalla de equipo', async () => {
    api.me.mockResolvedValue({ ...SESSION, permissions: ['team.read'] })

    render(
      <MemoryRouter initialEntries={['/equipo']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: /^equipo$/i })).toBeInTheDocument()
    expect(await screen.findByText(/todavía no hay miembros/i)).toBeInTheDocument()
  })

  it('sin chair.read la ruta /clinica muestra el acceso denegado', async () => {
    api.me.mockResolvedValue({ ...SESSION, permissions: ['professional.read'] })

    render(
      <MemoryRouter initialEntries={['/clinica']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(clinic.listChairs).not.toHaveBeenCalled()
  })

  it('con chair.read la ruta /clinica renderiza la pantalla de la clínica', async () => {
    api.me.mockResolvedValue({ ...SESSION, permissions: ['chair.read'] })

    render(
      <MemoryRouter initialEntries={['/clinica']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Sillones')).toBeInTheDocument()
    expect(await screen.findByText(/todavía no hay sillones/i)).toBeInTheDocument()
  })

  it('sin patient.read la ruta /pacientes muestra el acceso denegado y no pide datos', async () => {
    api.me.mockResolvedValue({ ...SESSION, permissions: ['chair.read'] })

    render(
      <MemoryRouter initialEntries={['/pacientes']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(patients.listPatients).not.toHaveBeenCalled()
  })

  it('con patient.read la ruta /pacientes renderiza la pantalla de pacientes', async () => {
    api.me.mockResolvedValue({ ...SESSION, permissions: ['patient.read'] })

    render(
      <MemoryRouter initialEntries={['/pacientes']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: /^pacientes$/i })).toBeInTheDocument()
    expect(await screen.findByText(/no hay pacientes para mostrar/i)).toBeInTheDocument()
    expect(patients.listPatients).toHaveBeenCalledWith({ q: '' })
  })

  it('la home enlaza a /pacientes solo con patient.read', async () => {    api.me.mockResolvedValue({ ...SESSION, permissions: ['patient.read'] })

    const { unmount } = render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('link', { name: /pacientes/i })).toBeInTheDocument()
    unmount()

    api.me.mockResolvedValue({ ...SESSION, permissions: [] })
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: /gestión odontológica/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /pacientes/i })).not.toBeInTheDocument()
  })

  it('sin appointment.create la ruta /turnos/nuevo muestra el acceso denegado y no pide datos', async () => {
    api.me.mockResolvedValue({ ...SESSION, permissions: ['patient.read'] })

    render(
      <MemoryRouter initialEntries={['/turnos/nuevo']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(clinic.listProfessionals).not.toHaveBeenCalled()
    expect(clinic.listChairs).not.toHaveBeenCalled()
    expect(patients.listPatients).not.toHaveBeenCalled()
  })

  it('con appointment.create la ruta /turnos/nuevo renderiza el formulario de alta', async () => {
    api.me.mockResolvedValue({
      ...SESSION,
      roles: ['front_desk'],
      permissions: ['appointment.create', 'patient.read', 'professional.read', 'chair.read'],
    })

    render(
      <MemoryRouter initialEntries={['/turnos/nuevo']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: /nuevo turno/i })).toBeInTheDocument()
    expect(await screen.findByLabelText(/profesional/i)).toBeInTheDocument()
    expect(await screen.findByLabelText(/sillón/i)).toBeInTheDocument()
  })

  it('la home enlaza a /turnos/nuevo solo con appointment.create', async () => {
    api.me.mockResolvedValue({ ...SESSION, roles: ['front_desk'], permissions: ['appointment.create'] })

    const { unmount } = render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('link', { name: /agendar turno/i })).toBeInTheDocument()
    unmount()

    api.me.mockResolvedValue({ ...SESSION, permissions: ['patient.read'] })
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: /gestión odontológica/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /agendar turno/i })).not.toBeInTheDocument()
  })
})
