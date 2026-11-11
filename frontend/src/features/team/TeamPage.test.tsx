import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import { ApiError } from '@/api/http'
import * as teamApi from '@/api/team'
import type { MemberOut } from '@/api/team'
import { AuthProvider } from '@/features/auth/AuthProvider'
import TeamPage from './TeamPage'

vi.mock('@/api/auth')
vi.mock('@/api/team')

const auth = vi.mocked(authApi)
const team = vi.mocked(teamApi)

const OWNER_PERMISSIONS = [
  'team.read',
  'team.create',
  'team.update',
  'team.delete',
  'ownership.transfer',
]

function sessionWith(permissions: string[]): SessionOut {
  return {
    user: { id: 'u-owner', email: 'owner@example.test', nombre: 'Olivia', apellido: 'Owner' },
    tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
    roles: ['owner'],
    permissions,
    mfa_enrolled: true,
  }
}

const OWNER: MemberOut = {
  id: 'm-owner',
  user_id: 'u-owner',
  email: 'owner@example.test',
  nombre: 'Olivia',
  apellido: 'Owner',
  rol: 'owner',
  activo: true,
  professional_id: null,
}

const PROFE: MemberOut = {
  id: 'm-profe',
  user_id: 'u-profe',
  email: 'profe@example.test',
  nombre: 'Paula',
  apellido: 'Pérez',
  rol: 'professional',
  activo: true,
  professional_id: null,
}

const MEMBERS: MemberOut[] = [OWNER, PROFE]

function renderPage(permissions: string[] = OWNER_PERMISSIONS) {
  auth.me.mockResolvedValue(sessionWith(permissions))
  return render(
    <MemoryRouter initialEntries={['/equipo']}>
      <AuthProvider>
        <TeamPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function rowOf(email: string): HTMLElement {
  const row = screen.getByText(email).closest('tr')
  if (row === null) throw new Error(`No hay fila para ${email}`)
  return row
}

beforeEach(() => {
  vi.resetAllMocks()
  team.listMembers.mockResolvedValue({ members: MEMBERS })
  team.changeRole.mockResolvedValue({ ...PROFE, rol: 'clinical_admin' })
  team.deactivateMember.mockResolvedValue(undefined)
  team.transferOwnership.mockResolvedValue({
    members: MEMBERS.map((member) =>
      member.id === 'm-profe' ? { ...member, rol: 'owner' } : { ...member, rol: 'clinical_admin' },
    ),
  })
})

describe('TeamPage', () => {
  it('lista los miembros del tenant con su rol y estado', async () => {
    renderPage()

    expect(await screen.findByText('owner@example.test')).toBeInTheDocument()
    expect(screen.getByText('profe@example.test')).toBeInTheDocument()
    expect(within(rowOf('owner@example.test')).getByText('owner')).toBeInTheDocument()
    expect(within(rowOf('profe@example.test')).getByText('professional')).toBeInTheDocument()
    expect(screen.getAllByText(/activo/i).length).toBeGreaterThan(0)
  })

  it('muestra el control de cambio de rol solo con team.update', async () => {
    const { unmount } = renderPage(['team.read'])
    await screen.findByText('profe@example.test')
    expect(screen.queryByRole('button', { name: /guardar rol/i })).not.toBeInTheDocument()
    unmount()

    renderPage(['team.read', 'team.update'])
    await screen.findByText('profe@example.test')
    expect(screen.getAllByRole('button', { name: /guardar rol/i }).length).toBeGreaterThan(0)
  })

  it('muestra dar de baja solo con team.delete', async () => {
    const { unmount } = renderPage(['team.read', 'team.update'])
    await screen.findByText('profe@example.test')
    expect(screen.queryByRole('button', { name: /dar de baja/i })).not.toBeInTheDocument()
    unmount()

    renderPage(['team.read', 'team.delete'])
    await screen.findByText('profe@example.test')
    expect(screen.getAllByRole('button', { name: /dar de baja/i }).length).toBeGreaterThan(0)
  })

  it('muestra transferir titularidad solo con ownership.transfer', async () => {
    const { unmount } = renderPage(['team.read', 'team.update'])
    await screen.findByText('profe@example.test')
    expect(
      screen.queryByRole('button', { name: /transferir titularidad/i }),
    ).not.toBeInTheDocument()
    unmount()

    renderPage(['team.read', 'ownership.transfer'])
    await screen.findByText('profe@example.test')
    expect(
      screen.getAllByRole('button', { name: /transferir titularidad/i }).length,
    ).toBeGreaterThan(0)
  })

  it('un 403 de la API se mapea a la pantalla de acceso denegado con su code', async () => {
    team.listMembers.mockRejectedValue(new ApiError(403, 'forbidden', 'No autorizado.'))

    renderPage(['team.read'])

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(screen.getByText('forbidden')).toBeInTheDocument()
  })

  it('cambia el rol con la API y refleja el resultado', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('profe@example.test')

    const row = rowOf('profe@example.test')
    await user.selectOptions(within(row).getByLabelText(/rol de profe@example\.test/i), 'clinical_admin')
    await user.click(within(row).getByRole('button', { name: /guardar rol/i }))

    await waitFor(() =>
      expect(team.changeRole).toHaveBeenCalledWith('m-profe', 'clinical_admin'),
    )
    expect(await screen.findByText(/rol actualizado/i)).toBeInTheDocument()
    expect(within(rowOf('profe@example.test')).getByText('clinical_admin')).toBeInTheDocument()
  })

  it('da de baja con la API y marca al miembro como inactivo', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('profe@example.test')
    team.listMembers.mockResolvedValueOnce({
      members: MEMBERS.map((member) =>
        member.id === 'm-profe' ? { ...member, activo: false } : member,
      ),
    })

    await user.click(within(rowOf('profe@example.test')).getByRole('button', { name: /dar de baja/i }))

    await waitFor(() => expect(team.deactivateMember).toHaveBeenCalledWith('m-profe'))
    expect(await screen.findByText(/miembro dado de baja/i)).toBeInTheDocument()
    expect(within(rowOf('profe@example.test')).getByText(/inactivo/i)).toBeInTheDocument()
  })

  it('un error de negocio de la API se muestra con su code', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('owner@example.test')
    team.deactivateMember.mockRejectedValue(
      new ApiError(409, 'last_owner', 'La clínica necesita un owner activo.'),
    )

    await user.click(within(rowOf('owner@example.test')).getByRole('button', { name: /dar de baja/i }))

    expect(await screen.findByText(/last_owner/)).toBeInTheDocument()
  })
})
