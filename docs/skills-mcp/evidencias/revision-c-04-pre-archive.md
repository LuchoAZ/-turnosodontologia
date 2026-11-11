# Revisión de escenarios — c-04-rbac-permissions (pre-archive)

> Gate de la skill `spec-scenario-review` ejecutado el **2026-11-11** sobre el change ya implementado,
> como paso previo al archivado. No revisa "si la spec está linda": verifica que cada escenario tenga
> hoy una prueba ejecutable que lo respalde. Datos de la corrida completa en `docs/rbac.md` § 10.

## Veredicto

**LISTO PARA APLICAR** (a archivar). 12 requisitos / 61 escenarios, todos con ≥3 escenarios, con las
tres clases cubiertas y con una tarea de verificación ejecutada. Gate de tenancy completo.

## Cobertura por requisito

| Spec | Requisito | Escenarios | Esperado | Error de negocio | Borde | RN citada | Estado |
|---|---|---:|---|---|---|---|---|
| `platform-auth` | Guarda de sesión y contrato de `GET /auth/me` | S7.1–S7.5 | ✅ S7.1 | ✅ S7.2, S7.3, S7.4 | ✅ S7.5 | RN-TEN-03, RN-AU-04 | OK |
| `platform-rbac` | Catálogo y matriz rol→permiso | S1.1–S1.4 | ✅ S1.1 | ✅ S1.3, S1.4 | ✅ S1.2 | RN-TEN-04 | OK |
| `platform-rbac` | Guarda HTTP y catálogo de errores | S2.1–S2.4 | ✅ S2.1 | ✅ S2.2 | ✅ S2.3, S2.4 | RN-TEN-02, RN-TEN-03 | OK |
| `platform-rbac` | Fronteras duras clínicas | S3.1–S3.5 | ✅ S3.2 | ✅ S3.1, S3.3, S3.5 | ✅ S3.4 | RN-CMP-04 | OK |
| `platform-rbac` | Permisos efectivos en la sesión | S4.1–S4.5 | ✅ S4.1 | ✅ S4.5 | ✅ S4.2, S4.3, S4.4 | RN-TEN-02 | OK |
| `platform-team` | Lectura de miembros | S1.1–S1.3 | ✅ S1.1 | ✅ S1.2 | ✅ S1.3 | RN-TEN-04 | OK |
| `platform-team` | Alta de miembro (sin email) | S2.1–S2.8 | ✅ S2.1, S2.2 | ✅ S2.3–S2.6 | ✅ S2.7, S2.8 | RN-TEN-04, PQ-08 | OK |
| `platform-team` | Cambio de rol | S3.1–S3.7 | ✅ S3.1 | ✅ S3.2, S3.3, S3.5–S3.7 | ✅ S3.4 | RN-TEN-04 | OK |
| `platform-team` | Baja lógica | S4.1–S4.4 | ✅ S4.1 | ✅ S4.2, S4.4 | ✅ S4.3 | RN-EX-03 | OK |
| `platform-team` | Transferencia de ownership | S5.1–S5.7 + S5.2b | ✅ S5.1 | ✅ S5.2, S5.2b, S5.4 | ✅ S5.3, S5.5–S5.7 | RN-TEN-04 | OK |
| `platform-team` | Auditoría append-only | S6.1–S6.4 | ✅ S6.1 | ✅ S6.2, S6.3 | ✅ S6.4 | RN-CMP-03 | OK |
| `platform-team` | Aislamiento cross-tenant | S7.1–S7.4 | ✅ S7.1 | ✅ S7.2, S7.4 | ✅ S7.3 | RN-TEN-02 | OK |

## Huecos detectados

Ninguno bloqueante. Dos observaciones que quedan registradas:

