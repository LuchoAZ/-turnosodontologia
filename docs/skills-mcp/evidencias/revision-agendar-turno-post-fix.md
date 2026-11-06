# Evidencia — `spec-scenario-review` (3.ª pasada, verificación final) sobre `agendar-turno-sin-solapamiento`

**Fecha de ejecución**: 2026-11-06 · **Skill**: `spec-scenario-review` (`.agents/skills/spec-scenario-review/SKILL.md`)
**Motivo**: verificación final de los 3 defectos de la ronda anterior sobre los 4 artefactos releídos desde disco, más el chequeo de los 24 escenarios y de contradicciones spec↔design↔tasks.
**Change revisado**: `openspec/changes/agendar-turno-sin-solapamiento/`
**Entradas leídas**: `proposal.md`, `design.md`, `specs/agenda/appointments/spec.md`, `tasks.md`; `knowledge-base/05_reglas_de_negocio.md` (§ Tenancy, § Agenda), `knowledge-base/04_modelo_de_datos.md` (§ Agenda), `CHANGES.md`, `openspec/changes/archive/`, `backend/alembic/versions/`.

## Historial de la revisión
| Pasada | Fecha | Veredicto | Resultado |
|--------|-------|-----------|-----------|
| 1.ª | 2026-11-05 | FALTAN ESCENARIOS | 6 huecos (`revision-agendar-turno.md`) — cerrados |
| 2.ª | 2026-11-06 | FALTAN ESCENARIOS | 2 defectos de contrato/verificación + 1 dependencia — cerrados |
| 3.ª | 2026-11-06 | **LISTO PARA APLICAR** | verificación final: `tenant_id`, `fin`/UTC, rango del requisito y `patient_id NULL` cerrados; 24/24 escenarios con tarea; sin contradicciones nuevas |

---

# Revisión de escenarios — agendar-turno-sin-solapamiento

## Veredicto
**LISTO PARA APLICAR**

Los 3 defectos de la ronda anterior están cerrados y no apareció ninguna contradicción nueva entre spec, design y tasks. Los 24 escenarios de la delta tienen al menos una tarea de verificación. Queda una sola condición, de aplicabilidad y no de spec: C-03/C-05/C-06 todavía no existen.

## Cobertura por requisito
| Requisito | Esperado | Error de negocio | Borde | RN citada | Estado |
|-----------|----------|------------------|-------|-----------|--------|
| Crear turno reservando profesional y sillón | ✅ Turno creado (`201` con `id`, `inicio`, `fin`, `duracion_min`, `estado=pendiente`, `origen=recepcion`) | ✅ Recurso inactivo (`409`); sin sesión (`401`); sesión sin membership activa (`401`) | ✅ Payload inválido (`422`: faltante, UUID, `inicio` sin offset, `fin`/`duracion_min` enviados) | RN-AG-01, RN-TEN-03 | OK |
| Prevenir solapamiento por profesional y por sillón | ✅ Turno sin solape (`201`) | ✅ Solape por `professional` y por `chair` (`409` + recurso + rango) | ✅ Contiguo (buffers 0); `cancelado`/`no_asistio`; concurrencia `23P01` | RN-AG-02 | OK |
| Derivar duración y buffers del tipo de práctica | ✅ `fin = inicio + duracion_min`; buffers snapshot; rango bloqueado `[inicio-bp, fin+bpost)` | ✅ `tipo_practica` fuera del enum (`422`); duración `<= 0` (`409 duracion_invalida`) | ✅ Sin `tipo_practica` → default del profesional, buffers 0 | RN-AG-03 | OK |
| Almacenar horarios en UTC | ✅ `inicio` RFC 3339; `fin` derivado; ambos en UTC | ✅ `inicio` sin offset (`422`) | ✅ Cruce de medianoche | RN-AG-09 | OK |
| Prevenir turnos solapados del mismo paciente con el mismo profesional | ✅ Paciente sin solape (`201`) | ✅ Solape `pendiente`/`confirmado`/`en_curso` (`409`) | ✅ Otro rango/profesional/`cancelado`/`no_asistio`; `patient_id NULL` → `201` | RN-AG-10 | OK |
| Aislar la agenda por tenant | ✅ `tenant_id` de body/query/header descartado → `201` en A | ✅ Recurso ajeno (`404`); `tenant_id` de B + recursos de B (`404`) | ✅ Turnos de un tenant invisibles para otro | RN-TEN-02, RN-TEN-03, RN-EX-06 | OK |

### Cierre de los 4 puntos verificados
| # | Punto | Estado | Evidencia |
|---|-------|--------|-----------|
| 1 | Contradicción de `tenant_id` | ✅ cerrado | `design.md:51` ("el borde HTTP **descarta** `tenant_id` de body/query/header antes de validar… `extra = "forbid"` para el resto"); `tasks.md:12` (descarta `tenant_id`; el unitario exige "`tenant_id` enviado → se ignora (no `422`)"); `tasks.md:16` y `tasks.md:35` (se ignora → 201 en A); ya no contradice `spec.md:11` ni `spec.md:143-146` |
| 2 | UTC con `fin` de entrada | ✅ cerrado | `spec.md:97` ("el payload envía `inicio`"), `spec.md:98` ("el servidor deriva `fin`"), `spec.md:102` ("`inicio` llega sin offset"); sin restos de `inicio`+`fin` como payload (grep sobre los 4 artefactos) |
| 3 | Rango del requisito de solapamiento | ✅ cerrado | `spec.md:40` ("cuyo rango bloqueado `[inicio - buffer_previo_min, fin + buffer_posterior_min)`"); coherente con `spec.md:69/74`, `design.md:35/41`, `tasks.md:7/22` |
| 4 | `patient_id NULL` sin tarea | ✅ cerrado | `spec.md:124-127` + `tasks.md:31` (5.1 incluye `patient_id = NULL` → `201` y la verificación "cubre el caso sin paciente identificado") |

