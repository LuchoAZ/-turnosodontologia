import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from '@/api/auth'
import type { SessionOut } from '@/api/auth'
import { ApiError } from '@/api/http'
import { AuthProvider } from '@/features/auth/AuthProvider'
import Login from './Login'

vi.mock('@/api/auth')

const api = vi.mocked(authApi)

const SESSION: SessionOut = {
  user: { id: 'u-1', email: 'demo@example.test', nombre: 'Demo', apellido: 'Pérez' },
  tenant: { id: 't-1', slug: 'clinica-demo', nombre_comercial: 'Clínica Demo' },
  roles: ['professional'],
  permissions: [],
  mfa_enrolled: true,
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<h1>Home autenticada</h1>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

async function submitLogin(email = 'demo@example.test', password = 'secreta-123') {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/clínica/i), 'clinica-demo')
  await user.type(screen.getByLabelText(/email/i), email)
  await user.type(screen.getByLabelText(/contraseña/i), password)
  await user.click(screen.getByRole('button', { name: /ingresar/i }))
  return user
}

beforeEach(() => {
  vi.resetAllMocks()
  api.me.mockRejectedValue(new ApiError(401, 'not_authenticated', 'No hay sesión.'))
  api.login.mockResolvedValue(SESSION)
})

describe('Login', () => {
  it('con credenciales válidas navega a la home', async () => {
    renderLogin()

    await submitLogin()

    expect(await screen.findByRole('heading', { name: /home autenticada/i })).toBeInTheDocument()
    expect(api.login).toHaveBeenCalledWith({
      tenant_slug: 'clinica-demo',
      email: 'demo@example.test',
      password: 'secreta-123',
    })
  })

  it('con credenciales inválidas muestra el mensaje del catálogo', async () => {
    api.login.mockRejectedValue(
      new ApiError(401, 'invalid_credentials', 'Email o contraseña incorrectos.'),
    )
    renderLogin()

    await submitLogin()

    expect(await screen.findByRole('alert')).toHaveTextContent('Email o contraseña incorrectos.')
    expect(screen.queryByRole('heading', { name: /home autenticada/i })).not.toBeInTheDocument()
  })

  it('con la cuenta bloqueada muestra el tiempo restante', async () => {
    api.login.mockRejectedValue(new ApiError(423, 'locked', 'La cuenta está bloqueada temporalmente.', 900))
    renderLogin()

    await submitLogin()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/bloqueada/i)
    expect(alert).toHaveTextContent(/15 minutos/i)
  })

  it('con 403 mfa_required pasa al estado mfaStepUp y verifica el código', async () => {
    api.login.mockRejectedValueOnce(new ApiError(403, 'mfa_required', 'Se requiere el segundo factor.'))
    api.mfaVerify.mockResolvedValue(SESSION)
    renderLogin()

    const user = await submitLogin()

    expect(await screen.findByRole('heading', { name: /verificación en dos pasos/i })).toBeInTheDocument()
    await user.type(screen.getByLabelText(/código de verificación/i), '123456')
    await user.click(screen.getByRole('button', { name: /verificar/i }))

    expect(await screen.findByRole('heading', { name: /home autenticada/i })).toBeInTheDocument()
    expect(api.mfaVerify).toHaveBeenCalledWith('123456')
  })

  it('con 403 mfa_enrollment_required muestra el secreto y confirma el alta', async () => {
    api.login.mockRejectedValueOnce(
      new ApiError(403, 'mfa_enrollment_required', 'Tenés que enrolar el segundo factor.'),
    )
    api.mfaEnrollStart.mockResolvedValue({
      secret: 'JBSWY3DPEHPK3PXP',
      otpauth_uri: 'otpauth://totp/Odontologia:demo@example.test?secret=JBSWY3DPEHPK3PXP',
    })
    api.mfaEnrollConfirm.mockResolvedValue({ ...SESSION, mfa_enrolled: true })
    renderLogin()

    const user = await submitLogin()

    expect(
      await screen.findByRole('heading', { name: /configurá el segundo factor/i }),
    ).toBeInTheDocument()
    expect(screen.getByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument()
    await user.type(screen.getByLabelText(/código de verificación/i), '654321')
    await user.click(screen.getByRole('button', { name: /confirmar/i }))

    expect(await screen.findByRole('heading', { name: /home autenticada/i })).toBeInTheDocument()
    expect(api.mfaEnrollConfirm).toHaveBeenCalledWith('654321')
  })

  it('con mfa_step_up_expired reinicia el login', async () => {
    api.login.mockRejectedValueOnce(new ApiError(403, 'mfa_required', 'Se requiere el segundo factor.'))
    api.mfaVerify.mockRejectedValueOnce(
      new ApiError(401, 'mfa_step_up_expired', 'La verificación expiró; volvé a iniciar sesión.'),
    )
    renderLogin()

    const user = await submitLogin()
    await screen.findByRole('heading', { name: /verificación en dos pasos/i })
    await user.type(screen.getByLabelText(/código de verificación/i), '000000')
    await user.click(screen.getByRole('button', { name: /verificar/i }))

    expect(await screen.findByRole('heading', { name: /iniciar sesión/i })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/volvé a iniciar sesión/i)
  })

  it('con error de red muestra un mensaje genérico', async () => {
    api.login.mockRejectedValue(new TypeError('Failed to fetch'))
    renderLogin()

    await submitLogin()

    expect(await screen.findByRole('alert')).toHaveTextContent(/no pudimos conectar/i)
  })

  it('valida los campos antes de llamar al backend', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: /ingresar/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/ingresá la clínica/i)
    expect(api.login).not.toHaveBeenCalled()
  })
})