1. **S4.5 (sin memberships activas)** se verifica por el mismo camino que
   `test_membership_desactivada_despues_del_login_invalida_y_revoca`: al no resolverse membership
   activa del tenant de la sesión, `/auth/me` responde `401` y revoca; no hay permisos residuales
   porque `SessionOut` se arma desde `resolve_permissions` de las memberships **activas**. No se agrega
   un test artificial de "cero permisos" que sólo probaría el mismo predicado.
2. **S5.2 y S5.2b** comparten título y se distinguen por la numeración (`b`): el destino *inexistente*
   y el destino *de otro tenant* deben ser indistinguibles. Se mantiene porque el escenario doble es
   el que congela la indistinguibilidad; está cubierto por
   `test_un_destino_inexistente_y_uno_de_otro_tenant_son_indistinguibles`.

## Tenancy (RN-TEN-02)

- [x] El change toca tablas con `tenant_id` (`membership`, `membership_event`).
- [x] Hay escenario cross-tenant explícito: S2.5, S3.3, S7.1–S7.4.
- [x] `tenant_id` sale del token/sesión; en body responde `422 invalid_request`, en query/header se
      ignora (S2.3, S7.4).
- [x] `tasks.md` incluye el test de aislamiento: 9.1a, 9.1b, 9.2 (gate con prueba de mutación).

## Verificación en tasks.md

| Escenario (grupo) | Tareas | Evidencia ejecutada |
|---|---|---|
| S1.1–S1.4 (matriz) | 1.1–1.4 | `tests/unit/rbac/test_matrix.py` — 10 tests |
| S2.1–S2.4 (guard/errores) | 2.1–2.6, 10.4 | `tests/unit/rbac/test_errors.py` (6), `test_guard.py` (5), `frontend/src/features/auth/rolesSweep.test.ts` (2) |
| S3.1–S3.5 (fronteras) | 3.1–3.4 | `tests/integration/test_rbac_clinical_boundary.py` — 10 tests |
| S4.1–S4.5 (sesión) | 2.5, 2.6, 7.3, 10.2 | `tests/integration/test_auth_me.py` (11), `test_auth_switch_tenant.py` (6) |
| `platform-auth` S7.1–S7.5 | 2.5, 2.6, 2.7 | `test_auth_me.py` (S7.1–S7.4), `test_team_rls.py` (S7.5 vía contrato de tenant) |
| Team S1.1–S1.3 | 5.1–5.4 | `test_team_members_read.py` — 6 tests |
| Team S2.1–S2.8 | 6.1–6.4 | `test_team_members_create.py` — 11 tests |
| Team S3.1–S3.7 | 7.1, 7.2, 7.5 | `test_team_members_update.py` — 7 tests |
| Team S4.1–S4.4 | 7.3–7.5 | `test_team_members_deactivate.py` — 5 tests |
| Team S5.1–S5.7 | 8.1–8.5 | `test_team_ownership_transfer.py` — 11 tests (incluye `Barrier` y lock con `TimeoutError`) |
| Team S6.1–S6.4 | 4.1–4.4, 6.1, 7.1 | `test_membership_event_migration.py` — 15 tests |
| Team S7.1–S7.4 | 9.1a, 9.1b, 9.2 | `test_team_rls.py` — 11 tests (nivel SQL, HTTP y mutación) |
| Criterio 3 del TPI | 10.1–10.4, 11.2, 11.3 | `permissions.test.tsx` (7), `TeamPage.test.tsx` (8), `Home.test.tsx` (2), `team.spec.ts` (5) |

Pipeline de la corrida: `ruff` limpio, `mypy app` 52 archivos, **334 passed**; `eslint` 0 errores,
`tsc -b` limpio, **43 unit**; **11 e2e** con `E2E_WEB_PORT=5180`.

## Próximo paso

1. Archivar el change (`openspec archive c-04-rbac-permissions`) y verificar que aparezcan
   `openspec/specs/platform-rbac` y `openspec/specs/platform-team` sincronizadas.
2. Arrancar C-05 con el mismo gate antes de aplicar.
