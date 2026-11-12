import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import * as clinicApi from '@/api/clinic'
import type { ProfessionalOut } from '@/api/clinic'
import { ApiError } from '@/api/http'
import { AuthProvider } from '@/features/auth/AuthProvider'
import ProfessionalsSection from './ProfessionalsSection'

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

const PROFE: ProfessionalOut = {
  id: 'pr-1',
  user_id: null,
  nombre: 'Paula',
  apellido: 'Pérez',
  matricula: 'MP-1234',
  especialidad: { id: 'sp-orto', nombre: 'Ortodoncia' },
  duracion_default_min: 45,
  porcentaje_liquidacion: '40.00',
  color_agenda: '#2563EB',
  activo: true,
}

const CATALOG = [
  { id: 'sp-gen', nombre: 'Odontología general' },
  { id: 'sp-orto', nombre: 'Ortodoncia' },
]

function renderSection(permissions: string[] = ['professional.read']) {
  auth.me.mockResolvedValue(sessionWith(permissions))
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ProfessionalsSection />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function rowOf(texto: string | RegExp): HTMLElement {
  const row = screen.getByText(texto).closest('tr')
  if (row === null) throw new Error(`No hay fila para ${texto}`)
  return row
}

beforeEach(() => {
  vi.resetAllMocks()
  clinic.listProfessionals.mockResolvedValue({ professionals: [PROFE] })
  clinic.listSpecialties.mockResolvedValue({ specialties: CATALOG })
  clinic.createProfessional.mockResolvedValue({
    ...PROFE,
    id: 'pr-2',
    nombre: 'Bruno',
    apellido: 'Berra',
    matricula: 'MP-9999',
  })
  clinic.updateProfessional.mockResolvedValue({ ...PROFE, activo: false })
})

describe('ProfessionalsSection', () => {
  it('lista matrícula, especialidad, duración y liquidación', async () => {
    renderSection()

    expect(await screen.findByText(/paula pérez/i)).toBeInTheDocument()
    const row = rowOf(/paula pérez/i)
    expect(within(row).getByText('MP-1234')).toBeInTheDocument()
    expect(within(row).getByText('Ortodoncia')).toBeInTheDocument()
    expect(within(row).getByText('45 min')).toBeInTheDocument()
    expect(within(row).getByText('40%')).toBeInTheDocument()
  })

  it('muestra el alta solo con professional.create', async () => {
    const { unmount } = renderSection(['professional.read'])
    await screen.findByText(/paula pérez/i)
    expect(screen.queryByRole('button', { name: /nuevo profesional/i })).not.toBeInTheDocument()
    unmount()

    renderSection(['professional.read', 'professional.create'])
    await screen.findByText(/paula pérez/i)
    expect(screen.getByRole('button', { name: /nuevo profesional/i })).toBeInTheDocument()
  })

  it('el select de especialidad se llena con el catálogo y crea con ese id', async () => {
    const user = userEvent.setup()
    renderSection(['professional.read', 'professional.create'])
    await screen.findByText(/paula pérez/i)

    const select = screen.getByLabelText(/especialidad/i)
    // El catálogo llega en un efecto aparte: esperar las opciones antes de mirar.
    const options = await within(select).findAllByRole('option')
    expect(options).toHaveLength(2)
    expect(within(select).getByRole('option', { name: 'Odontología general' })).toBeInTheDocument()
    // El primer elemento del catálogo queda seleccionado: nunca un UUID fijo.
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe('sp-gen'))

    await user.selectOptions(select, 'sp-orto')
    await user.type(screen.getByLabelText(/^nombre$/i), 'Bruno')
    await user.type(screen.getByLabelText(/apellido/i), 'Berra')
    await user.type(screen.getByLabelText(/matrícula/i), 'MP-9999')
    await user.click(screen.getByRole('button', { name: /nuevo profesional/i }))

    await waitFor(() =>
      expect(clinic.createProfessional).toHaveBeenCalledWith({
        nombre: 'Bruno',
        apellido: 'Berra',
        matricula: 'MP-9999',
        especialidad_id: 'sp-orto',
        duracion_default_min: 30,
        porcentaje_liquidacion: 40,
      }),
    )
    expect(await screen.findByText(/profesional creado/i)).toBeInTheDocument()
  })

  it('muestra la matrícula repetida con su code', async () => {
    const user = userEvent.setup()
    renderSection(['professional.read', 'professional.create'])
    await screen.findByText(/paula pérez/i)
    clinic.createProfessional.mockRejectedValue(
      new ApiError(409, 'professional_matricula_taken', 'La matrícula ya existe.'),
    )

    await user.type(screen.getByLabelText(/^nombre$/i), 'Otra')
    await user.type(screen.getByLabelText(/apellido/i), 'Persona')
    await user.type(screen.getByLabelText(/matrícula/i), 'MP-1234')
    await user.click(screen.getByRole('button', { name: /nuevo profesional/i }))

    expect(await screen.findByText(/ya hay un profesional con esa matrícula/i)).toBeInTheDocument()
    expect(screen.getByText('professional_matricula_taken')).toBeInTheDocument()
  })

  it('la baja se ofrece solo con professional.update y usa activo=false', async () => {
    const user = userEvent.setup()
    const { unmount } = renderSection(['professional.read'])
    await screen.findByText(/paula pérez/i)
    expect(screen.queryByRole('button', { name: /dar de baja/i })).not.toBeInTheDocument()
    unmount()

    renderSection(['professional.read', 'professional.update'])
    await screen.findByText(/paula pérez/i)
    await user.click(screen.getByRole('button', { name: /dar de baja/i }))

    await waitFor(() => expect(clinic.updateProfessional).toHaveBeenCalledWith('pr-1', { activo: false }))
    expect(await screen.findByText(/profesional dado de baja/i)).toBeInTheDocument()
    expect(within(rowOf(/paula pérez/i)).getByText('Inactivo')).toBeInTheDocument()
  })
})
