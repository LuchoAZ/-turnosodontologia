import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import { ApiError } from '@/api/http'
import Home from '@/routes/Home'
import Login from '@/routes/Login'
import { AuthProvider } from './AuthProvider'
import RequireAuth from './RequireAuth'

vi.mock('@/api/auth')

const api = vi.mocked(authApi)

const SESSION: SessionOut = {
  user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
  tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
  roles: ['professional'],
  permissions: [],
  mfa_enrolled: true,
}

function renderApp(initialEntries: string[] = ['/']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<Home />} />
            <Route path="/turnos" element={<h1>Agenda de turnos</h1>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  api.me.mockRejectedValue(new ApiError(401, 'not_authenticated', 'No hay sesión.'))
  api.logout.mockResolvedValue(undefined)
})

describe('AuthProvider + RequireAuth', () => {
  it('restaura la sesión con /auth/me y renderiza la ruta protegida', async () => {
    api.me.mockResolvedValue(SESSION)

    renderApp()

    expect(await screen.findByText(/Clínica Demo/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /gestión odontológica/i })).toBeInTheDocument()
  })

  it('sin sesión redirige a /login', async () => {
    renderApp()

    expect(await screen.findByRole('heading', { name: /iniciar sesión/i })).toBeInTheDocument()
    expect(screen.queryByText(/Clínica Demo/)).not.toBeInTheDocument()
  })

  it('después del login vuelve al destino original', async () => {
    const user = userEvent.setup()
    api.login.mockResolvedValue(SESSION)
    renderApp(['/turnos'])

    await screen.findByRole('heading', { name: /iniciar sesión/i })
    await user.type(screen.getByLabelText(/clínica/i), 'clinica-demo')
    await user.type(screen.getByLabelText(/email/i), 'demo@example.test')
    await user.type(screen.getByLabelText(/contraseña/i), 'secreta-123')
    await user.click(screen.getByRole('button', { name: /ingresar/i }))

    expect(await screen.findByRole('heading', { name: /agenda de turnos/i })).toBeInTheDocument()
  })

  it('logout limpia la sesión y vuelve a /login', async () => {
    const user = userEvent.setup()
    api.me.mockResolvedValue(SESSION)
    renderApp()

    await screen.findByText(/Clínica Demo/)
    await user.click(screen.getByRole('button', { name: /salir/i }))

    expect(api.logout).toHaveBeenCalledTimes(1)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /iniciar sesión/i })).toBeInTheDocument(),
    )
    expect(screen.queryByText(/Clínica Demo/)).not.toBeInTheDocument()
  })
})

