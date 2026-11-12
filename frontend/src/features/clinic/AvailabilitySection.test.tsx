import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import * as clinicApi from '@/api/clinic'
import type { AvailabilityOut } from '@/api/clinic'
import { ApiError } from '@/api/http'
import { AuthProvider } from '@/features/auth/AuthProvider'
import AvailabilitySection from './AvailabilitySection'

vi.mock('@/api/auth')
vi.mock('@/api/clinic')

const auth = vi.mocked(authApi)
const clinic = vi.mocked(clinicApi)

function sessionWith(permissions: string[]): SessionOut {
  return {
    user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
    tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
    roles: ['owner'],
    permissions,
    mfa_enrolled: true,
  }
}

const REGLA: AvailabilityOut = {
  id: 'av-1',
  professional_id: null,
  chair_id: null,
  dia_semana: 1,
  hora_inicio: '09:00:00',
  hora_fin: '12:00:00',
  slot_min: 30,
  buffer_previo_min: 5,
  buffer_posterior_min: 5,
  fecha_desde: '2026-11-16',
  fecha_hasta: null,
  tipo_practica: null,
}

function renderSection(permissions: string[] = ['professional.read']) {
  auth.me.mockResolvedValue(sessionWith(permissions))
  return render(
    <MemoryRouter>
      <AuthProvider>
        <AvailabilitySection />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  clinic.listAvailability.mockResolvedValue({ availability: [REGLA] })
  clinic.listProfessionals.mockResolvedValue({ professionals: [] })
  clinic.listChairs.mockResolvedValue({ chairs: [] })
  clinic.createAvailability.mockResolvedValue({ ...REGLA, id: 'av-2' })
})

describe('AvailabilitySection', () => {
  it('lista día, horario, slot, buffers y vigencia', async () => {
    renderSection()

    expect(await screen.findByText('Lunes')).toBeInTheDocument()
    expect(screen.getByText('09:00–12:00')).toBeInTheDocument()
    expect(screen.getByText('30 min')).toBeInTheDocument()
    expect(screen.getByText('5/5 min')).toBeInTheDocument()
    expect(screen.getByText(/2026-11-16 en adelante/i)).toBeInTheDocument()
    expect(screen.getByText('Toda la clínica')).toBeInTheDocument()
  })

  it('muestra el alta solo con professional.update', async () => {
    const { unmount } = renderSection(['professional.read'])
    await screen.findByRole('cell', { name: 'Lunes' })
    expect(screen.queryByRole('button', { name: /nueva regla/i })).not.toBeInTheDocument()
    unmount()

    renderSection(['professional.read', 'professional.update'])
    await screen.findByRole('cell', { name: 'Lunes' })
    expect(screen.getByRole('button', { name: /nueva regla/i })).toBeInTheDocument()
  })

  it('crea una regla con los valores del formulario', async () => {
    const user = userEvent.setup()
    renderSection(['professional.read', 'professional.update'])
    await screen.findByRole('cell', { name: 'Lunes' })

    await user.selectOptions(screen.getByLabelText(/^día$/i), '2')
    fireEvent.change(screen.getByLabelText(/hora de inicio/i), { target: { value: '14:00' } })
    fireEvent.change(screen.getByLabelText(/hora de fin/i), { target: { value: '18:00' } })
    fireEvent.change(screen.getByLabelText(/vigente desde/i), { target: { value: '2026-11-17' } })
    await user.click(screen.getByRole('button', { name: /nueva regla/i }))

    await waitFor(() =>
      expect(clinic.createAvailability).toHaveBeenCalledWith({
        dia_semana: 2,
        hora_inicio: '14:00',
        hora_fin: '18:00',
        slot_min: 30,
        fecha_desde: '2026-11-17',
        fecha_hasta: null,
        professional_id: null,
        chair_id: null,
      }),
    )
    expect(await screen.findByText(/regla de disponibilidad creada/i)).toBeInTheDocument()
  })

  it('muestra el solape con su code', async () => {
    const user = userEvent.setup()
    renderSection(['professional.read', 'professional.update'])
    await screen.findByRole('cell', { name: 'Lunes' })
    clinic.createAvailability.mockRejectedValue(
      new ApiError(409, 'availability_overlap', 'Se superpone.'),
    )

    fireEvent.change(screen.getByLabelText(/vigente desde/i), { target: { value: '2026-11-17' } })
    await user.click(screen.getByRole('button', { name: /nueva regla/i }))

    expect(await screen.findByText(/se superpone con otra regla/i)).toBeInTheDocument()
    expect(screen.getByText('availability_overlap')).toBeInTheDocument()
  })
})
