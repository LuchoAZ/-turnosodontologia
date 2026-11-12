import { expect, test, type Page } from '@playwright/test'

/**
 * e2e de configuración clínica contra el backend real (tasks 8.1–8.2).
 *
 * Cubre lo que un test unitario no puede: la pantalla `/clinica` habla con la API
 * real (Postgres con RLS), el alta de profesional resuelve la especialidad desde
 * el catálogo sembrado, el error de negocio llega como `code` estable y el
 * aislamiento cross-tenant se ve en la UI, no solo en la consulta.
 *
 * Cuentas: `backend/tests/fixtures/seed_auth_e2e.py`. Las filas que crea este
 * spec llevan el prefijo `E2E-` y el seed las borra en cada arranque, así que
 * correrlo dos veces no choca contra `409 chair_name_taken`.
 */

const TENANT = process.env.E2E_TENANT_SLUG ?? 'clinica-demo'
const OTHER_TENANT = process.env.E2E_OTHER_TENANT_SLUG ?? 'clinica-demo-b'
const PASSWORD = process.env.E2E_USER_PASSWORD ?? 'demo-password-123'

const PROFESSIONAL_EMAIL = process.env.E2E_USER_EMAIL ?? 'demo@example.test'
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@example.test'
const OTHER_TENANT_EMAIL = process.env.E2E_OTHER_TENANT_EMAIL ?? 'ajeno@example.test'

const SEED_CHAIR = 'Sillón demo'
const SEED_MATRICULA = 'MP-DEMO-1'
const RUN = Date.now().toString(36).slice(-6)
const NEW_CHAIR = `E2E-Sillón ${RUN}`
const NEW_MATRICULA = `E2E-MP-${RUN}`

async function login(page: Page, email: string, tenant: string = TENANT) {
  await page.goto('/login')
  await page.getByLabel('Clínica').fill(tenant)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Contraseña').fill(PASSWORD)
  await page.getByRole('button', { name: 'Ingresar' }).click()
  await expect(page.getByRole('heading', { name: 'Gestión Odontológica' })).toBeVisible()
}

test.describe.configure({ mode: 'serial' })

test.describe('clínica: permisos en la UI, la API y el flujo de alta', () => {
  test('un profesional ve la pantalla pero no el alta, y la API rechaza el POST', async ({
    page,
  }) => {
    await login(page, PROFESSIONAL_EMAIL)

    await page.getByRole('link', { name: 'Clínica' }).click()
    await expect(page.getByRole('heading', { name: 'Clínica' })).toBeVisible()

    // `professional` tiene `chair.read` pero no `chair.create`.
    await expect(page.getByText(SEED_CHAIR)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Nuevo sillón' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Nuevo profesional' })).toHaveCount(0)

    // Forzar el endpoint no alcanza: la guarda del backend responde 403.
    const response = await page.request.post('/api/v1/clinic/chairs', {
      data: { nombre: `E2E-Forzado ${RUN}`, tipo: 'otro' },
    })

    expect(response.status()).toBe(403)
    const body = (await response.json()) as { code?: string; chairs?: unknown }
    expect(body.code).toBe('forbidden')
    expect(body.chairs).toBeUndefined()
  })

  test('el tenant B no ve la configuración del tenant A', async ({ page }) => {
    await login(page, OTHER_TENANT_EMAIL, OTHER_TENANT)

    await page.getByRole('link', { name: 'Clínica' }).click()
    await expect(page.getByRole('heading', { name: 'Clínica' })).toBeVisible()

    // El sillón y la matrícula de A existen en la misma base: no pueden aparecer.
    await expect(page.getByText(SEED_CHAIR)).toHaveCount(0)
    await expect(page.getByText(SEED_MATRICULA)).toHaveCount(0)
    await expect(page.getByText('Todavía no hay sillones.')).toBeVisible()
  })

  test('administrativo clínico da de alta un sillón y un profesional del catálogo', async ({
    page,
  }) => {
    await login(page, ADMIN_EMAIL)

    await page.getByRole('link', { name: 'Clínica' }).click()
    await expect(page.getByRole('heading', { name: 'Clínica' })).toBeVisible()

    // Alta de sillón: `clinical_admin` tiene `chair.create`.
    await page.getByLabel('Nombre del sillón').fill(NEW_CHAIR)
    await page.getByLabel('Tipo de sillón').selectOption('rx')
    await page.getByRole('button', { name: 'Nuevo sillón' }).click()

    await expect(page.getByText('Sillón creado.')).toBeVisible()
    const chairRow = page.getByRole('row').filter({ hasText: NEW_CHAIR })
    await expect(chairRow).toBeVisible()
    await expect(chairRow.getByRole('cell', { name: 'Rayos X' })).toBeVisible()
    await expect(chairRow.getByRole('cell', { name: 'Activo' })).toBeVisible()

    // Alta de profesional: la especialidad sale del catálogo real, no de un UUID fijo.
    const specialty = page.getByLabel('Especialidad')
    await expect(specialty.locator('option', { hasText: 'Odontología general' })).toHaveCount(1)
    await specialty.selectOption({ label: 'Odontología general' })
    await page.getByLabel('Nombre', { exact: true }).fill('Bruno')
    await page.getByLabel('Apellido').fill('Berra')
    await page.getByLabel('Matrícula').fill(NEW_MATRICULA)
    await page.getByRole('button', { name: 'Nuevo profesional' }).click()

    await expect(page.getByText('Profesional creado.')).toBeVisible()
    const proRow = page.getByRole('row').filter({ hasText: NEW_MATRICULA })
    await expect(proRow).toBeVisible()
    await expect(proRow.getByRole('cell', { name: 'Odontología general' })).toBeVisible()

    // El seed ya dejó un profesional canónico en la tabla.
    await expect(page.getByText(SEED_MATRICULA)).toBeVisible()

    // Matrícula repetida: `409 professional_matricula_taken` con su `code` visible.
    await page.getByLabel('Nombre', { exact: true }).fill('Otra')
    await page.getByLabel('Apellido').fill('Persona')
    await page.getByLabel('Matrícula').fill(NEW_MATRICULA)
    await page.getByRole('button', { name: 'Nuevo profesional' }).click()

    await expect(page.getByText('Ya hay un profesional con esa matrícula.')).toBeVisible()
    await expect(page.getByText('professional_matricula_taken')).toBeVisible()
  })

  test('el profesional de la clínica no tiene el permiso de baja de sillón', async ({ page }) => {
    await login(page, PROFESSIONAL_EMAIL)

    await page.getByRole('link', { name: 'Clínica' }).click()

    // `professional` tiene `chair.read`; no `chair.update` ni `chair.delete`.
    await expect(page.getByText(SEED_CHAIR)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Dar de baja' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Guardar' })).toHaveCount(0)
  })
})
