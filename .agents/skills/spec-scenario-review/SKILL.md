---
name: spec-scenario-review
description: Revisa los artefactos de un change de OpenSpec (proposal, design, specs) del proyecto odontología-saas ANTES de implementar, verificando que cada requisito tenga al menos tres escenarios verificables (funcionamiento esperado, error de negocio y caso borde), que las reglas de negocio (RN-XX) no sean ambiguas y que el aislamiento cross-tenant (RN-TEN-02) esté cubierto. Usala siempre que se proponga, actualice o vaya a aplicarse un change, cuando el usuario pregunte "¿faltan casos borde?", "revisá la spec", "¿están los escenarios?", o antes de correr /opsx:apply. No la uses para implementar código ni para escribir la spec desde cero: eso es openspec-propose.
---

# Spec Scenario Review

Esta skill existe para atrapar, **antes de escribir código**, los huecos que después cuestan caro: requisitos sin escenario de error, reglas de negocio ambiguas, casos borde sin definir y cambios que tocan tablas con `tenant_id` sin su test de aislamiento. El objetivo no es "aprobar" la spec: es producir una lista corta y accionable de huecos y escenarios faltantes que el equipo pueda cerrar en minutos.

## Cuándo se activa

- Después de `/opsx:propose` o `/opsx:update`, antes de `/opsx:apply`.
- Cuando el usuario pide "revisar escenarios", "revisar la spec", "¿faltan casos borde?", "¿esto está completo?".
- Cuando un change toca reglas de negocio (RN-XX), tenancy (`tenant_id`), agenda/turnos, historia clínica o facturación.
- Como gate previo al archivado: si la spec no tiene escenarios verificables, el change no está listo para contarse como completo.

## Entradas

1. El change a revisar: `openspec/changes/<nombre>/`
   - `proposal.md` (qué y por qué)
   - `design.md` (cómo)
   - `specs/**/spec.md` (delta con ADDED/MODIFIED/REMOVED/RENAMED)
   - `tasks.md` (cómo se verificará)
2. La knowledge base relevante (leer solo lo que el change toca):
   - `knowledge-base/05_reglas_de_negocio.md` (códigos RN-XX)
   - `knowledge-base/04_modelo_de_datos.md` (entidades y `tenant_id`)
   - `knowledge-base/03_actores_y_roles.md` (si hay permisos)
   - `knowledge-base/07_flujos_principales.md` (flujos y errores)
   - `knowledge-base/10_preguntas_abiertas.md` (si el change depende de una pregunta abierta)

## Procedimiento

1. **Extraer requisitos.** Listá cada requisito de la delta spec (cada `### Requirement:` y sus escenarios). Si un requisito no tiene escenarios, ya es un hueco.
2. **Clasificar escenarios.** Para cada requisito, verificá que existan al menos tres:
   - **Esperado**: el camino feliz, con datos válidos.
   - **Error de negocio**: una regla RN-XX violada (solapamiento, tenant ajeno, transición de estado inválida, etc.).
   - **Borde**: límite o caso raro (duración 0, cambio de horario, feriado, recurso inexistente, concurrencia, dato vacío).
3. **Cruzar con las reglas de negocio.** Buscá el código `RN-{DOMINIO}-{NN}` que aplica. Si la spec no lo cita o lo interpreta distinto a la KB, marcá la ambigüedad.
4. **Verificar tenancy (RN-TEN-02).** Si el change toca una tabla con `tenant_id`:
   - ¿La spec incluye un escenario cross-tenant (tenant A no ve ni modifica datos de tenant B)?
   - ¿El `tenant_id` se resuelve del token/sesión y nunca del body/query?
   - ¿Se planifica el test de aislamiento en `tasks.md`?
   Si falta cualquiera, es **bloqueante**.
5. **Verificar que las tareas cubran los escenarios.** Cada escenario de la spec debe tener al menos una tarea de verificación en `tasks.md` (test, migración, constraint, etc.). Si un escenario no tiene cómo comprobarse, es un hueco.
6. **Emitir el informe** con el formato de abajo. No reescribas la spec: señalá qué falta y proponé el escenario faltante en una línea.

