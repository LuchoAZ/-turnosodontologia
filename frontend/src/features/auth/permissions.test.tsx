import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import { ApiError } from '@/api/http'
import { AuthProvider } from './AuthProvider'
import RequireAuth from './RequireAuth'
import RequirePermission from './RequirePermission'
import { useAuth } from './context'

vi.mock('@/api/auth')

const api = vi.mocked(authApi)

const SESSION: SessionOut = {
  user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
  tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
  roles: ['owner'],
  permissions: ['team.read', 'team.update', 'team.create', 'team.delete', 'ownership.transfer'],
  mfa_enrolled: true,
}

const LIMITED: SessionOut = {
  ...SESSION,
  roles: ['front_desk'],
  permissions: [],
}

function Probe() {
  const { hasPermission } = useAuth()
  return (
    <ul>
      <li>team.read: {String(hasPermission('team.read'))}</li>
      <li>team.delete: {String(hasPermission('team.delete'))}</li>
      <li>ownership.transfer: {String(hasPermission('ownership.transfer'))}</li>
    </ul>
  )
}

function renderProbe() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function renderProtected(permission = 'team.read', code: string | null = null) {
  return render(
    <MemoryRouter initialEntries={['/equipo']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<h1>Iniciar sesión</h1>} />
          <Route element={<RequireAuth />}>
            <Route
              path="/equipo"
              element={
                <RequirePermission permission={permission} code={code}>
                  <h1>Equipo</h1>
                </RequirePermission>
              }
            />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  api.me.mockRejectedValue(new ApiError(401, 'not_authenticated', 'No hay sesión.'))
})

describe('hasPermission', () => {
  it('devuelve true para un permiso presente en la sesión', async () => {
    api.me.mockResolvedValue(SESSION)

    renderProbe()

    expect(await screen.findByText(/team\.read: true/)).toBeInTheDocument()
    expect(screen.getByText(/ownership\.transfer: true/)).toBeInTheDocument()
  })

  it('devuelve false para un permiso ausente', async () => {
    api.me.mockResolvedValue({ ...SESSION, permissions: ['team.read'] })

    renderProbe()

    expect(await screen.findByText(/team\.read: true/)).toBeInTheDocument()
    expect(screen.getByText(/team\.delete: false/)).toBeInTheDocument()
  })

  it('sin sesión todos los permisos son false y no rompe', async () => {
    renderProbe()

    expect(await screen.findByText(/team\.read: false/)).toBeInTheDocument()
    expect(screen.getByText(/ownership\.transfer: false/)).toBeInTheDocument()
  })
})

describe('RequirePermission', () => {
  it('con el permiso renderiza el contenido', async () => {
    api.me.mockResolvedValue(SESSION)

    renderProtected()

    expect(await screen.findByRole('heading', { name: /^equipo$/i })).toBeInTheDocument()
    expect(screen.queryByText(/no tenés permiso/i)).not.toBeInTheDocument()
  })

  it('sin el permiso renderiza el acceso denegado y muestra el code de la API', async () => {
    api.me.mockResolvedValue(LIMITED)

    renderProtected('team.read', 'forbidden')

    expect(await screen.findByText(/no tenés permiso para ver esta sección/i)).toBeInTheDocument()
    expect(screen.getByText('forbidden')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^equipo$/i })).not.toBeInTheDocument()
  })

  it('sin sesión delega en RequireAuth y redirige a /login', async () => {
    renderProtected()

    expect(await screen.findByRole('heading', { name: /iniciar sesión/i })).toBeInTheDocument()
    expect(screen.queryByText(/no tenés permiso/i)).not.toBeInTheDocument()
  })
})

describe('reloadSession', () => {
  it('vuelve a pedir /auth/me y actualiza la sesión', async () => {
    const user = userEvent.setup()
    api.me.mockResolvedValueOnce(SESSION).mockResolvedValueOnce({
      ...SESSION,
      tenant: { ...SESSION.tenant, nombre_comercial: 'Clínica Renovada' },
    })

    function Reload() {
      const { reloadSession, session } = useAuth()
      return (
        <div>
          <p>{session?.tenant.nombre_comercial}</p>
          <button type="button" onClick={() => void reloadSession()}>
            Recargar
          </button>
        </div>
      )
    }

    render(
      <MemoryRouter>
        <AuthProvider>
          <Reload />
        </AuthProvider>
      </MemoryRouter>,
    )

    await screen.findByText('Clínica Demo')
    await user.click(screen.getByRole('button', { name: /recargar/i }))

    expect(await screen.findByText('Clínica Renovada')).toBeInTheDocument()
    await waitFor(() => expect(api.me).toHaveBeenCalledTimes(2))
  })
})
