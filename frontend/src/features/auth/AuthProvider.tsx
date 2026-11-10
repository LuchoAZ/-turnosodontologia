import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as authApi from '@/api/auth'
import type { LoginRequest, SessionOut } from '@/api/auth'
import { ApiError, setUnauthorizedHandler } from '@/api/http'
import { AuthContext, type AuthStatus, type SignInResult } from './context'

interface AuthState {
  status: AuthStatus
  session: SessionOut | null
}

const ANONYMOUS: AuthState = { status: 'anonymous', session: null }

/**
 * Estado de sesión del SPA (design D1/D9).
 *
 * Los tokens no existen en JS: al montar se pregunta `GET /auth/me` y, si el
 * refresh automático falla, `apiFetch` avisa por `setUnauthorizedHandler` para
 * que la UI vuelva a `anonymous` sin recargar la página.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', session: null })

  useEffect(() => {
    setUnauthorizedHandler(() => setState(ANONYMOUS))
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    let active = true
    authApi
      .me()
      .then((session) => {
        if (active) setState({ status: 'authenticated', session })
      })
      .catch(() => {
        if (active) setState(ANONYMOUS)
      })
    return () => {
      active = false
    }
  }, [])

  const signIn = useCallback(async (payload: LoginRequest): Promise<SignInResult> => {
    try {
      const session = await authApi.login(payload)
      setState({ status: 'authenticated', session })
      return { kind: 'authenticated' }
    } catch (error) {
      if (error instanceof ApiError && error.code === 'mfa_required') {
        return { kind: 'mfaStepUp' }
      }
      if (error instanceof ApiError && error.code === 'mfa_enrollment_required') {
        return { kind: 'mfaEnrollment' }
      }
      throw error
    }
  }, [])

  const startEnrollment = useCallback(() => authApi.mfaEnrollStart(), [])

  const completeMfa = useCallback(async (code: string) => {
    const session = await authApi.mfaVerify(code)
    setState({ status: 'authenticated', session })
  }, [])

  const completeEnrollment = useCallback(async (code: string) => {
    const session = await authApi.mfaEnrollConfirm(code)
    setState({ status: 'authenticated', session })
  }, [])

  const signOut = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      setState(ANONYMOUS)
    }
  }, [])

  const value = useMemo(
    () => ({
      status: state.status,
      session: state.session,
      signIn,
      startEnrollment,
      completeMfa,
      completeEnrollment,
      signOut,
    }),
    [state, signIn, startEnrollment, completeMfa, completeEnrollment, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
