import { createContext, useContext } from 'react'
import type { LoginRequest, MfaEnrollStartResponse, SessionOut } from '@/api/auth'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

/** Resultado del login: la sesión quedó lista o falta el segundo factor (D5). */
export type SignInResult =
  | { kind: 'authenticated' }
  | { kind: 'mfaStepUp' }
  | { kind: 'mfaEnrollment' }

export interface AuthContextValue {
  status: AuthStatus
  session: SessionOut | null
  /** Login por contraseña; devuelve qué estado de MFA corresponde. */
  signIn: (payload: LoginRequest) => Promise<SignInResult>
  /** Genera el secreto del alta de TOTP (solo en `mfaEnrollment`). */
  startEnrollment: () => Promise<MfaEnrollStartResponse>
  completeMfa: (code: string) => Promise<void>
  completeEnrollment: (code: string) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (value === null) {
    throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  }
  return value
}
