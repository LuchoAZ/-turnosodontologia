import { expect, test, type Page } from '@playwright/test'
import { E2E_PASSWORD, login } from './support'

/**
 * e2e del alta de turnos contra el backend real (task 7.1; criterios 4 y 5).
 *
 * Cubre lo que un test unitario no puede: el formulario `/turnos/nuevo` habla con
 * la API real (FastAPI + Postgres con RLS + el `EXCLUDE` de la base), el servidor
 * deriva `fin` y `duracion_min` de la disponibilidad, el `409` llega como `code`
 * estable con el recurso y el rango en conflicto, la guarda de RBAC corta al rol
 * que no puede agendar y un recurso inexistente responde `404` sin filtrar nada.
 * El aislamiento cross-tenant del alta se prueba en
 * `backend/tests/integration/test_appointments_rls.py` (gate RN-TEN-02).
 *
 * Cuentas: `backend/tests/fixtures/seed_auth_e2e.py`. `desk@example.test`
 * (`front_desk`) es el rol que agenda en recepción: tiene `appointment.create`,
 * `patient.read`, `professional.read` y `chair.read`.
 *
 * El seed deja un profesional (`MP-DEMO-1`, 30 min), un sillón (`Sillón demo`),
 * el paciente canónico `E2E-Paciente, Demo` y **ninguna** `availability_rule`: sin
 * regla aplicable la duración es la del profesional (30) y los buffers son 0.
 *
 * Los turnos **no** se borran entre corridas, así que cada corrida usa un día
 * distinto derivado del reloj: correr el spec dos veces no choca contra el
 * `EXCLUDE` de la corrida anterior.
 */

const TENANT = process.env.E2E_TENANT_SLUG ?? 'clinica-demo'
const OTHER_TENANT = process.env.E2E_OTHER_TENANT_SLUG ?? 'clinica-demo-b'
const FRONT_DESK_EMAIL = process.env.E2E_FRONT_DESK_EMAIL ?? 'desk@example.test'
const OTHER_TENANT_EMAIL = process.env.E2E_OTHER_TENANT_EMAIL ?? 'ajeno@example.test'

const BASE_MS = Date.UTC(2030, 0, 1)
const DAY_MS = 86_400_000
/** Día base de la corrida: cambia cada segundo, así que dos corridas no coinciden. */
const RUN_DAY = Math.floor(Date.now() / 1000) % 1200

const SEED_CHAIR = 'Sillón demo'
const SEED_PROFESSIONAL = 'Profesional, Paula'
const SEED_PATIENT = 'E2E-Paciente, Demo'

function fecha(offsetDias: number): string {
  return new Date(BASE_MS + (RUN_DAY + offsetDias) * DAY_MS).toISOString().slice(0, 10)
}

/**
 * Elige una opción por el texto visible y no por el `value`: los ids los genera
 * la base y el orden del listado depende de las filas que otros specs creen en
 * paralelo. El número de historia clínica del paciente tampoco es estable entre
 * corridas, por eso el match es por prefijo.
 */
async function elegirPorTexto(page: Page, selectId: string, texto: string): Promise<void> {
  const select = page.locator(`#${selectId}`)
  const opcion = select.locator('option', { hasText: texto }).first()
  const valor = await opcion.getAttribute('value')
  expect(valor, `no se encontró la opción "${texto}" en #${selectId}`).not.toBeNull()
  await select.selectOption(valor as string)
}

/** Completa fecha y hora (el resto de los selectores ya están elegidos). */
async function agendar(
  page: Page,
  turno: { dia: string; desde: string; conPaciente?: boolean },
): Promise<void> {
  if (turno.conPaciente ?? true) {
    await elegirPorTexto(page, 'turno-paciente', SEED_PATIENT)
  }
  await page.getByLabel('Fecha').fill(turno.dia)
  await page.getByLabel('Hora').fill(turno.desde)
  await page.getByRole('button', { name: 'Guardar turno' }).click()
}

async function irAlFormulario(page: Page): Promise<void> {
  await page.getByRole('link', { name: 'Agendar turno' }).click()
  await expect(page.getByRole('heading', { name: 'Nuevo turno' })).toBeVisible()
  // El formulario aparece cuando terminó el `Promise.all` de pacientes,
  // profesionales y sillones.
  await expect(page.locator('#turno-profesional')).toBeVisible()
}

/**
 * Login por API sobre el **mismo contexto** del browser: cambia las cookies sin
 * pasar por `/login` (que redirige a la home si ya hay sesión). Se usa solo para
 * cambiar de tenant dentro de un test.
 */
async function loginApi(page: Page, tenant: string, email: string): Promise<void> {
  const response = await page.request.post('/api/v1/auth/login', {
    data: { tenant_slug: tenant, email, password: E2E_PASSWORD },
  })
  expect(response.status(), await response.text()).toBe(200)
}

test.describe.configure({ mode: 'serial' })

