/**
 * Contrato de auth del backend (OpenAPI de FastAPI, `app/schemas/auth.py`).
 *
 * Los DTOs replican el shape de respuesta; los `code` de error son uniones
 * literales del catálogo estable del design D9, para que la UI conmute por
 * `code` y nunca por status ni por texto.
 */

import { apiFetch, type ApiRequestInit } from './http'

export type Role =
  | 'owner'
  | 'clinical_admin'
  | 'professional'
  | 'assistant'
  | 'front_desk'
  | 'billing'
  | 'patient'
  | 'external_lab'
  | 'accountant'

export type AuthErrorCode =
  | 'invalid_credentials'
  | 'not_authenticated'
  | 'session_expired'
  | 'credentials_changed'
  | 'invalid_mfa_code'
  | 'mfa_step_up_expired'
  | 'mfa_required'
  | 'mfa_enrollment_required'
  | 'mfa_unavailable'
  | 'tenant_not_available'
  | 'locked'
  | 'refresh_reuse'
  | 'invalid_or_expired_token'

export interface UserOut {
  id: string
  email: string | null
  nombre: string
  apellido: string
}

export interface TenantOut {
  id: string
  slug: string
  nombre_comercial: string
}

export interface SessionOut {
  user: UserOut
  tenant: TenantOut
  roles: Role[]
  mfa_enrolled: boolean
}

export interface LoginRequest {
  tenant_slug: string
  email: string
  password: string
}

export interface MfaCodeRequest {
  code: string
}

export interface MfaEnrollStartResponse {
  secret: string
  otpauth_uri: string
}

export interface SwitchTenantRequest {
  tenant_slug: string
}

export interface ForgotPasswordRequest {
  email: string
}

export interface ForgotPasswordResponse {
  token?: string
}

export interface ResetPasswordRequest {
  token: string
  new_password: string
}

export interface ResetPasswordResponse {
  status: 'ok'
}

function post<T>(path: string, body?: unknown, init: ApiRequestInit = {}): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    ...init,
  })
}

/** Login válido; responde `403 mfa_required`/`mfa_enrollment_required` si falta el segundo factor. */
export function login(payload: LoginRequest): Promise<SessionOut> {
  return post<SessionOut>('/auth/login', payload, { skipAuthRetry: true })
}

/** Restaura la sesión al arrancar el SPA; un `401` deja el árbol sin usuario. */
export function me(): Promise<SessionOut> {
  return apiFetch<SessionOut>('/auth/me')
}

export function refresh(): Promise<SessionOut> {
  return post<SessionOut>('/auth/refresh', undefined, { skipAuthRetry: true })
}

export function logout(): Promise<void> {
  return post<void>('/auth/logout', undefined, { skipAuthRetry: true })
}

export function switchTenant(payload: SwitchTenantRequest): Promise<SessionOut> {
  return post<SessionOut>('/auth/switch-tenant', payload)
}

export function mfaVerify(code: string): Promise<SessionOut> {
  return post<SessionOut>('/auth/mfa/verify', { code } satisfies MfaCodeRequest, {
    skipAuthRetry: true,
  })
}

export function mfaEnrollStart(): Promise<MfaEnrollStartResponse> {
  return post<MfaEnrollStartResponse>('/auth/mfa/enroll/start', undefined, {
    skipAuthRetry: true,
  })
}

export function mfaEnrollConfirm(code: string): Promise<SessionOut> {
  return post<SessionOut>('/auth/mfa/enroll/confirm', { code } satisfies MfaCodeRequest, {
    skipAuthRetry: true,
  })
}

export function forgotPassword(payload: ForgotPasswordRequest): Promise<ForgotPasswordResponse> {
  return post<ForgotPasswordResponse>('/auth/forgot-password', payload, { skipAuthRetry: true })
}

export function resetPassword(payload: ResetPasswordRequest): Promise<ResetPasswordResponse> {
  return post<ResetPasswordResponse>('/auth/reset-password', payload, { skipAuthRetry: true })
}
