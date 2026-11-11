import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import { ApiError } from '@/api/http'
import * as teamApi from '@/api/team'
import App from './App'

vi.mock('@/api/auth')
vi.mock('@/api/team')

const api = vi.mocked(authApi)
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
})
