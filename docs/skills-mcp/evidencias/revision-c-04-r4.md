# Evidencia — `spec-scenario-review` sobre `c-04-rbac-permissions` (r4, confirmación)

**Fecha**: 2026-11-10 · **Skill**: `spec-scenario-review` · **Change**: `c-04-rbac-permissions`
**Ronda**: r4 (confirmación puntual de N12/N13 + editoriales E1–E8)

## Veredicto

**`LISTO PARA APLICAR`**

## Verificación

| # | Punto | Estado | Evidencia |
|---|-------|--------|-----------|
| 1 | `appointment.create_own` + 9 `_own` (8 paciente + `settlement.read_own`) | OK | `design.md:82`, `design.md:103-108`, `tasks.md:16-18` |
| 2 | S4.4 distingue `_own` del paciente de `settlement.read_own` | OK | `specs/platform-rbac/spec.md:203-211` |
| 3 | S3.4 acotado a "rol asignable", sin colisión con S3.7 | OK | `specs/platform-team/spec.md:149-153` / `:168-174` |
| 4 | Matriz S5.1–S5.7 + S5.2b y suma de 61 escenarios | OK | `tasks.md:288`, `:279-290` |
| 5 | Task 5.1 asserta ausencia de `permissions` | OK | `tasks.md:112-116`, `design.md:291-294` |
| 6 | `previous_owner_role: str \| None` + validación en servicio | OK | `tasks.md:189-192` |
| 7 | `RequestValidationError` → `422 invalid_request` | OK | `tasks.md:42-47` |
| 8 | Aritmética 18 = 16 − 1 + 2 + 1 y rango 33-48 | OK | `design.md:93-94`, `design.md:69`, `tasks.md:16` |
| 9 | Título de S2.3 cubre el contrato de `tenant_id` | OK | `specs/platform-rbac/spec.md:96-105` |
| 10 | Sin escenario huérfano; sin `member_not_found`/`RN-AU-05`; 13 `code` en D3 | OK | grep = 0, `design.md:161-167` |

Sin fallas. **Gate superado: el change puede aplicarse.**
