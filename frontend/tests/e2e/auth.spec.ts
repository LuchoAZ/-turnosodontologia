import { expect, test, type Page } from '@playwright/test'

const TENANT = process.env.E2E_TENANT_SLUG ?? 'clinica-demo'
const EMAIL = process.env.E2E_USER_EMAIL ?? 'demo@example.test'
const PASSWORD = process.env.E2E_USER_PASSWORD ?? 'demo-password-123'

async function fillCredentials(page: Page, password: string) {
  await page.getByLabel('Clínica').fill(TENANT)
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Contraseña').fill(password)
  await page.getByRole('button', { name: 'Ingresar' }).click()
}

async function login(page: Page) {
  await page.goto('/login')
  await fillCredentials(page, PASSWORD)
  await expect(page.getByRole('heading', { name: 'Gestión Odontológica' })).toBeVisible()
}

test('sin sesión, la raíz redirige a /login', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible()
})

test('credenciales inválidas muestran el error del catálogo', async ({ page }) => {
  await page.goto('/login')

  await fillCredentials(page, 'contraseña-incorrecta')

  await expect(page.getByRole('alert')).toContainText('Email o contraseña incorrectos.')
  await expect(page).toHaveURL(/\/login$/)
})

test('login válido llega a la home con el tenant de la sesión', async ({ page }) => {
  await page.goto('/login')

  await fillCredentials(page, PASSWORD)

  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Gestión Odontológica' })).toBeVisible()
  await expect(page.getByText('Clínica Demo')).toBeVisible()
})

test('logout vuelve a /login y una recarga no restaura la sesión', async ({ page }) => {
  await login(page)

  await page.getByRole('button', { name: 'Salir' }).click()

  await expect(page).toHaveURL(/\/login$/)
  await page.reload()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible()
})
