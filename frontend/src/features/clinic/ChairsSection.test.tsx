import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import * as clinicApi from '@/api/clinic'
import type { ChairOut } from '@/api/clinic'
import { ApiError } from '@/api/http'
import { AuthProvider } from '@/features/auth/AuthProvider'
import ChairsSection from './ChairsSection'

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

const SILLON: ChairOut = {
  id: 'ch-1',
  nombre: 'Sillón 1',
  tipo: 'consultorio',
  ubicacion: 'Planta baja',
  equipamiento: null,
  activo: true,
}

function renderSection(permissions: string[] = ['chair.read']) {
  auth.me.mockResolvedValue(sessionWith(permissions))
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ChairsSection />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function rowOf(nombre: string): HTMLElement {
  const row = screen.getByText(nombre).closest('tr')
  if (row === null) throw new Error(`No hay fila para ${nombre}`)
  return row
}

beforeEach(() => {
  vi.resetAllMocks()
  clinic.listChairs.mockResolvedValue({ chairs: [SILLON] })
  clinic.createChair.mockResolvedValue({ ...SILLON, id: 'ch-2', nombre: 'Sillón 2' })
  clinic.updateChair.mockResolvedValue({ ...SILLON, nombre: 'Sillón 1 bis' })
  clinic.deactivateChair.mockResolvedValue(undefined)
})

describe('ChairsSection', () => {
  it('lista los sillones del tenant con su tipo y estado', async () => {
    renderSection()

    expect(await screen.findByText('Sillón 1')).toBeInTheDocument()
    const row = rowOf('Sillón 1')
    expect(within(row).getByText('Consultorio')).toBeInTheDocument()
    expect(within(row).getByText('Planta baja')).toBeInTheDocument()
    expect(within(row).getByText('Activo')).toBeInTheDocument()
  })

  it('muestra el alta solo con chair.create', async () => {
    const { unmount } = renderSection(['chair.read'])
    await screen.findByText('Sillón 1')
    expect(screen.queryByRole('button', { name: /nuevo sillón/i })).not.toBeInTheDocument()
    unmount()

    renderSection(['chair.read', 'chair.create'])
    await screen.findByText('Sillón 1')
    expect(screen.getByRole('button', { name: /nuevo sillón/i })).toBeInTheDocument()
  })

  it('muestra Guardar solo con chair.update y la baja solo con chair.delete', async () => {
    const { unmount } = renderSection(['chair.read'])
    await screen.findByText('Sillón 1')
    expect(screen.queryByRole('button', { name: /guardar/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /dar de baja/i })).not.toBeInTheDocument()
    unmount()

    renderSection(['chair.read', 'chair.update'])
    await screen.findByDisplayValue('Sillón 1')
    expect(screen.getByRole('button', { name: /guardar/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /dar de baja/i })).not.toBeInTheDocument()
    unmount()

    renderSection(['chair.read', 'chair.update', 'chair.delete'])
    await screen.findByDisplayValue('Sillón 1')
    expect(screen.getByRole('button', { name: /dar de baja/i })).toBeInTheDocument()
  })

  it('crea un sillón con la API y lo agrega a la tabla', async () => {
    const user = userEvent.setup()
    renderSection(['chair.read', 'chair.create'])
    await screen.findByText('Sillón 1')

    await user.type(screen.getByLabelText(/nombre del sillón/i), 'Sillón 2')
    await user.click(screen.getByRole('button', { name: /nuevo sillón/i }))

    await waitFor(() =>
      expect(clinic.createChair).toHaveBeenCalledWith({
        nombre: 'Sillón 2',
        tipo: 'consultorio',
        ubicacion: null,
      }),
    )
    expect(await screen.findByText('Sillón 2')).toBeInTheDocument()
    expect(await screen.findByText(/sillón creado/i)).toBeInTheDocument()
  })

  it('guarda los cambios del sillón con la API', async () => {
    const user = userEvent.setup()
    renderSection(['chair.read', 'chair.update'])
    const input = await screen.findByLabelText(/nombre de sillón 1/i)
    const row = input.closest('tr')
    if (row === null) throw new Error('No hay fila para el sillón')

    await user.clear(input)
    await user.type(input, 'Sillón 1 bis')
    await user.click(within(row).getByRole('button', { name: /guardar/i }))

    await waitFor(() =>
      expect(clinic.updateChair).toHaveBeenCalledWith('ch-1', {
        nombre: 'Sillón 1 bis',
        ubicacion: 'Planta baja',
      }),
    )
    expect(await screen.findByText(/sillón actualizado/i)).toBeInTheDocument()
  })

  it('un error de negocio se muestra con su code', async () => {
    const user = userEvent.setup()
    renderSection(['chair.read', 'chair.create'])
    await screen.findByText('Sillón 1')
    clinic.createChair.mockRejectedValue(
      new ApiError(409, 'chair_name_taken', 'El nombre ya existe.'),
    )

    await user.type(screen.getByLabelText(/nombre del sillón/i), 'Sillón 1')
    await user.click(screen.getByRole('button', { name: /nuevo sillón/i }))

    expect(await screen.findByText(/ya hay un sillón con ese nombre/i)).toBeInTheDocument()
    expect(screen.getByText('chair_name_taken')).toBeInTheDocument()
  })

  it('un 403 de la lista se muestra como acceso denegado', async () => {
    clinic.listChairs.mockRejectedValue(new ApiError(403, 'forbidden', 'No autorizado.'))

    renderSection()

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(screen.getByText('forbidden')).toBeInTheDocument()
  })
})
