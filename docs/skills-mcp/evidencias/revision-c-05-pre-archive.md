# Revisión de escenarios — c-05-clinic-setup (pre-archive)

> Gate de la skill `spec-scenario-review` ejecutado el **2026-11-11** sobre el change ya implementado,
> como paso previo al archivado. No revisa "si la spec está linda": verifica que cada escenario tenga
> hoy una prueba ejecutable que lo respalde. Datos de la corrida completa en `docs/clinic.md` § 11.
> Ejecutado manualmente porque las sub-sesiones no tienen permiso para la tool `skill`.

## Veredicto

**LISTO PARA APLICAR** (a archivar). 10 requisitos / 44 escenarios, todos con ≥3 escenarios, con las
tres clases cubiertas y con una tarea de verificación **ejecutada**. Gate de tenancy completo y
bloqueante (task 6.4 incluye prueba de mutación, documentada en `gate-rls-c-05.md`).

## Cobertura por requisito

| Requisito | Escenarios | Esperado | Error de negocio | Borde | RN citada | Estado |
|---|---|---:|---|---|---|---|
| Lectura de sillones | S1.1–S1.3 | ✅ S1.1 | ✅ S1.2 | ✅ S1.3 | RN-EX-03, RN-TEN-02 | OK |
| Alta de sillón | S2.1–S2.5 | ✅ S2.1 | ✅ S2.2, S2.3 | ✅ S2.4, S2.5 | RN-AG-06, RN-TEN-04 | OK |
| Actualización y baja lógica de sillón | S3.1–S3.5 | ✅ S3.1, S3.2 | ✅ S3.4, S3.5 | ✅ S3.3 | RN-EX-03, RN-TEN-02 | OK |
| Lectura de profesionales | S4.1–S4.3 | ✅ S4.1 | ✅ S4.2 | ✅ S4.3 | RN-TEN-02 | OK |
| Alta de profesional | S5.1–S5.6 | ✅ S5.1 | ✅ S5.2–S5.5 | ✅ S5.6 | RN-TEN-04 | OK |
| Desactivación de profesional | S6.1–S6.4 | ✅ S6.1 | ✅ S6.2, S6.4 | ✅ S6.3 | RN-EX-03 | OK |
| Reglas de disponibilidad | S7.1–S7.8 | ✅ S7.1, S7.6 | ✅ S7.2–S7.5, S7.7, S7.8 | ✅ S7.5, S7.8 | RN-AG-03 | OK |
| Aislamiento cross-tenant | S8.1–S8.4 | ✅ S8.1 | ✅ S8.2, S8.4 | ✅ S8.3 | RN-TEN-02, RN-TEN-03 | OK |
| Pantalla de configuración | S9.1–S9.3 | ✅ S9.1 | ✅ S9.2, S9.3 | ✅ S9.3 | RN-TEN-04 | OK |
| Catálogo visible de especialidades | S10.1–S10.3 | ✅ S10.1 | ✅ S10.2 | ✅ S10.3 | RN-TEN-02 | OK |

## Huecos detectados

Ninguno bloqueante. Tres observaciones que quedan registradas:

1. **S6.3 (desactivar no borra la disponibilidad)** no tiene un test separado porque `S6.1` ya
   verifica lo mismo en la misma transacción: `test_desactivar_conserva_la_fila_y_sus_reglas` afirma
   que la regla sigue visible después del `PATCH activo = false`. Separarlo sería duplicar el mismo
   assert.
2. **S7.5 tiene dos bordes propios** (`test_reglas_que_solo_se_tocan_en_el_extremo_no_solapan` y
   `test_otro_dia_no_solapa`): el solape es el caso canónico, pero "tocarse en el extremo" y "otro
   día" son exactamente los falsos positivos que un `OVERLAPS` mal escrito produce.
3. **S9.2/S9.3 se verifican dos veces**: en unit (mock de la API, con `listChairs` no invocado) y en
   e2e contra el backend real (`clinic.spec.ts`, 403 forzando el endpoint). Es intencional: el unit
   prueba la decisión de la UI y el e2e prueba que la API no confía en ella.

## Tenancy (RN-TEN-02)

- [x] El change crea tres tablas con `tenant_id NOT NULL` (`chair`, `professional`,
      `availability_rule`) con RLS `FORCE` y política `USING/WITH CHECK`.
- [x] Hay escenario cross-tenant explícito: S1.2, S2.5, S3.5, S5.4, S5.6, S6.4, S7.7, S8.1–S8.4,
      S10.3 (una especialidad propia de B no se lista ni se puede usar desde A).
- [x] El `tenant_id` sale del token/sesión; en body responde `422 invalid_request` y en query/header
      se ignora (S8.4).
- [x] `tasks.md` incluye el gate con prueba de mutación ejecutada: 6.1, 6.2, 6.3 y 6.4
      (`ALTER TABLE chair DISABLE ROW LEVEL SECURITY` → el gate ve filas de B y falla).
- [x] La única tabla sin RLS (`specialty`) se valida explícitamente (`tenant_id IS NULL OR = :tid`)
      y tiene sus escenarios propios (S5.4 y S10.1–S10.3).

## Verificación en tasks.md

| Escenario (grupo) | Tareas | Evidencia ejecutada |
|---|---|---|
| S1.1–S1.3 (sillones, lectura) | 3.1, 3.2 | `test_clinic_chairs.py` — 3 tests |
| S2.1–S2.5 (alta de sillón) | 3.1–3.4 | `test_clinic_chairs.py` — 5 tests |
| S3.1–S3.5 (PATCH y baja lógica) | 3.1–3.5 | `test_clinic_chairs.py` — 5 tests |
| S4.1–S4.3 (profesionales, lectura) | 4.1, 4.2 | `test_clinic_professionals.py` — 3 tests |
| S5.1–S5.6 (alta de profesional) | 4.1–4.5 | `test_clinic_professionals.py` — 7 tests (S5.5 con membership activa e inactiva) |
| S6.1–S6.4 (desactivación) | 4.6 | `test_clinic_professionals.py` — 3 tests (S6.1 y S6.3 comparten test; S6.4 es `test_el_profesional_de_otro_tenant_es_indistinguible`) |
| S7.1–S7.8 (disponibilidad) | 5.1–5.7 | `test_clinic_availability.py` — 11 tests, `unit/clinic/test_validation.py` — 22 |
| S8.1–S8.4 (aislamiento) | 6.1–6.4 | `test_clinic_rls.py` — 9 tests (incluye mutación), `test_clinic_migration.py` — 11 |
| S9.1–S9.3 (pantalla) | 7.1–7.5, 8.1, 8.2 | `ChairsSection` (7), `ProfessionalsSection` (5), `AvailabilitySection` (4), `ClinicPage` (4), `App` (6), `Home` (4), `clinic.spec.ts` (4 e2e) |
| S10.1–S10.3 (catálogo) | 4.7 | `test_clinic_specialties.py` — 4 tests |

Pipeline de la corrida: `ruff` limpio, `mypy app` 60 archivos, **444 passed**; `eslint` 0 errores,
`tsc -b` limpio, **67 unit**; **15 e2e** con `E2E_WEB_PORT=5180`.

## Próximo paso

1. Marcar las tasks restantes y archivar el change (`openspec archive c-05-clinic-setup`) verificando
   que `openspec/specs/clinic-setup` quede sincronizada.
2. Arrancar C-06 (`patients`) con el mismo gate antes de aplicar.
