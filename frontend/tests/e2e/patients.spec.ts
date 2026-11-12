import { expect, test } from '@playwright/test'
import { login } from './support'

/**
 * e2e de la ficha demográfica contra el backend real (task 5.6).
 *
 * Cubre lo que un test unitario no puede probar (rúbrica, criterios 3 y 5):
 * la pantalla `/pacientes` consume la API real con Postgres + RLS, el alta crea
 * la ficha con su número de historia clínica, el `409` por DNI llega como `code`
 * estable, la UI respeta los permisos de la sesión y el tenant B no ve nada del
 * tenant A.
 *
 * Cuentas: `backend/tests/fixtures/seed_auth_e2e.py`. El seed deja el paciente
 * canónico `E2E-Paciente, Demo` (DNI reservado `99000111`) y borra en cada
 * arranque los pacientes con `apellido LIKE 'E2E-%'`, así que este spec puede
 * crear fichas nuevas sin chocar contra el índice único de DNI.
 */

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@example.test'
const PROFESSIONAL_EMAIL = process.env.E2E_USER_EMAIL ?? 'demo@example.test'
const OTHER_TENANT_EMAIL = process.env.E2E_OTHER_TENANT_EMAIL ?? 'ajeno@example.test'
const OTHER_TENANT = process.env.E2E_OTHER_TENANT_SLUG ?? 'clinica-demo-b'

const SEED_PATIENT_APELLIDO = 'E2E-Paciente'
const RUN = Date.now().toString(36).slice(-6)
const NEW_APELLIDO = `E2E-${RUN}`
const NEW_NOMBRE = `Paciente ${RUN}`
const NEW_DNI = String(Date.now()).slice(-8)

test.describe.configure({ mode: 'serial' })

