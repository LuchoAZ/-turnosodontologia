# Evidencia — `spec-scenario-review` sobre `c-04-rbac-permissions` (r3)

**Fecha de ejecución**: 2026-11-10 · **Skill**: `spec-scenario-review`
**Change revisado**: `openspec/changes/c-04-rbac-permissions/`
**Ronda**: r3 (verificación tras corregir los 11 huecos de r2)
**Base**: [`revision-c-04-r2.md`](revision-c-04-r2.md)

> Nota de método: revisión read-only; la skill no pudo cargarse por la tool (permiso denegado) y se
> aplicó el mismo procedimiento del gate de forma manual sobre los 6 artefactos + KB 03.

---

## Veredicto

**FALTAN ESCENARIOS**

- **12 requisitos / 61 escenarios / 49 tareas** (`platform-rbac` 4+4+5+5 = 18; `platform-team`
  3+8+7+4+8+4+4 = 38; `platform-auth` 5). Mínimo por requisito = 3.
- **Los 11 huecos de r2 (N1–N11) están cerrados.**
- **Tenancy: completo, sin bloqueante.** RN-TEN-02 por T7 + S7.1–S7.4 + §9 (9.1a SQL, 9.1b HTTP como
  `odontologia_app` con chequeo de `current_user`, 9.2 mutación). RN-CMP-04 en P3. RN-TEN-04 en T5
  con `threading.Barrier`. RN-CMP-03 en T6.
- `odontologia_app` tiene `SELECT/INSERT/UPDATE/DELETE` sobre `tenant`
  (`backend/alembic/versions/002_core_tenancy.py:352`), así que el `SELECT … FOR UPDATE` de D7 no
  falla por privilegio.
- Los dos huérfanos son **de fidelidad de matriz (N12, N13)**: pueden hacer fallar el test RED 9×18 y
  el escenario S4.4.

## Cierre de la ronda r2 (N1–N11)

| # | Hueco r2 | Estado | Dónde se cerró |
|---|----------|--------|----------------|
| N1 | Destino ajeno/inexistente: `404 membership_not_found`, sin `member_not_found` | **CERRADO** | D3 (catálogo), D7 p.4, S5.2b, task 8.1 |
| N2 | Enum de `membership_event_tipo` con 5 valores | **CERRADO** | task 4.1 |
| N3 | D8 con `member_reactivated` | **CERRADO** | D8 (+ D6 paso 5) |
| N4 | Body → `422`; query/header se ignora; guarda 403 antes del body | **CERRADO** | `platform-rbac` S2.3 + task 9.1b |
| N5 | S3.5 sin "detalle de auditoría" | **CERRADO** | `platform-rbac` S3.5 (solo log de aplicación) |
| N6 | Target con otra fila `owner` inactiva → `409 role_conflict` | **CERRADO** | S5.7 + D7 (chequeo simétrico) + task 8.1/8.2 |
| N7 | 18 recursos: 16 → desdoble → 17 → `membership_event` = 18 | **CERRADO** | `platform-rbac` R1 |
| N8 | Matriz S4.1–S4.5 incluye 7.3 | **CERRADO** | matriz de tasks |
| N9 | RN-CMP-03 en lugar de RN-AU-05 | **CERRADO** | grep `RN-AU-05` = 0 |
| N10 | `422 role_not_assignable` para `previous_owner_role` | **CERRADO** | S5.2 + D7 paso 1 |
| N11 | R3 "Salvo los clínicos…"; task 6.1 "Ocho casos" | **CERRADO** | R3 + task 6.1 |

**Resultado r2: 11/11 CERRADOS.**

## Contradicciones residuales

### N12 — MEDIO — falta `appointment.create_own` (corregido después)

- KB `03_actores_y_roles.md:40`: paciente en Turnos = `C R (propios)` → dos acciones.
- R1 exige traducir cada celda a la misma cantidad de acciones con sufijo `_own`, y la regla de
  derivación mapea `C (propia)` → `create_own`.
- D1 declaraba solo `appointment.read_own` → el test de fidelidad de task 1.1 fallaba.

### N13 — MEDIO — S4.4 decía que todo `_own` es del paciente (corregido después)

- D1 declara `settlement.read_own` para `professional` (KB `03_actores_y_roles.md:43`, "R (propias)").
- S4.4 afirmaba que "los `_own` … solo aparecen para `patient`" → test imposible de cumplir.

### Editoriales (aplicadas)

