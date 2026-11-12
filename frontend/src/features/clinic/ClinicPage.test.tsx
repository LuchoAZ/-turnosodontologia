import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import * as clinicApi from '@/api/clinic'
import { ApiError } from '@/api/http'
import { AuthProvider } from '@/features/auth/AuthProvider'
import RequirePermission from '@/features/auth/RequirePermission'
import ClinicPage from './ClinicPage'

vi.mock('@/api/auth')
vi.mock('@/api/clinic')

const auth = vi.mocked(authApi)
const clinic = vi.mocked(clinicApi)

function sessionWith(permissions: string[]): SessionOut {
  return {
    user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
    tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
    roles: ['clinical_admin'],
    permissions,
    mfa_enrolled: true,
  }
}

function renderPage(permissions: string[]) {
  auth.me.mockResolvedValue(sessionWith(permissions))
  return render(
    <MemoryRouter initialEntries={['/clinica']}>
      <AuthProvider>
        <RequirePermission permission="chair.read">
          <ClinicPage />
        </RequirePermission>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  clinic.listChairs.mockResolvedValue({
    chairs: [
      {
        id: 'ch-1',
        nombre: 'Sillón 1',
        tipo: 'consultorio',
        ubicacion: null,
        equipamiento: null,
        activo: true,
      },
    ],
  })
  clinic.listProfessionals.mockResolvedValue({
    professionals: [
      {
        id: 'pr-1',
        user_id: null,
        nombre: 'Paula',
        apellido: 'Pérez',
        matricula: 'MP-1234',
        especialidad: { id: 'sp-orto', nombre: 'Ortodoncia' },
        duracion_default_min: 30,
        porcentaje_liquidacion: '40.00',
        color_agenda: '#2563EB',
        activo: true,
      },
    ],
  })
  clinic.listSpecialties.mockResolvedValue({
    specialties: [{ id: 'sp-orto', nombre: 'Ortodoncia' }],
  })
  clinic.listAvailability.mockResolvedValue({
    availability: [
      {
        id: 'av-1',
        professional_id: null,
        chair_id: null,
        dia_semana: 1,
        hora_inicio: '09:00:00',
        hora_fin: '12:00:00',
        slot_min: 30,
        buffer_previo_min: 0,
        buffer_posterior_min: 0,
        fecha_desde: '2026-11-16',
        fecha_hasta: null,
        tipo_practica: null,
      },
    ],
  })
})

describe('ClinicPage', () => {
  it('con chair.read lista sillones, profesionales y disponibilidad', async () => {
    renderPage(['chair.read', 'professional.read'])

    expect(await screen.findByText('Sillones')).toBeInTheDocument()
    expect(await screen.findByText('Profesionales')).toBeInTheDocument()
    expect(await screen.findByText('Disponibilidad')).toBeInTheDocument()
    expect(await screen.findByText('MP-1234')).toBeInTheDocument()
    expect(await screen.findByText('09:00–12:00')).toBeInTheDocument()
  })

  it('sin chair.read no muestra la pantalla ni llama a la API', async () => {
    renderPage(['professional.read'])

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(clinic.listChairs).not.toHaveBeenCalled()
  })

  it('clinical_admin ve Nuevo sillón y Guardar pero no la baja', async () => {
    clinic.listProfessionals.mockResolvedValue({ professionals: [] })
    renderPage(['chair.read', 'chair.create', 'chair.update', 'professional.read'])

    expect(await screen.findByRole('button', { name: /nuevo sillón/i })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /guardar/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /dar de baja/i })).not.toBeInTheDocument()
  })

  it('un 403 de la API se muestra como acceso denegado con su code', async () => {
    clinic.listChairs.mockRejectedValue(new ApiError(403, 'forbidden', 'No autorizado.'))

    renderPage(['chair.read', 'professional.read'])

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(screen.getByText('forbidden')).toBeInTheDocument()
  })
})
