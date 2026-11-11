# Evidencia — `spec-scenario-review` sobre `c-04-rbac-permissions` (r2)

**Fecha de ejecución**: 2026-11-10 · **Skill**: `spec-scenario-review`
**Change revisado**: `openspec/changes/c-04-rbac-permissions/`
**Ronda**: r2 (post-correcciones de los 14 huecos de r1)
**Base**: [`revision-c-04.md`](revision-c-04.md) (r1)

> Nota de método: el agente que corre la revisión es read-only; el informe se transcribe acá y las
> correcciones se aplicaron después sobre los artefactos (ver r3).

---

## Veredicto

**FALTAN ESCENARIOS**

- **12 requisitos / 59 escenarios** (`platform-rbac` 4+4+5+5 = 18; `platform-team` 3+8+7+4+6+4+4 = 36;
  `platform-auth` 5) y **49 tareas**.
- `openspec validate c-04-rbac-permissions --strict` → `Change 'c-04-rbac-permissions' is valid`.
- **Tenancy: completo, sin bloqueante.** RN-TEN-02 cubierto por R7 + S7.1–S7.4 + §9 (9.1a SQL, 9.1b HTTP
  como `odontologia_app`, 9.2 mutación). RN-CMP-04 en R3 + S3.1–S3.5 + 3.1–3.4. RN-TEN-04 en R5 +
  S5.1–S5.6 + 8.1–8.3 con `threading.Barrier`.
- Los huecos restantes son **inconsistencias entre documentos** que pueden producir un `500` (N1, N6) o
  hacer fallar los tests RED (N2, N3), no invariantes ausentes.

## Cierre de la ronda r1

