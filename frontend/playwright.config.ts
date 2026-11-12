import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

const backendDir = fileURLToPath(new URL('../backend', import.meta.url))

// El puerto del SPA es configurable: Docker Desktop (u otro servicio) puede estar
// escuchando en 5173 y Playwright aborta si el puerto ya responde.
const WEB_PORT = process.env.E2E_WEB_PORT ?? '5173'
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`
const BACKEND_URL = `http://127.0.0.1:${process.env.E2E_BACKEND_PORT ?? '8000'}`

const webServers = [
  {
    command: 'uv run python scripts/e2e_server.py',
    cwd: backendDir,
    url: `${BACKEND_URL}/health`,
    timeout: 240_000,
    reuseExistingServer: false,
    stdout: 'pipe' as const,
    stderr: 'pipe' as const,
  },
  {
    command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
    url: WEB_URL,
    // Nunca reutilizar: un Vite viejo con el optimizador desactualizado sirve
    // módulos con 500 y el e2e falla sin causa evidente.
    reuseExistingServer: process.env.E2E_REUSE_SERVER === '1',
    timeout: 120_000,
  },
]

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  // 5 s (default) es corto para el primer login de la corrida: el backend real
  // arranca en frío (uvicorn + pool + argon2) y cuatro workers lo golpean a la
  // vez. Con 10 s el gate no se vuelve flaky; la app sigue respondiendo en <1 s
  // una vez tibia.
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? WEB_URL,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Backend real (Testcontainers + Alembic + seed) y Vite con el proxy `/api`.
  // `E2E_EXTERNAL_SERVER=1` desactiva ambos para apuntar a servidores ya vivos.
  webServer: process.env.E2E_EXTERNAL_SERVER === '1' ? undefined : webServers,
})
