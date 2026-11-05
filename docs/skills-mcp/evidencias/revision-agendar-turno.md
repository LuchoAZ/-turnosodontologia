# Evidencia — `spec-scenario-review` sobre `agendar-turno-sin-solapamiento`

**Fecha de ejecución**: 2026-11-05 · **Skill**: `spec-scenario-review` (`.agents/skills/spec-scenario-review/SKILL.md`)
**Change revisado**: `openspec/changes/agendar-turno-sin-solapamiento/`
**Entradas leídas**: `proposal.md`, `design.md`, `specs/agenda/appointments/spec.md`, `tasks.md`,
`knowledge-base/05_reglas_de_negocio.md` (§ Tenancy, § Agenda), `knowledge-base/04_modelo_de_datos.md` (§ Agenda).

---

# Revisión de escenarios — agendar-turno-sin-solapamiento

## Veredicto
**FALTAN ESCENARIOS**

## Cobertura por requisito
| Requisito | Esperado | Error de negocio | Borde | RN citada | Estado |
|-----------|----------|------------------|-------|-----------|--------|
| Crear turno reservando profesional y sillón | ✅ | ⚠️ (solo `422` de schema y `401`; falta recurso inexistente) | ❌ | RN-AG-01, RN-TEN-03 | Falta borde |
| Prevenir solapamiento por profesional y sillón | ✅ | ✅ | ❌ (no define turno contiguo) | RN-AG-02 | Falta borde |
| Derivar duración y buffers | ✅ | ❌ | ✅ (sin tipo de práctica) | RN-AG-03 | Falta error de negocio |
| Almacenar horarios en UTC | ✅ | ❌ | ❌ | RN-AG-09 | Faltan 2 escenarios |
| Prevenir turnos solapados del mismo paciente | ✅ | ✅ | ⚠️ (implícito en el 2.º escenario) | RN-AG-10 | Ambigüedad de "activo" |
| Aislar la agenda por tenant | ✅ | ✅ | ❌ (falta `tenant_id` en body ignorado) | RN-TEN-02, RN-TEN-03, RN-EX-06 | Falta borde |

## Huecos detectados

1. **Crear turno reservando profesional y sillón**: falta el escenario de **borde**. Sugerencia:
   *WHEN el `professional` está inactivo o el `chair` está deshabilitado en el tenant → THEN `404`/`409` y no se crea el turno* (definir cuál y con qué regla).
2. **Prevenir solapamiento**: falta el escenario de **borde** del turno contiguo. Sugerencia:
   *WHEN el turno nuevo empieza exactamente cuando termina otro (`nuevo.inicio == existente.fin`) → THEN `201`, porque el rango es `[inicio, fin)`*.
3. **Derivar duración y buffers**: falta el **error de negocio**. Sugerencia:
   *WHEN el `tipo_practica` no existe en el tenant o su duración es ≤ 0 → THEN `422`/`404` y no se crea el turno*.
4. **Almacenar horarios en UTC**: faltan **error de negocio** y **borde**. Sugerencia:
   *WHEN `inicio` llega sin offset de zona → THEN `422`*; *WHEN el turno cruza la medianoche o cae en un cambio de huso del tenant → THEN se persiste en UTC y la UI lo muestra en la zona del tenant sin corrimiento*.
5. **Paciente con turno solapado**: ambigüedad de regla. El requisito dice "turno en estado `pendiente`, `confirmado` o `en_curso`" pero el escenario 2 usa "estado activo". Sugerencia: reemplazar "activo" por la lista explícita de estados de RN-AG-10 en el texto del escenario.
6. **Aislar la agenda por tenant**: falta el escenario de **borde** de RN-TEN-03. Sugerencia:
   *WHEN el payload incluye un `tenant_id` del tenant B mientras la sesión es del tenant A → THEN el campo se ignora, el turno se crea (o falla por recurso ajeno) **en el tenant A**, nunca en B*.

## Tenancy (RN-TEN-02)
- [x] El change toca tablas con `tenant_id` (`appointment`, `chair`, `professional`, `patient`)
- [x] Hay escenario cross-tenant (requisito "Aislar la agenda por tenant", 2 escenarios)
- [x] `tenant_id` sale del token, no del body (requisito + tarea 2.2)
- [x] `tasks.md` incluye el test de aislamiento (tarea 6.1, gate de merge, con prueba de mutación)

**Resultado del check**: completo. No hay bloqueante de tenancy.

## Verificación en tasks.md
| Escenario | Tarea de verificación | Estado |
|-----------|----------------------|--------|
| Turno creado (201) | 2.1 | ✅ |
| Payload inválido (422) | 1.1 | ✅ |
| Sin sesión (401) | 2.2 (dependencia de C-03) | ✅ |
| Solape profesional / sillón (409) | 3.1 | ✅ |
| Cancelado / no asistió no bloquea | 3.1 | ✅ |
| Doble booking concurrente (23P01) | 4.1 | ✅ |
| Duración + buffers | 1.1 | ✅ |
| Sin tipo de práctica | 1.1 | ✅ |
| UTC persistido | 2.1 | ✅ |
| Paciente solapado (RN-AG-10) | 5.1 | ✅ |
| Cross-tenant (404 / invisibilidad) | 6.1 | ✅ |
| **Contiguo, tipo inexistente, fecha sin offset, `tenant_id` en body** | **sin tarea** | ❌ |

## Próximo paso
1. Agregar los 6 escenarios faltantes a `specs/agenda/appointments/spec.md` (contiguo, recurso inactivo, tipo de práctica inválido, fecha sin offset, cruce de medianoche, `tenant_id` en body).
2. Sumar la verificación de esos escenarios a las tareas 1.1, 3.1 y 6.1 de `tasks.md`.
3. Recién entonces el change queda `LISTO PARA APLICAR`; hoy **no** lo está (aunque no tiene bloqueantes de tenancy).
