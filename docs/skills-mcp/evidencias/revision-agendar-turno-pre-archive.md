# Revisión de escenarios — `agendar-turno-sin-solapamiento` (gate pre-archive)

> Skill: `spec-scenario-review`. Ejecutada el **2026-11-12** sobre el change ya implementado,
> como gate previo al archivado. Entradas: `proposal.md`, `design.md`, `specs/agenda/appointments/spec.md`
> (26 escenarios) y `tasks.md` (13 tasks), cruzados con
> `knowledge-base/05_reglas_de_negocio.md` (RN-AG-02/03/09/10, RN-TEN-02/03, RN-EX-06) y
> `knowledge-base/04_modelo_de_datos.md` (`appointment.tenant_id`).
>
> Esta es la **segunda** pasada: la primera (`revision-agendar-turno-post-fix.md`) fue pre-apply.
> Acá se revisó además que la spec **coincida con lo implementado y verificado**.

## Veredicto

**LISTO PARA ARCHIVAR.** Las 6 requirements tienen camino esperado, error de negocio y borde, cada
escenario tiene test que lo verifica y el check de tenancy está completo. En esta pasada se corrigieron
en la delta 5 defectos de redacción que habrían quedado congelados en la spec principal (ninguno
implicó cambiar código: lo implementado ya era lo correcto).

## Cobertura por requisito

| Requisito | Esperado | Error de negocio | Borde | RN citada | Estado |
|---|---|---|---|---|---|
| Crear turno reservando profesional y sillón | ✅ 201 con `fin`/`duracion_min` derivados | ✅ `409 recurso_inactivo`, `403 forbidden`, `401` sin sesión / sin membership | ✅ `422 invalid_request` (offset, campo desconocido, UUID mal formado) | RN-AG-01/03, RN-TEN-03 | OK |
| Prevenir solapamiento por profesional y por sillón | ✅ 201 sin conflicto | ✅ `409 turno_solapado` por `professional` y por `chair`, con `rangoEnConflicto` | ✅ cancelado/no_asistio no bloquea · contiguo `[inicio, fin)` → 201 · solape **solo por buffer** → 409 · concurrencia: uno 201 y otro 409 por `EXCLUDE` | RN-AG-02/03 | OK (el borde de buffers era hueco: agregado en esta pasada) |
| Derivar duración y buffers del tipo de práctica | ✅ `slot_min` de la regla que declara el tipo, con buffers | ✅ `422` por tipo fuera del enum · `409 duracion_invalida` | ✅ sin `tipo_practica` → `duracion_default_min` y buffers 0/0 | RN-AG-03 | OK (con nota: `duracion_invalida` es guarda defensiva, ver §Huecos) |
| Almacenar horarios en UTC | ✅ RFC 3339 con offset → `timestamptz` en UTC | ✅ `422` sin offset (nunca asume la zona del servidor) | ✅ turno que cruza la medianoche: `fin` en el día siguiente UTC | RN-AG-09 | OK |
| Prevenir turnos solapados del mismo paciente con el mismo profesional | ✅ 201 sin conflicto | ✅ `409 paciente_solapado` (estados `pendiente`/`confirmado`/`en_curso`) | ✅ otro profesional / otro rango / `cancelado` → 201 · `patient_id = NULL` → RN-AG-10 no se evalúa | RN-AG-10 | OK (escenario corregido: ver §Huecos 1) |
| Aislar la agenda por tenant | ✅ turnos homólogos de dos tenants conviven | ✅ recurso de otro tenant → `404` (nunca 403) · `tenant_id` ajeno en body/query/header → 404 o se ignora | ✅ RLS `FORCE` con `SET ROLE odontologia_app` + prueba de mutación | RN-TEN-02/03, RN-EX-06 | OK |

## Huecos detectados (y cómo se cerraron)

1. **RN-AG-10, escenario «Turno sin paciente identificado»** (era bloqueante de coherencia): decía que
   con `patient_id = NULL` y otro turno solapado del mismo profesional la respuesta era `201`. Bajo
   RN-AG-02 eso es **imposible**: el `EXCLUDE` del profesional rechaza el turno igual. Se reescribió el
   escenario: RN-AG-10 no se evalúa (`paciente_solapado` nunca aparece), pero RN-AG-02 sigue siendo
   regla dura → `409 turno_solapado`. El test
   `test_sin_paciente_identificado_rn_ag_10_no_aplica_y_gana_rn_ag_02` ya probaba exactamente eso.
2. **RN-AG-02 mencionaba `tstzrange`**: `timestamptz - interval` no es `IMMUTABLE` y Postgres rechaza
   la expresión en un índice (*«functions in index expression must be marked IMMUTABLE»*). La spec
   ahora exige `tsrange` sobre marcas UTC y explica por qué; coincide con `007_agenda`.
