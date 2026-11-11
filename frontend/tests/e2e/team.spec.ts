import { createHmac } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

/**
 * e2e de gestión de equipo contra el backend real (task 11.2).
 *
 * Cubre las tres cosas que la rúbrica pide ver y que un test unitario no prueba:
 * la UI respeta los permisos de la sesión, la **API** rechaza el acceso aunque
 * se fuerce el endpoint, y el flujo de gestión funciona de punta a punta con un
 * usuario que tiene el segundo factor.
 *
 * Cuentas: las siembra `backend/tests/fixtures/seed_auth_e2e.py` (ficticias,
 * contraseña conocida, TOTP del vector público de RFC 4648).
 */

const TENANT = process.env.E2E_TENANT_SLUG ?? 'clinica-demo'
const PASSWORD = process.env.E2E_USER_PASSWORD ?? 'demo-password-123'

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? 'owner@example.test'
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@example.test'
const DESK_EMAIL = process.env.E2E_DESK_EMAIL ?? 'desk@example.test'
const TARGET_EMAIL = process.env.E2E_TARGET_EMAIL ?? 'profe@example.test'
const OTHER_TENANT_EMAIL = process.env.E2E_OTHER_TENANT_EMAIL ?? 'ajeno@example.test'
const OWNER_TOTP_SECRET = process.env.E2E_OWNER_TOTP_SECRET ?? 'JBSWY3DPEHPK3PXP'

const STEP_SECONDS = 30
const DIGITS = 6
const BASE32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'

/** Base32 RFC 4648 sin padding → bytes (el mismo que usa `pyotp`). */
export function decodeBase32(secret: string): Buffer {
  const clean = secret.replace(/=+$/u, '').toUpperCase()
  let bits = 0
  let value = 0
  const bytes: number[] = []
  for (const char of clean) {
    const index = BASE32.indexOf(char)
    if (index === -1) throw new Error(`Secreto base32 inválido: ${char}`)
    value = (value << 5) | index
    bits += 5
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 0xff)
      bits -= 8
    }
  }
  return Buffer.from(bytes)
}

/**
 * TOTP de 6 dígitos, HMAC-SHA1 y paso de 30 s: exactamente lo que valida
 * `app/domain/auth/totp.py` con `pyotp`. `atMs` permite fijar el instante.
 */
export function totp(secret: string, atMs: number = Date.now()): string {
  const counter = Math.floor(atMs / (STEP_SECONDS * 1000))
  const message = Buffer.alloc(8)
  message.writeUInt32BE(Math.floor(counter / 2 ** 32), 0)
  message.writeUInt32BE(counter % 2 ** 32, 4)

  const digest = createHmac('sha1', decodeBase32(secret)).update(message).digest()
  const offset = digest[digest.length - 1] & 0x0f
  const binary =
    ((digest[offset] & 0x7f) << 24) |
    ((digest[offset + 1] & 0xff) << 16) |
    ((digest[offset + 2] & 0xff) << 8) |
    (digest[offset + 3] & 0xff)

  return (binary % 10 ** DIGITS).toString().padStart(DIGITS, '0')
}

async function fillCredentials(page: Page, email: string) {
  await page.getByLabel('Clínica').fill(TENANT)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Contraseña').fill(PASSWORD)
  await page.getByRole('button', { name: 'Ingresar' }).click()
}

/** Login de un rol sin MFA obligatorio. */
async function login(page: Page, email: string) {
  await page.goto('/login')
  await fillCredentials(page, email)
  await expect(page.getByRole('heading', { name: 'Gestión Odontológica' })).toBeVisible()
}

/** Login de `owner`: contraseña + código TOTP del secreto sembrado. */
async function loginWithMfa(page: Page, email: string, secret: string) {
  await page.goto('/login')
  await fillCredentials(page, email)
  await expect(page.getByRole('heading', { name: 'Verificación en dos pasos' })).toBeVisible()
  await page.getByLabel('Código de verificación').fill(totp(secret))
  await page.getByRole('button', { name: 'Verificar' }).click()
  await expect(page.getByRole('heading', { name: 'Gestión Odontológica' })).toBeVisible()
}

test('el helper TOTP reproduce el vector de RFC 6238', () => {
  // Secreto de prueba de la RFC ("12345678901234567890") en base32.
  const secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
  expect(totp(secret, 59_000)).toBe('287082')
  expect(totp(secret, 1_111_111_109_000)).toBe('081804')
})

// Serial: los tests de gestión mutan roles y no deben pisarse entre sí
// (`fullyParallel` está activo a nivel de config).
test.describe.configure({ mode: 'serial' })

test.describe('equipo: permisos en la UI y en la API', () => {
  test('recepción no ve el enlace Equipo y /equipo muestra acceso denegado', async ({ page }) => {
    await login(page, DESK_EMAIL)

    await expect(page.getByRole('link', { name: 'Equipo' })).toHaveCount(0)

    await page.goto('/equipo')

    await expect(page.getByText('No tenés permiso para ver esta sección.')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Equipo' })).toHaveCount(0)
  })

  test('recepción forzando GET /team/members recibe 403 forbidden', async ({ page }) => {
    await login(page, DESK_EMAIL)

    const response = await page.request.get('/api/v1/team/members')

    expect(response.status()).toBe(403)
    const body = (await response.json()) as { code?: string; members?: unknown }
    expect(body.code).toBe('forbidden')
    expect(body.members).toBeUndefined()
  })

  test('administrativo clínico ve la lista pero no los botones de gestión', async ({ page }) => {
    await login(page, ADMIN_EMAIL)

    await page.getByRole('link', { name: 'Equipo' }).click()
    await expect(page.getByRole('heading', { name: 'Equipo' })).toBeVisible()
    await expect(page.getByText(OWNER_EMAIL)).toBeVisible()
    await expect(page.getByText(TARGET_EMAIL)).toBeVisible()

    // El tenant B existe en la misma base: no puede filtrarse a esta lista.
    await expect(page.getByText(OTHER_TENANT_EMAIL)).toHaveCount(0)

    await expect(page.getByRole('button', { name: 'Guardar rol' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Dar de baja' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Transferir titularidad' })).toHaveCount(0)
  })

  test('owner con TOTP ve la lista y cambia el rol de un miembro', async ({ page }) => {
    await loginWithMfa(page, OWNER_EMAIL, OWNER_TOTP_SECRET)

    await page.getByRole('link', { name: 'Equipo' }).click()
    await expect(page.getByRole('heading', { name: 'Equipo' })).toBeVisible()

    const row = page.getByRole('row').filter({ hasText: TARGET_EMAIL })
    await expect(row).toBeVisible()
    await expect(row.getByRole('cell', { name: 'professional', exact: true })).toBeVisible()

    await row.getByLabel(`Rol de ${TARGET_EMAIL}`).selectOption('assistant')
    await row.getByRole('button', { name: 'Guardar rol' }).click()

    await expect(page.getByText('Rol actualizado.')).toBeVisible()
    await expect(row.getByRole('cell', { name: 'assistant', exact: true })).toBeVisible()
    await expect(row.getByRole('cell', { name: 'professional', exact: true })).toHaveCount(0)
  })
})