test.describe('pacientes: búsqueda, alta y permisos contra la API real', () => {
  test('el listado consume el backend y muestra el paciente sembrado con su HCE', async ({
    page,
  }) => {
    // `clinical_admin` tiene `patient.create/read/update` (matriz de C-04).
    await login(page, ADMIN_EMAIL)

    await page.getByRole('link', { name: 'Pacientes' }).click()
    await expect(page.getByRole('heading', { name: 'Pacientes' })).toBeVisible()

    const seedRow = page.getByRole('row').filter({ hasText: SEED_PATIENT_APELLIDO })
    await expect(seedRow).toBeVisible()
    // La HCE la emite `patient_counter`: seis dígitos, nunca un UUID.
    await expect(seedRow.getByRole('cell', { name: /^\d{6}$/ })).toBeVisible()
    await expect(seedRow.getByRole('cell', { name: '99000111' })).toBeVisible()

    // La búsqueda va al backend con el término y trae el resultado real.
    const [response] = await Promise.all([
      page.waitForResponse(
        (candidate) =>
          candidate.request().method() === 'GET' &&
          candidate.url().includes('/api/v1/patients?') &&
          candidate.url().includes('q=demo'),
      ),
      (async () => {
        await page.getByLabel('Buscar paciente').fill('demo')
        await page.getByRole('button', { name: 'Buscar' }).click()
      })(),
    ])
    expect(response.status()).toBe(200)
    await expect(page.getByRole('row').filter({ hasText: SEED_PATIENT_APELLIDO })).toBeVisible()
  })

  test('administrativo clínico da de alta una ficha y el DNI repetido se informa', async ({
    page,
  }) => {
    await login(page, ADMIN_EMAIL)
    await page.getByRole('link', { name: 'Pacientes' }).click()
    await expect(page.getByRole('heading', { name: 'Pacientes' })).toBeVisible()

    await page.getByRole('button', { name: 'Nuevo paciente' }).click()
    const dialogo = page.getByRole('dialog', { name: 'Nuevo paciente' })
    await expect(dialogo).toBeVisible()

    await dialogo.getByLabel('Nombre', { exact: true }).fill(NEW_NOMBRE)
    await dialogo.getByLabel('Apellido').fill(NEW_APELLIDO)
    await dialogo.getByLabel('Teléfono').fill('11 4444-8271')
    await dialogo.getByLabel('DNI').fill(NEW_DNI)
    await page.getByRole('button', { name: 'Guardar paciente' }).click()

    // El alta aparece en la tabla con la HCE que devolvió el backend.
    await expect(page.getByText(/paciente creado con hce \d{6}/i)).toBeVisible()
    const newRow = page.getByRole('row').filter({ hasText: NEW_APELLIDO })
    await expect(newRow).toBeVisible()
    await expect(newRow.getByRole('cell', { name: /^\d{6}$/ })).toBeVisible()
    await expect(newRow.getByRole('cell', { name: NEW_DNI })).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)

    // Mismo DNI, otra persona: `409 patient_dni_duplicado`, sin diálogo de
    // confirmación (esa regla no se puede vencer) y sin perder lo cargado.
    await page.getByRole('button', { name: 'Nuevo paciente' }).click()
    const repetido = page.getByRole('dialog', { name: 'Nuevo paciente' })
    await repetido.getByLabel('Nombre', { exact: true }).fill('Otra')
    await repetido.getByLabel('Apellido').fill('Persona')
    await repetido.getByLabel('Teléfono').fill('11 4444-8272')
    await repetido.getByLabel('DNI').fill(NEW_DNI)
    await page.getByRole('button', { name: 'Guardar paciente' }).click()

    await expect(page.getByText(/ya hay un paciente con ese dni/i)).toBeVisible()
    await expect(page.getByText('patient_dni_duplicado')).toBeVisible()
    await expect(page.getByRole('dialog', { name: 'Posible duplicado' })).toHaveCount(0)
    await expect(repetido.getByLabel('DNI')).toHaveValue(NEW_DNI)

    // Forzar la API con `confirmar_duplicado` tampoco vence el dedupe duro.
    const forced = await page.request.post('/api/v1/patients', {
      data: {
        nombre: 'Otra',
        apellido: `E2E-Forzado ${RUN}`,
        telefono: '11 4444-8273',
        dni: NEW_DNI,
        confirmar_duplicado: true,
      },
    })
    expect(forced.status()).toBe(409)
    const body = (await forced.json()) as { code?: string }
    expect(body.code).toBe('patient_dni_duplicado')
  })

  test('un profesional ve la lista pero no el alta, y la API rechaza el POST', async ({ page }) => {
    // `professional` tiene `patient.read`; no `patient.create` ni `patient.update`.
    await login(page, PROFESSIONAL_EMAIL)
    await page.getByRole('link', { name: 'Pacientes' }).click()

    await expect(page.getByRole('heading', { name: 'Pacientes' })).toBeVisible()
    await expect(page.getByRole('row').filter({ hasText: SEED_PATIENT_APELLIDO })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Nuevo paciente' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Editar' })).toHaveCount(0)

    const response = await page.request.post('/api/v1/patients', {
      data: { nombre: 'Sin', apellido: 'Permiso', telefono: '11 4444-9999' },
    })
    expect(response.status()).toBe(403)
    const body = (await response.json()) as { code?: string; id?: unknown }
    expect(body.code).toBe('forbidden')
    expect(body.id).toBeUndefined()
  })

  test('el tenant B no ve los pacientes del tenant A', async ({ page }) => {
    await login(page, OTHER_TENANT_EMAIL, OTHER_TENANT)
    await page.getByRole('link', { name: 'Pacientes' }).click()

    await expect(page.getByRole('heading', { name: 'Pacientes' })).toBeVisible()
    // La ficha de A existe en la misma base: no puede aparecer en B.
    await expect(page.getByText(SEED_PATIENT_APELLIDO)).toHaveCount(0)
    await expect(page.getByText('No hay pacientes para mostrar.')).toBeVisible()

    const response = await page.request.get('/api/v1/patients?q=demo')
    expect(response.status()).toBe(200)
    const body = (await response.json()) as { patients?: unknown[]; total?: number }
    expect(body.total).toBe(0)
    expect(body.patients).toEqual([])
  })
})
