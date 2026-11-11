import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import { AuthProvider } from '@/features/auth/AuthProvider'
import Home from './Home'

vi.mock('@/api/auth')

const api = vi.mocked(authApi)

function sessionWith(permissions: string[]): SessionOut {
  return {
    user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
    tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
    roles: ['front_desk'],
    permissions,
    mfa_enrolled: true,
  }
}

function renderHome(permissions: string[]) {
  api.me.mockResolvedValue(sessionWith(permissions))
  return render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Home />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
})

describe('Home', () => {
  it('muestra el enlace Equipo cuando la sesión tiene team.read', async () => {
    renderHome(['team.read'])

    expect(await screen.findByRole('link', { name: /equipo/i })).toBeInTheDocument()
  })

  it('oculta el enlace Equipo sin team.read', async () => {
    renderHome(['chart.read'])

    expect(await screen.findByRole('heading', { name: /gestión odontológica/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /equipo/i })).not.toBeInTheDocument()
  })
})
