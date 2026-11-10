import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import { ApiError } from '@/api/http'
import App from './App'

vi.mock('@/api/auth')

const api = vi.mocked(authApi)

const SESSION: SessionOut = {
  user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
  tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
  roles: ['professional'],
  mfa_enrolled: true,
}

beforeEach(() => {
  vi.resetAllMocks()
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
})