3. **Faltaba el borde «solape producido solo por un buffer»**: el rango clínico no se toca pero el
   bloqueado sí. Estaba implementado y testeado (2 tests) pero no declarado; se agregó como escenario.
4. **Faltaba el escenario de autorización (`403`)**: el requisito solo hablaba de sesión/membership.
   La guarda de RBAC (`appointment.create`, C-04) responde `403 forbidden`; se agregó el escenario y
   se cubre en `test_appointments_http.py` y en el e2e (`un rol sin appointment.create…`).
5. **`duracion_invalida` es inalcanzable por API con los `CHECK` vigentes**
   (`duracion_default_min BETWEEN 5 AND 480`, `slot_min > 0`). No se borra el escenario: se anotó como
   guarda defensiva y el test HTTP muta el esquema (drop/re-add del `CHECK`) restaurándolo en
   `finally`. Queda como límite declarado, no como hueco abierto.

## Tenancy (RN-TEN-02)

- [x] El change toca tablas con `tenant_id` (`appointment`, y lee `professional`/`chair`/`patient`).
- [x] Hay escenario cross-tenant: «Recurso de otro tenant», «Turnos de un tenant invisibles para otro»,
      «`tenant_id` en el body se ignora», «`tenant_id` del body no habilita recursos ajenos».
- [x] `tenant_id` sale del token/sesión; body, query y header se ignoran (`model_validator` descarta
      `tenant_id` del payload antes de validar; el router ni lee query/header).
- [x] `tasks.md` incluye el test de aislamiento (task 6.1) **con prueba de mutación** obligatoria.

Evidencia: `docs/skills-mcp/evidencias/gate-rls-agenda.md` (8 tests verdes; con RLS apagada y 5 filtros
quitados → 5 failed, `assert 201 == 404`; restaurado → 8 passed).

## Verificación en tasks.md

| Escenario (abreviado) | Tarea / test | Estado |
|---|---|---|
| 201 con `fin` derivado, sin `tenant_id` en la respuesta | task 2.1 · `test_appointments_http.py::test_s1_1_*` | ✅ |
| `422` por campo faltante / UUID / sin offset / `fin` enviado | tasks 1.1 y 2.1 · `tests/unit/agenda/test_appointments.py`, `test_s1_2_*` | ✅ |
| `409 recurso_inactivo` (profesional y sillón) | task 3.2 · `test_appointments_resources.py::test_s1_3_*` | ✅ |
| `401` sin sesión / sin membership | task 2.3 · `test_2_3_*` | ✅ |
| `403` sin `appointment.create` | task 7.1 (guarda C-04) · `test_appointments_http.py` + e2e `appointments.spec.ts` | ✅ |
| `409 turno_solapado` por profesional y por sillón | task 3.1 · `test_appointments_overlap.py::test_s2_1/test_s2_2` | ✅ |
| `cancelado`/`no_asistio` no bloquean | task 3.1 · `test_s2_3` | ✅ |
| Contiguo `[inicio, fin)` → 201 | task 3.1 · `test_s2_4` | ✅ |
| Solape solo por buffer (posterior y previo) | task 3.1 · `test_el_buffer_posterior_*`, `test_el_buffer_previo_*` | ✅ |
| Concurrencia: `EXCLUDE` (`23P01`) | task 4.1 · `test_appointments_service.py::test_s2_5` | ✅ |
| Duración por regla con buffers / sin tipo / fuera del enum | task 1.1 · unit `test_appointments.py` | ✅ |
| `409 duracion_invalida` | task 2.3 · `test_s3_4_*` (con mutación del `CHECK`) | ✅ |
| UTC, sin offset, medianoche | tasks 2.1 y 4 · `test_s4_3_*`, `test_s1_1_*` | ✅ |
| RN-AG-10 (409 / otros casos / `NULL` bajo RN-AG-02) | task 5.1 · `test_appointments_patient_rule.py` (8 tests) | ✅ |
| Cross-tenant (404, `tenant_id` ajeno, homólogos, `SET ROLE`) | task 6.1 · `test_appointments_rls.py` (8 tests) + mutación | ✅ |
| UI: alta, 409 visible, 404 legible, permisos | task 7.1 · `datetime.test.ts`, `NewAppointmentPage.test.tsx`, e2e `appointments.spec.ts` | ✅ |

## Próximo paso

1. Archivar el change (`/opsx:archive`): la delta ya está corregida, así que la spec principal hereda
   los escenarios coherentes con la implementación.
2. Dejar constancia en el resumen de entrega de los dos límites declarados: `duracion_invalida` como
   guarda defensiva y la zona horaria del formulario (la aporta el navegador porque `SessionOut` aún no
   expone `tenant.timezone`).
3. No hay cambios de código pendientes por esta revisión: los 5 defectos eran de redacción de la spec.