| # | Observación | Fix |
|---|-------------|-----|
| E1 | S3.4 (idempotente) vs S3.7 (`owner` → 409) | S3.4 acotado a "rol **asignable**" |
| E2 | Matriz rotulaba `S5.1–S5.7 | 8` sin nombrar S5.2b | Rótulo `S5.1–S5.7 + S5.2b` |
| E3 | 5.1 no assertaba ausencia de `permissions` | Agregado al test |
| E4 | `previous_owner_role` requerido rompe el `code` estable | `str \| None` + validación en servicio (task 8.2) |
| E5 | `invalid_request` exige handler de `RequestValidationError` | Task 2.2 |
| E6 | Aritmética 16+1+1 y rango de la KB inconsistente | D1 y tasks a líneas 33-48 |
| E7 | Título de S2.3 no cubría el contrato de `tenant_id` | Renombrado |
| E8 | S4.4 enumeraba 3 `_own` como si fueran todos | Lista completa (9) |

## Cobertura por requisito

| # | Requisito | Esc. | Esperado | Error de negocio | Borde | RN | Estado |
|---|-----------|------|----------|------------------|-------|----|--------|
| P1 | `platform-rbac` R1 — Catálogo y matriz | 4 | S1.1 | S1.3, S1.4 | S1.2, S1.4 | 03 § RBAC | OK tras N12 |
| P2 | `platform-rbac` R2 — Guarda y catálogo | 4 | S2.1 | S2.2 | S2.3, S2.4 | RN-TEN-03 | OK |
| P3 | `platform-rbac` R3 — Fronteras duras | 5 | S3.2 | S3.1, S3.3, S3.5 | S3.3, S3.4 | RN-CMP-04 | OK |
| P4 | `platform-rbac` R4 — Permisos en sesión | 5 | S4.1 | S4.5 | S4.2–S4.4 | RN-TEN-05 | OK tras N13 |
| T1 | `platform-team` R1 — Lectura | 3 | S1.1 | S1.2 | S1.3 | RN-TEN-02 | OK |
| T2 | `platform-team` R2 — Alta | 8 | S2.1, S2.2, S2.7 | S2.3, S2.4, S2.6, S2.8 | S2.5, S2.7 | RN-TEN-05 | OK |
| T3 | `platform-team` R3 — Cambio de rol | 7 | S3.1, S3.4 | S3.2, S3.3, S3.5, S3.6, S3.7 | S3.6, S3.7 | RN-TEN-04 | OK |
| T4 | `platform-team` R4 — Baja | 4 | S4.1 | S4.2, S4.4 | S4.3 | RN-EX-03 | OK |
| T5 | `platform-team` R5 — Ownership | 8 | S5.1, S5.2b | S5.2, S5.2b, S5.4, S5.6, S5.7 | S5.3, S5.5, S5.6, S5.7 | RN-TEN-04 | OK |
| T6 | `platform-team` R6 — Auditoría | 4 | S6.1 | S6.4 | S6.2, S6.3 | RN-CMP-03 | OK |
| T7 | `platform-team` R7 — Cross-tenant | 4 | S7.1 | S7.2 | S7.3, S7.4 | RN-TEN-02 | OK |
| A1 | `platform-auth` R1 — Sesión y `/auth/me` | 5 | S7.1 | S7.2, S7.4 | S7.3, S7.5 | RN-TEN-05 | OK |

**Chequeo de conteos**: `18 + 38 + 5 = 61`; la matriz de `tasks.md` suma 61; las 49 tareas cuadran
§1 4 + §2 7 + §3 4 + §4 4 + §5 4 + §6 4 + §7 5 + §8 5 + §9 3 + §10 4 + §11 3 + §12 2 = 49.

### Escenarios nuevos ↔ tarea

| Escenario | Tarea | Estado |
|-----------|-------|--------|
| S5.2b (destino inexistente = ajeno → 404) | 8.1 | ✅ |
| S5.7 (target con otra `owner` inactiva → 409) | 8.1 + 8.2 | ✅ |
| S2.3 (body→422, query/header ignorado, 403 antes del body) | 2.3 + 9.1b | ✅ |
| S4.5 (sin memberships activas) | 7.3 | ✅ |

## Tenancy — RN-TEN-02

- [x] Toca `membership` (RLS `FORCE`) y `membership_event` (nueva, `tenant_id NOT NULL`, RLS
  `ENABLE` + `FORCE`, `GRANT INSERT` solo, trigger `55000`).
- [x] Escenarios cross-tenant: S2.5, S3.3, S5.2b, S7.1–S7.4.
- [x] `tenant_id` del token/sesión; body → `422`; query/header ignorados.
- [x] Gate de merge §9 completa (9.1a, 9.1b, 9.2).
- **`cross-tenant leak = 0`** como criterio de salida.

## Próximo paso

Cerrar N12 (`appointment.create_own`) y N13 (`settlement.read_own` en S4.4) + E1–E8, re-validar y
confirmar con una ronda corta. Sin bloqueante de tenancy.
