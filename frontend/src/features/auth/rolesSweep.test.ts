import { readFileSync, readdirSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Barrido de la task 10.4: la UI decide visibilidad por **permiso**, nunca
 * comparando `session.roles` contra literales.
 *
 * Un barrido textual es tosco pero es exactamente el invariante que queremos
 * congelar: si mañana alguien escribe `session.roles.includes('owner')` para
 * mostrar un botón, este test lo frena antes de que llegue a main. Las
 * excepciones son el contrato (`api/auth.ts` declara el tipo) y el catálogo de
 * etiquetas de la propia pantalla de Equipo.
 */

const SRC = join(process.cwd(), 'src')

const EXEMPT = new Set(['api/auth.ts', 'features/team/roles.ts'])

const ROLE_LITERAL =
  /['"](owner|clinical_admin|professional|front_desk|billing|assistant|accountant|patient|external_lab)['"]/

const ROLES_REFERENCE = /\broles\b|\bsession\.roles\b/

function sourceFiles(): string[] {
  const entries = readdirSync(SRC, { recursive: true }) as string[]
  return entries
    .filter((entry) => /\.(ts|tsx)$/.test(entry))
    .filter((entry) => !/\.test\.(ts|tsx)$/.test(entry))
    .map((entry) => entry.split(sep).join('/'))
}

describe('barrido de roles en la UI', () => {
  it('no compara roles contra literales para decidir visibilidad', () => {
    const violations: string[] = []

    for (const file of sourceFiles()) {
      if (EXEMPT.has(file)) continue
      const lines = readFileSync(join(SRC, file), 'utf8').split(/\r?\n/)
      lines.forEach((line, index) => {
        if (ROLES_REFERENCE.test(line) && ROLE_LITERAL.test(line)) {
          violations.push(`${relative(SRC, join(SRC, file))}:${index + 1}: ${line.trim()}`)
        }
      })
    }

    expect(violations).toEqual([])
  })

  it('el barrido realmente detecta una comparación prohibida', () => {
    // Autotest: si el regex dejara de matchear, el gate quedaría vacío.
    expect(ROLES_REFERENCE.test("if (session.roles.includes('owner')) {")).toBe(true)
    expect(ROLE_LITERAL.test("if (session.roles.includes('owner')) {")).toBe(true)
    expect(ROLES_REFERENCE.test("hasPermission('team.read')")).toBe(false)
  })
})
