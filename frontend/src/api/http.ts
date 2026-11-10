/**
 * Cliente HTTP del SPA (design D9).
 *
 * Los tokens viven en cookies `HttpOnly`: acá no se leen ni se escriben. Por eso
 * toda request viaja con `credentials: 'include'` y el refresh es transparente:
 * un `401` dispara **un** `POST /auth/refresh` compartido por todas las requests
 * en vuelo (single-flight) y, si sale bien, una única reintentativa.
 */

const API_BASE = '/api/v1'
const REFRESH_PATH = '/auth/refresh'

export interface ApiRequestInit extends RequestInit {
  /** Login, MFA, reset y refresh no deben intentar refrescar la sesión. */
  skipAuthRetry?: boolean
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly retryAfter: number | null

  constructor(status: number, code: string | null, message: string, retryAfter: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
  }
}

type UnauthorizedHandler = () => void

let unauthorizedHandler: UnauthorizedHandler | null = null

/** El provider registra acá qué hacer cuando la sesión ya no se puede refrescar. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}

let refreshPromise: Promise<boolean> | null = null

function buildUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

function buildHeaders(init: RequestInit): Headers {
  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }
  if (init.body !== undefined && init.body !== null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  return headers
}

async function send(path: string, init: ApiRequestInit): Promise<Response> {
  // Se enumeran los campos de `RequestInit` para que `skipAuthRetry` (opción del
  // cliente) no llegue nunca a `fetch`.
  return fetch(buildUrl(path), {
    credentials: 'include',
    method: init.method,
    body: init.body,
    headers: buildHeaders(init),
    signal: init.signal,
    cache: init.cache,
    mode: init.mode,
    redirect: init.redirect,
    referrer: init.referrer,
    referrerPolicy: init.referrerPolicy,
    integrity: init.integrity,
    keepalive: init.keepalive,
  })
}

async function parseBody<T>(response: Response): Promise<T> {
  if (response.status === 204 || response.status === 205) {
    return undefined as T
  }
  return (await response.json()) as T
}

async function toApiError(response: Response): Promise<ApiError> {
  let code: string | null = null
  let message = response.statusText || 'La petición falló.'
  try {
    const body = (await response.json()) as { code?: unknown; message?: unknown }
    if (typeof body.code === 'string') code = body.code
    if (typeof body.message === 'string' && body.message) message = body.message
  } catch {
    // Un error sin JSON (proxy caído, 502 de infraestructura) conserva el texto HTTP.
  }
  const retryAfterHeader = response.headers.get('Retry-After')
  const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : null
  return new ApiError(
    response.status,
    code,
    message,
    retryAfter !== null && Number.isFinite(retryAfter) ? retryAfter : null,
  )
}

async function performRefresh(): Promise<boolean> {
  try {
    const response = await send(REFRESH_PATH, { method: 'POST', skipAuthRetry: true })
    return response.ok
  } catch {
    // Red caída: la sesión no se puede refrescar, pero tampoco hay que romper el flujo.
    return false
  }
}

/** Single-flight: N requests con `401` comparten el mismo `POST /auth/refresh`. */
function refreshSession(): Promise<boolean> {
  if (refreshPromise === null) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

export async function apiFetch<T = unknown>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const response = await send(path, init)
  if (response.ok) {
    return parseBody<T>(response)
  }

  const error = await toApiError(response)
  if (response.status !== 401 || init.skipAuthRetry) {
    throw error
  }

  const refreshed = await refreshSession()
  if (!refreshed) {
    unauthorizedHandler?.()
    throw error
  }

  const retried = await send(path, { ...init, skipAuthRetry: true })
  if (retried.ok) {
    return parseBody<T>(retried)
  }
  throw await toApiError(retried)
}