## Escenarios: taxonomía y ejemplos

| Tipo | Qué prueba | Ejemplo (agenda) |
|------|-----------|------------------|
| Esperado | El flujo válido completo | Crear un turno en un hueco libre del profesional y del sillón |
| Error de negocio | Una RN-XX violada | Mismo profesional, mismo horario → rechazo (RN-AG-02) |
| Borde | Límite o rareza | Turno que termina justo cuando empieza otro; feriado; duración 0; concurrencia de dos requests |

Evitá escenarios tautológicos ("el endpoint devuelve 200 porque el código devuelve 200") y escenarios acoplados a la implementación ("se llama a X método"). Un buen escenario se lee como una regla del negocio y sobrevive a un refactor.

## Checks específicos del proyecto

- **RN-TEN-02** (gate de merge): toda tabla de negocio tiene `tenant_id NOT NULL` + RLS; sin test cross-tenant el change no se considera completo.
- **RN-AG-02** (agenda): anti-solapamiento por profesional y por sillón; el doble mecanismo (validación en aplicación + `EXCLUDE USING gist` en Postgres) debe estar cubierto por escenarios separados.
- **RN-CMP-02** (historia clínica): append-only con `supersedes_id`; nunca `UPDATE`/`DELETE`.
- **ARCA** (facturación): nunca síncrono en un request; Outbox + Celery con estados `BORRADOR → PENDIENTE → EMITIDO/RECHAZADO`; idempotencia.
- **Auth**: `tenant_id` del token, cookie `httpOnly`, refresh rotativo; el escenario de acceso denegado debe existir.

## Formato de salida

Usá exactamente esta estructura:

```markdown
# Revisión de escenarios — <nombre del change>

## Veredicto
[LISTO PARA APLICAR | FALTAN ESCENARIOS | BLOQUEADO]

## Cobertura por requisito
| Requisito | Esperado | Error de negocio | Borde | RN citada | Estado |
|-----------|----------|------------------|-------|-----------|--------|
| ... | ✅/❌ | ✅/❌ | ✅/❌ | RN-XX | OK/Falta ... |

## Huecos detectados
1. **<requisito>**: falta el escenario de <tipo>. Sugerencia: <una línea>.
2. ...

## Tenancy (RN-TEN-02)
- [ ] El change toca tablas con `tenant_id`
- [ ] Hay escenario cross-tenant
- [ ] `tenant_id` sale del token, no del body
- [ ] `tasks.md` incluye el test de aislamiento
[Si no toca tenancy: "No aplica".]

## Verificación en tasks.md
| Escenario | Tarea de verificación | Estado |
|-----------|----------------------|--------|
| ... | ... | ✅/❌ |

## Próximo paso
[Qué corregir antes de aplicar/archivar, en 1-3 bullets]
```

## Criterios de revisión del resultado

Antes de dar por buena una revisión, comprobá:

- Cada requisito tiene **≥3 escenarios** (o una justificación explícita de por qué no aplica uno).
- Cada escenario tiene una **tarea de verificación** concreta.
- Las reglas citadas coinciden con `knowledge-base/05_reglas_de_negocio.md`.
- Si hay `tenant_id`, el check de tenancy está completo y el test cross-tenant está en `tasks.md`.
- El veredicto es honesto: no marques "LISTO" si falta un bloqueante de tenancy o un error de negocio.

## Ejemplo breve

**Entrada**: delta spec de "crear turno" con un solo escenario (camino feliz).

**Salida** (resumida):
- Veredicto: FALTAN ESCENARIOS.
- Huecos: falta error de negocio (solapamiento RN-AG-02) y borde (turno contiguo / concurrencia).
- Tenancy: el change toca `appointment` con `tenant_id`; falta escenario cross-tenant y test en `tasks.md` → BLOQUEANTE.
- Próximo paso: agregar los 2 escenarios faltantes y la tarea de test de aislamiento antes de `/opsx:apply`.