test.describe('agenda: alta de turno contra el backend real', () => {
  test('recepción agenda un turno y ve el fin y la duración que derivó el servidor', async ({
    page,
  }) => {
    await login(page, FRONT_DESK_EMAIL)
    await irAlFormulario(page)

    await elegirPorTexto(page, 'turno-profesional', SEED_PROFESSIONAL)
    await elegirPorTexto(page, 'turno-sillon', SEED_CHAIR)

    const dia = fecha(0)
    await agendar(page, { dia, desde: '09:00' })

    // La UI no manda `fin` ni `duracion_min`: los calcula el backend (RN-AG-03)
    // a partir de la duración por defecto del profesional (30 min, sin regla).
    const confirmacion = page.getByText(/Turno creado para el/)
    await expect(confirmacion).toBeVisible()
    await expect(confirmacion).toContainText('09:00')
    await expect(confirmacion).toContainText('09:30')
    await expect(confirmacion).toContainText('30 min')
    await expect(confirmacion).toContainText('pendiente')
  })

  test('un turno solapado del mismo recurso muestra el 409 con recurso y rango', async ({
    page,
  }) => {
    await login(page, FRONT_DESK_EMAIL)
    await irAlFormulario(page)

    await elegirPorTexto(page, 'turno-profesional', SEED_PROFESSIONAL)
    await elegirPorTexto(page, 'turno-sillon', SEED_CHAIR)

    const dia = fecha(1)
    // Sin paciente identificado: el conflicto que se busca es de recurso, no de
    // RN-AG-10 (que se evalúa primero).
    await agendar(page, { dia, desde: '10:00', conPaciente: false })
    await expect(page.getByText(/Turno creado para el/)).toBeVisible()

    await agendar(page, { dia, desde: '10:15', conPaciente: false })

    const alerta = page.getByRole('alert').filter({ hasText: 'turno_solapado' })
    await expect(alerta).toBeVisible()
    await expect(alerta).toContainText('El horario se solapa con otro turno del mismo recurso')
    await expect(alerta).toContainText('Recurso en conflicto: profesional')
    await expect(alerta).toContainText('10:00')
    await expect(alerta).toContainText('10:30')
    // Los valores cargados se conservan: recepción corrige el horario sin reescribir todo.
    await expect(page.locator('#turno-profesional')).not.toHaveValue('')
    await expect(page.getByLabel('Hora')).toHaveValue('10:15')
  })

  test('RN-AG-10 gana sobre el solape de recursos: el mismo paciente avisa primero', async ({
    page,
  }) => {
    await login(page, FRONT_DESK_EMAIL)
    await irAlFormulario(page)

    await elegirPorTexto(page, 'turno-profesional', SEED_PROFESSIONAL)
    await elegirPorTexto(page, 'turno-sillon', SEED_CHAIR)

    // El turno de las 09:00 del primer test es del paciente canónico: uno nuevo a
    // las 09:15 con el mismo paciente choca contra RN-AG-10 **antes** que contra
    // el solape del profesional y del sillón.
    await agendar(page, { dia: fecha(0), desde: '09:15' })

    const alerta = page.getByRole('alert').filter({ hasText: 'paciente_solapado' })
    await expect(alerta).toBeVisible()
    await expect(alerta).toContainText('El paciente ya tiene un turno con ese profesional')
    await expect(alerta).toContainText('Recurso en conflicto: paciente')
  })

  test('un rol sin appointment.create no ve el enlace y la API responde 403', async ({ page }) => {
    // `ajeno@example.test` es `professional`: tiene `appointment.read` pero no
    // `appointment.create`, así que la guarda de RBAC corta antes del dominio.
    await login(page, OTHER_TENANT_EMAIL, OTHER_TENANT)

    await expect(page.getByRole('link', { name: 'Agendar turno' })).toHaveCount(0)

    await page.goto('/turnos/nuevo')
    await expect(page.getByText('No tenés permiso para ver esta sección.')).toBeVisible()

    const response = await page.request.post('/api/v1/appointments', {
      data: {
        professional_id: '00000000-0000-4000-8000-000000000001',
        chair_id: '00000000-0000-4000-8000-000000000002',
        patient_id: null,
        inicio: `${fecha(2)}T11:00:00-03:00`,
      },
    })

    expect(response.status()).toBe(403)
    const body = (await response.json()) as { code?: string; id?: string }
    expect(body.code).toBe('forbidden')
    expect(body.id).toBeUndefined()
  })

  test('un recurso inexistente responde 404 recurso_no_encontrado, nunca 403', async ({ page }) => {
    await loginApi(page, TENANT, FRONT_DESK_EMAIL)

    const chairs = (await (await page.request.get('/api/v1/clinic/chairs')).json()) as {
      chairs: { id: string; nombre: string }[]
    }
    const sillon = chairs.chairs.find((item) => item.nombre === SEED_CHAIR)
    expect(sillon, `falta el sillón sembrado "${SEED_CHAIR}"`).toBeDefined()

    // Un id que no existe en el tenant responde lo mismo que un id de otro tenant
    // (RN-EX-06): 404, sin filtrar la existencia del recurso.
    const response = await page.request.post('/api/v1/appointments', {
      data: {
        professional_id: '00000000-0000-4000-8000-000000000003',
        chair_id: sillon?.id,
        patient_id: null,
        inicio: `${fecha(2)}T11:00:00-03:00`,
      },
    })

    expect(response.status()).toBe(404)
    const body = (await response.json()) as { code?: string; recurso?: string; id?: string }
    expect(body.code).toBe('recurso_no_encontrado')
    expect(body.recurso).toBe('professional')
    expect(body.id).toBeUndefined()
  })
})