| # | Hueco r1 | Estado | Dónde se cerró |
|---|----------|--------|----------------|
| 1 | ALTO — `previous_owner_role` ya existente en otra membership → viola `uq_membership_tenant_user_rol` | **CERRADO** | D7 (chequeo antes del paso 5 → `409 role_conflict` + rollback), D3, R5 + **S5.6**, tasks 8.1/8.3 |
| 2 | `409 membership_exists` sin escenario | **CERRADO** | R3 texto + **S3.6**, task 7.1 |
| 3 | PATCH con rol no asignable | **CERRADO** | **S3.7**, task 7.1 |
| 4 | S7.3 ("0 filas" sobre `membership_event") ≠ S6.3 | **CERRADO** | **S7.3** reescrito: error de permisos, nunca 0 filas silencioso |
| 5 | `403` de `billing` en `clinical_record.update` sin verificación | **CERRADO** | task 2.3 (fila explícita), **S3.3** + **S3.5**, task 3.1 |
| 6 | Duplicado activo vs. constraint no parcial | **CERRADO** | R2 texto, **S2.4** (activa), **S2.7** (inactiva → reactivar), task 6.3 |
| 7 | Contrato de `tenant_id` en body | **PARCIAL** | R7 + **S7.4** + D6 + task 9.1b unifican `422 invalid_request`; **residuo en S2.3** → ver N4 |
| 8 | App HTTP no declarada como `odontologia_app` | **CERRADO** | task **9.1b** (engine/listener del rol + chequeo `current_user`) |
| 9 | Receta de mutación RLS inválida | **CERRADO** | task **9.2** (`ALTER TABLE … DISABLE ROW LEVEL SECURITY`, nunca `DROP POLICY`) |
| 10 | Cascada de `tenant` mal descrita | **CERRADO** | **S6.2** (`ON DELETE CASCADE`) + D5 |
| 11 | 18 vs 15 recursos | **CERRADO** | R1: 18 recursos / 16 1:1 + desdoble + `membership_event` (salvedad N7) |
| 12 | `password_temporal` sin escenario | **CERRADO** | **S2.8**, task 6.3 |
| 13 | `platform-rbac` R4 sin error propio | **CERRADO** | **S4.5** (salvedad N8: mapeo a tarea) |
| 14 | Métrica 48/37 | **CERRADO** | 49 tareas; 38 con `Verificación:` + 11 RED con "falla/fallando" = 49 |

**Resultado r1: 13 CERRADOS · 1 PARCIAL (G7 → N4).**

## Cobertura por requisito

| # | Requisito | Esc. | Esperado | Error de negocio | Borde | RN citada | Estado |
|---|-----------|------|----------|------------------|-------|-----------|--------|
| P1 | `platform-rbac` R1 — Catálogo y matriz 18×9 | 4 | S1.1 | S1.3, S1.4 | S1.2, S1.4 | 03 § RBAC | OK (N7) |
| P2 | `platform-rbac` R2 — Guarda HTTP y catálogo | 4 | S2.1 | S2.2 | S2.3, S2.4 | RN-TEN-03 | OK (N4) |
| P3 | `platform-rbac` R3 — Fronteras duras clínicas | 5 | S3.2 | S3.1, S3.3, S3.5 | S3.3, S3.4 | RN-CMP-04 | OK (N5, N11) |
| P4 | `platform-rbac` R4 — Permisos en sesión | 5 | S4.1 | S4.5 | S4.2, S4.3, S4.4 | RN-TEN-05 | OK (N8) |
| T1 | `platform-team` R1 — Lectura de miembros | 3 | S1.1 | S1.2 | S1.3 | RN-TEN-02 | OK |
| T2 | `platform-team` R2 — Alta de miembro | 8 | S2.1, S2.2, S2.7 | S2.3, S2.4, S2.6, S2.8 | S2.5, S2.7 | RN-TEN-05 | OK |
| T3 | `platform-team` R3 — Cambio de rol | 7 | S3.1, S3.4 | S3.2, S3.3, S3.5, S3.6, S3.7 | S3.6, S3.7 | RN-TEN-04 | OK |
| T4 | `platform-team` R4 — Baja lógica | 4 | S4.1 | S4.2, S4.4 | S4.3 | RN-EX-03 | OK |
| T5 | `platform-team` R5 — Ownership atómico | 6 | S5.1 | S5.2, S5.4, S5.6 | S5.3, S5.5, S5.6 | RN-TEN-04 | **Parcial**: N1, N6, N10 |
| T6 | `platform-team` R6 — Auditoría append-only | 4 | S6.1 | S6.4 | S6.2, S6.3 | RN-AU-05 → **RN-CMP-03** (N9) | **Parcial**: N3, N5, N9 |
| T7 | `platform-team` R7 — Cross-tenant | 4 | S7.1 | S7.2 | S7.3, S7.4 | RN-TEN-02 | OK (N4) |
| A1 | `platform-auth` R1 — Guarda de sesión y `/auth/me` | 5 | S7.1 | S7.2, S7.4 | S7.3, S7.5 | RN-TEN-05 | OK |

**Totales**: 12 requisitos · 59 escenarios · 49 tareas · mínimo por requisito = 3 (T1).

### Escenarios críticos ↔ tarea de verificación

| Escenario | Tarea | Estado |
|-----------|-------|--------|
| S2.7 readmisión | 6.3 | ✅ |
| S2.8 `password_temporal` | 6.3 + 6.1 | ✅ |
| S3.6 `membership_exists` | 7.1 | ✅ |
| S3.7 owner/portal en PATCH | 7.1 | ✅ |
| S5.6 `role_conflict` | 8.1 + 8.3 | ✅ |
| S7.4 contrato único de body | 9.1b | ✅ |
| S3.5 `403` billing/assistant | 3.1 + 2.3 | ✅ |
| S4.5 sin memberships activas | 7.3 (no figura en la matriz) | ⚠️ N8 |
| S5.2 destino de otro tenant | 8.1 dice `409`, D7 dice `404`, catálogo sin el code | ❌ N1 |
| Target con fila `owner` inactiva | **ninguna** | ❌ N6 |

## Huecos nuevos

| # | Sev. | Tipo | Hueco | Fix |
|---|------|------|-------|-----|
| N1 | MEDIO | Catálogo ↔ spec ↔ tasks | `member_not_found` **no existe** en `RbacErrorCode`; D7 dice 404, S5.2 y task 8.1 dicen 409, S7.2 usa `membership_not_found` 404 → test imposible y `500` | `404 membership_not_found` para destino ajeno/inexistente; corregir S5.2 + 8.1 |
| N2 | MEDIO | design ↔ tasks | Task 4.1 pide enum con **4 valores**; D5 declara **5** (`member_reactivated`) | 4 → 5 en task 4.1 |
| N3 | MEDIO | design interno | D8 omite `member_reactivated` y su `detail` | Agregar fila en D8 |
| N4 | MEDIO | spec ↔ spec (residuo G7) | S2.3 dice que `tenant_id` en body "se ignora" vs R7/S7.4/D6 = `422`; precedencia 403↔422 sin fijar | Corregir S2.3 y declarar que la guarda (403) corre antes del body (422) |
| N5 | MEDIO | spec ↔ spec (nuevo en r2) | S3.5 pide "permiso faltante en el detalle de auditoría" de un `403`, contra S2.2/S6.4/D8 ("un rechazo no audita") | Quitar "detalle de auditoría"; decir "campo del log de aplicación" |
| N6 | MEDIO | Borde faltante (espejo de G1) | Si el **target** tiene otra membership `owner` **inactiva**, el paso 7 viola `uq_membership_tenant_user_rol` → `500` sin escenario | Chequeo simétrico → `409 role_conflict`, escenario S5.7, caso en 8.1 |
| N7 | BAJO | spec ↔ design | R1 dice desdoble "`team` y `membership`"; D1/1.2 dicen "`team` + `ownership`"; la cuenta literal da 19 | Reescribir el paréntesis (16 → 17 → 18) |
| N8 | BAJO | Escenario ↔ matriz | S4.5 sin tarea propia; la fila omite 7.3 | Agregar 7.3 a la fila |
| N9 | BAJO | Trazabilidad RN | Auditoría append-only atribuida a RN-AU-05 (que es lockout); es **RN-CMP-03** | Reatribuir |
| N10 | BAJO | Ambigüedad de code | S5.2 deja "`422` por payload inválido" sin `code` | Fijar `role_not_assignable` |
| N11 | BAJO | Editorial | R3 "Ningún rol … MUST tener permiso de lectura" (falta "salvo"); task 6.1 "Siete casos" enumera 6 | Corregir redacción y conteo |

## Tenancy — RN-TEN-02

- [x] Toca `membership` (RLS `FORCE`, `uq_membership_tenant_user_rol` no parcial + `uq_membership_owner_activo`) y `membership_event` (nueva, RLS `ENABLE`+`FORCE`, `GRANT INSERT` solo). `user` es global y se declara.
- [x] Escenario cross-tenant: S7.1–S7.4, más S2.5, S3.3, S3.5, S5.2.
- [x] `tenant_id` sale del token/sesión (R2, R7, S2.3, S7.4, D3, D6). Salvedad N4.
- [x] Gate de merge: §9 completa — 9.1a (SQL), 9.1b (HTTP como `odontologia_app` con chequeo de `current_user`), 9.2 (mutación con `DISABLE ROW LEVEL SECURITY`).
- **`cross-tenant leak = 0`** como criterio de salida de 9.2.

## Próximo paso

1. Cerrar N1, N4, N6 (pueden producir `500`) y N2/N3/N5 (rompen los tests RED).
2. Cerrar N7–N11 (editorial y trazabilidad).
3. Re-validar y correr r3; sin tocar tenancy, el change pasa a **LISTO PARA APLICAR**.
