import { expect, test } from '@playwright/test'

test('sin sesión, la raíz muestra el login', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible()
})

test('con sesión, la raíz muestra la home', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Clínica').fill(process.env.E2E_TENANT_SLUG ?? 'clinica-demo')
  await page.getByLabel('Email').fill(process.env.E2E_USER_EMAIL ?? 'demo@example.test')
  await page.getByLabel('Contraseña').fill(process.env.E2E_USER_PASSWORD ?? 'demo-password-123')
  await page.getByRole('button', { name: 'Ingresar' }).click()

  await expect(page.getByRole('heading', { name: 'Gestión Odontológica' })).toBeVisible()
})
