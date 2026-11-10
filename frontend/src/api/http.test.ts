import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, setUnauthorizedHandler, type ApiRequestInit } from './http'

type FetchArgs = Parameters<typeof fetch>

const fetchMock = vi.fn<(...args: FetchArgs) => Promise<Response>>()

function jsonResponse(status: number, body: unknown = {}, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json', ...headers }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response
}

function emptyResponse(status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => {
      throw new Error('204 no tiene body')
    },
    text: async () => '',
  } as unknown as Response
}

function callUrl(index: number): string {
  const call = fetchMock.mock.calls[index]
  if (!call) throw new Error(`no existe la llamada ${index}`)
  return String(call[0])
}

function callInit(index: number): RequestInit {
  const call = fetchMock.mock.calls[index]
  return (call?.[1] ?? {}) as RequestInit
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('apiFetch', () => {
  it('manda credentials include contra el prefijo /api/v1 y devuelve el JSON', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: 'u-1' }))

    const result = await apiFetch<{ id: string }>('/auth/me')

    expect(result).toEqual({ id: 'u-1' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(callUrl(0)).toBe('/api/v1/auth/me')
    expect(callInit(0).credentials).toBe('include')
  })

  it('ante un 401 refresca una sola vez y reintenta la request original', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { code: 'session_expired', message: 'La sesión expiró.' }))
      .mockResolvedValueOnce(jsonResponse(200, { status: 'ok' }))
      .mockResolvedValueOnce(jsonResponse(200, { user: { id: 'u-1' } }))

    const result = await apiFetch<{ user: { id: string } }>('/auth/me')

    expect(result).toEqual({ user: { id: 'u-1' } })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(callUrl(1)).toBe('/api/v1/auth/refresh')
    expect(callInit(1).method).toBe('POST')
    expect(callInit(1).credentials).toBe('include')
    expect(callUrl(2)).toBe('/api/v1/auth/me')
    expect(callInit(2).credentials).toBe('include')
  })

  it('si el refresh falla no reintenta, avisa al handler y propaga el error original', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { code: 'session_expired', message: 'La sesión expiró.' }))
      .mockResolvedValueOnce(jsonResponse(401, { code: 'not_authenticated', message: 'No hay sesión.' }))

    await expect(apiFetch('/auth/me')).rejects.toMatchObject({
      status: 401,
      code: 'session_expired',
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('dos requests simultáneas con 401 comparten un único refresh (single-flight)', async () => {
    const urls: string[] = []
    fetchMock.mockImplementation(async (input) => {
      const url = String(input)
      urls.push(url)
      if (url === '/api/v1/auth/refresh') {
        return jsonResponse(200, { status: 'ok' })
      }
      const previous = urls.filter((seen) => seen === url).length
      if (previous === 1) {
        return jsonResponse(401, { code: 'not_authenticated', message: 'No hay sesión.' })
      }
      return jsonResponse(200, { path: url })
    })

    const [me, tenants] = await Promise.all([
      apiFetch<{ path: string }>('/auth/me'),
      apiFetch<{ path: string }>('/tenants'),
    ])

    expect(me).toEqual({ path: '/api/v1/auth/me' })
    expect(tenants).toEqual({ path: '/api/v1/tenants' })
    expect(urls.filter((url) => url === '/api/v1/auth/refresh')).toHaveLength(1)
    expect(urls).toHaveLength(5)
  })

  it('con skipAuthRetry no refresca ni reintenta (login/MFA/reset)', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { code: 'invalid_credentials', message: 'Email o contraseña incorrectos.' }),
    )

    const loginInit: ApiRequestInit = { method: 'POST', body: '{}', skipAuthRetry: true }

    await expect(apiFetch('/auth/login', loginInit)).rejects.toMatchObject({
      status: 401,
      code: 'invalid_credentials',
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('un 204 resuelve sin intentar parsear body', async () => {
    fetchMock.mockResolvedValueOnce(emptyResponse(204))

    await expect(apiFetch('/auth/logout', { method: 'POST' })).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('ApiError expone code, message y retryAfter del Retry-After', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        423,
        { code: 'locked', message: 'La cuenta está bloqueada temporalmente.' },
        { 'Retry-After': '900' },
      ),
    )

    const error = await apiFetch('/auth/login', { skipAuthRetry: true }).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 423,
      code: 'locked',
      message: 'La cuenta está bloqueada temporalmente.',
      retryAfter: 900,
    })
  })

  it('nunca escribe tokens en localStorage ni sessionStorage', async () => {
    // Se espía el prototipo: espiar la instancia de jsdom mete una clave "setItem".
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem')
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { code: 'session_expired', message: 'La sesión expiró.' }))
      .mockResolvedValueOnce(jsonResponse(200, { status: 'ok' }))
      .mockResolvedValueOnce(jsonResponse(200, { id: 'u-1' }))

    await apiFetch('/auth/me')

    expect(storageSpy).not.toHaveBeenCalled()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
    storageSpy.mockRestore()
  })
})