## Huecos detectados
**Ninguno.** No hay escenario sin tarea, regla ambigua ni contradicción de contrato en el barrido final spec ↔ design ↔ tasks:
- payload: solo `inicio`, `fin`/`duracion_min` derivados y con `422` si se envían (`spec.md:11/20`, `design.md:42/51`, `tasks.md:12`);
- `tenant_id`: descartado antes de validar, nunca rechazado (`design.md:51`, `tasks.md:12/16/35`);
- resolución de rango: `duracion_min` persistida, `fin = inicio + duracion_min`, buffers snapshot y rango bloqueado en pre-chequeo y `EXCLUDE` (`spec.md:40/69`, `design.md:35/41`, `tasks.md:7/12/22`);
- RN-AG-10: lista explícita de estados y exclusión de `patient_id NULL` (`spec.md:112`, `design.md:35`, `tasks.md:31`);
- DDL: columnas, `SET ROLE odontologia_app`, `down_revision` = head real (`tasks.md:7/8`).

*Observación heredada, no defecto:* la RLS de `chair`/`professional`/`patient` (`spec.md:131`) se verifica en C-05/C-06; 6.1 cubre `appointment` y el `404` funcional.

## Tenancy (RN-TEN-02)
- [x] El change toca tablas con `tenant_id` (`appointment`; referencia `chair`, `professional`, `patient`)
- [x] Hay escenario cross-tenant (4 escenarios en "Aislar la agenda por tenant")
- [x] `tenant_id` sale del token, no del body (requisito, D2, 2.2 y 6.1; body/query/header ajeno → 404)
- [x] `tasks.md` incluye el test de aislamiento (6.1, gate de merge, con `SET ROLE odontologia_app` y prueba de mutación)

**Resultado del check**: completo. Sin bloqueante de tenancy.

## Verificación en tasks.md
| Escenario | Tarea de verificación | Estado |
|-----------|----------------------|--------|
| Turno creado (201) | 2.1 | ✅ |
| Payload inválido (422, incl. `fin`/`duracion_min`) | 1.1 | ✅ |
| Recurso inactivo (409) | 3.2 | ✅ |
| Operación sin sesión (401) | 2.3 | ✅ |
| Sesión sin membership activa (401) | 2.3 | ✅ |
| Solape por profesional (409) | 3.1 | ✅ |
| Solape por sillón (409) | 3.1 | ✅ |
| Cancelado / no asistió no bloquea (201) | 3.1 | ✅ |
| Turno contiguo con buffers 0 (201) | 3.1 | ✅ |
| Doble booking concurrente (23P01 → 409) | 4.1 | ✅ |
| Duración por tipo + buffers | 1.1 (+ 3.1) | ✅ |
| Sin tipo de práctica | 1.1 | ✅ |
| Tipo de práctica fuera del enum (422) | 1.1 | ✅ |
| Duración no derivable (409 `duracion_invalida`) | 1.1 + 2.3 (HTTP) | ✅ |
| Rango UTC persistido | 2.1 | ✅ |
| Fecha sin offset (422) | 1.1 | ✅ |
| Turno que cruza la medianoche | 2.1 | ✅ |
| Paciente con turno solapado (409) | 5.1 | ✅ |
| Paciente en otro rango / otro profesional / cancelado (201) | 5.1 | ✅ |
| Turno sin paciente identificado (`patient_id NULL`) | 5.1 | ✅ |
| Recurso de otro tenant (404) | 6.1 (a) | ✅ |
| Turnos de un tenant invisibles para otro | 6.1 (c) | ✅ |
| `tenant_id` en body/query/header descartado (201 en A) | 1.1 (unitario) + 2.1 + 6.1 (b) | ✅ |
| `tenant_id` del body no habilita recursos ajenos (404) | 6.1 (b) | ✅ |

**24/24 escenarios con verificación.**

## Próximo paso
1. **Condición de aplicabilidad (no es defecto de spec)**: C-03, C-05 y C-06 no existen todavía ni como changes ni como migraciones (`backend/alembic/versions` solo tiene `c01_baseline` y `002_core_tenancy`). El apply debe pausarse hasta que existan, y la migración debe usar el siguiente número libre con `down_revision` = head real de ese momento.
2. Recordatorio de diseño ya declarado en `design.md:94`: confirmar el supuesto de D3 (`availability_rule.slot_min` como duración por `tipo_practica`) con el docente antes del apply; no cambia el contrato ni las tareas.
3. Con el entorno de dependencias disponible, el change queda habilitado para `/opsx:apply` tal cual está.
