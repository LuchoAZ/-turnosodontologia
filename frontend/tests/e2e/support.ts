import { expect, type Page } from '@playwright/test'

/**
 * Helpers compartidos por los specs e2e (no registran tests propios).
 *
 * Vive fuera de los `.spec.ts` a propósito: importar de un spec haría que
 * Playwright registre sus tests dos veces.
 */

export const E2E_TENANT = process.env.E2E_TENANT_SLUG ?? 'clinica-demo'
export const E2E_PASSWORD = process.env.E2E_USER_PASSWORD ?? 'demo-password-123'

/** Login de un rol sin MFA obligatorio (las cuentas las siembra `seed_auth_e2e.py`). */
export async function login(
  page: Page,
  email: string,
  tenant: string = E2E_TENANT,
): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Clínica').fill(tenant)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Contraseña').fill(E2E_PASSWORD)
  await page.getByRole('button', { name: 'Ingresar' }).click()
  await expect(page.getByRole('heading', { name: 'Gestión Odontológica' })).toBeVisible()
}
