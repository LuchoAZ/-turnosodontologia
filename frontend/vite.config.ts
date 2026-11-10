import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { configDefaults, defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // `VITE_PORT` permite correr el SPA en otro puerto cuando 5173 está ocupado
    // (p. ej. por Docker Desktop); Playwright lo usa vía `E2E_WEB_PORT`.
    port: Number(process.env.VITE_PORT ?? 5173),
    host: true,
    proxy: {
      // Mismo origen para el SPA: las cookies `HttpOnly` + `SameSite=Lax` del
      // backend viajan sin CORS ni `credentials` cross-site (ver docs/auth.md).
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/shared/test/setup.ts'],
    css: true,
    exclude: [...configDefaults.exclude, 'tests/e2e/**'],
  },
})
