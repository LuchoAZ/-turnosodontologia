# Evidencia — `spec-scenario-review` sobre `c-04-rbac-permissions` (r1)

**Fecha de ejecución**: 2026-11-10 · **Skill**: `spec-scenario-review`
**Change revisado**: `openspec/changes/c-04-rbac-permissions/`
**Alcance**: especificación previa a `/opsx:apply` (proposal, design, 3 delta specs, tasks).

> Nota de método: el agente que corrió la revisión es read-only; el informe se transcribe acá y las
> correcciones se aplicaron después sobre los artefactos (ver r2).

---

## Veredicto

**FALTAN ESCENARIOS**

12 requisitos / **51 escenarios** (4+4+4+4 en `platform-rbac`, 3+6+5+4+5+4+3 en `platform-team`,
5 en `platform-auth`) / 48 tareas. Ningún requisito baja de 3 escenarios y los 51 están mapeados en
la tabla escenario→tarea (`tasks.md`). Los tres gates duros están presentes: RN-TEN-02
(`platform-team` R7 + §9), RN-CMP-04 (`platform-rbac` R3 + 3.1–3.4) y RN-TEN-04 con concurrencia
(S5.3 + tarea 8.3). Los huecos son de cobertura puntual y de **inconsistencia entre documentos**,
no de invariante ausente.

`openspec validate c-04-rbac-permissions --strict` → `Change 'c-04-rbac-permissions' is valid`.

---

## Cobertura por requisito

| # | Requisito | Esc. | Esperado | Error de negocio | Borde | RN citada | Estado |
|---|-----------|------|----------|------------------|-------|-----------|--------|
| P1 | `platform-rbac` Catálogo y matriz | 4 | S1.1 | S1.3, S1.4 | S1.2 | — | OK (conteo "15 recursos" mal, G11) |
| P2 | `platform-rbac` Guarda HTTP y catálogo | 4 | S2.1 | S2.2 | S2.3 | RN-TEN-03 | OK |
| P3 | `platform-rbac` Fronteras duras | 4 | S3.2 | S3.1, S3.3 | S3.3, S3.4 | RN-CMP-04 | Falta verificación del `403` de `billing` en `clinical_record.update` (G5) |
| P4 | `platform-rbac` Permisos en sesión | 4 | S4.1 | delegado a `platform-auth` S7.3/S7.5 | S4.2, S4.3, S4.4 | RN-TEN-05 | OK con nota (G13) |
| T1 | `platform-team` Lectura | 3 | S1.1 | S1.2 | S1.3 | RN-TEN-02 | OK |
| T2 | `platform-team` Alta | 6 | S2.1, S2.2 | S2.3, S2.4, S2.6 | S2.5 | — | Faltan borde de membership inactiva (G6) y `password_temporal` (G12) |
| T3 | `platform-team` Cambio de rol | 5 | S3.1 | S3.2, S3.3, S3.5 | S3.4 | RN-TEN-04 | Faltan `membership_exists` (G2) y `owner`/`role_not_assignable` (G3) |
| T4 | `platform-team` Baja lógica | 4 | S4.1 | S4.2, S4.4 | S4.3 | RN-EX-03 | OK |
| T5 | `platform-team` Ownership | 5 | S5.1 | S5.2, S5.4 | S5.3, S5.5 | RN-TEN-04 | OK; falta choque de rol del actor (G1) |
| T6 | `platform-team` Auditoría | 4 | S6.1 | S6.2, S6.3, S6.4 | S6.2 | RN-AU-05 | Cascada de `tenant` mal descrita (G10) |
| T7 | `platform-team` Cross-tenant | 3 | S7.1 | S7.2 | S7.3 | RN-TEN-02 | S7.3 contradice S6.3 (G4) |
| A1 | `platform-auth` Guarda de sesión y `/auth/me` | 5 | S7.1 | S7.2, S7.4 | S7.3, S7.5 | RN-TEN-05 | OK |

---

## Huecos detectados

1. **ALTO — `platform-team` R5 / design D7**: la transferencia asigna al actor
   `previous_owner_role` sin verificar que **ya tenga otra membership con ese rol**. Con un usuario
   multi-membership (caso que S1.2 y RN-TEN-05 declaran normal) el `UPDATE` viola
   `uq_membership_tenant_user_rol` (`backend/app/models/tenancy.py:133-138`, no parcial) y sale un
   error de integridad, no un `409` del catálogo. Sugerencia: S5.6 → `409 role_conflict`, con
   `rollback`, actor sigue `owner` y `count(owner activo) = 1`.
2. **MEDIO — `platform-team` R3**: el MUST "la misma combinación usuario+rol ya existente →
   `409 membership_exists`" no tiene escenario ni tarea; y S3.4 define el mismo rol en la **misma**
   membership como `200` idempotente.
3. **MEDIO — `platform-team` R3**: falta escenario de `rol` no asignable en `PATCH`
   (`owner` → `409 owner_must_be_transferred`; `patient`/`external_lab` → `422 role_not_assignable`),
   que es lo que impide crear un segundo owner por esa vía (RN-TEN-04).
4. **MEDIO — Contradicción S7.3 vs S6.3**: S7.3 dice que `SELECT` sobre `membership_event` devuelve
   0 filas; S6.3, tarea 4.3 y el grant de design D5 (solo `INSERT`) dicen error de permisos.
5. **MEDIO — `platform-rbac` S3.3**: exige `403` de `billing` en una operación que exige
   `clinical_record.update`, pero ninguna tarea lo verifica.
6. **MEDIO — `platform-team` S2.4**: el duplicado se describe como membership **activa**, pero
   `uq_membership_tenant_user_rol` incluye las inactivas: readmitir a alguien dado de baja con el
   mismo rol también viola el constraint.
7. **MEDIO — `tenant_id` ajeno en body: cuatro comportamientos distintos**: se ignora, se rechaza
   por DTO 422, se ignora y opera igual, o da 404. El test de tenancy no puede asertar los cuatro.
8. **MEDIO — Tenancy, nivel endpoint**: 9.1 no declara que **la app HTTP** corra con el engine
   conectado como `odontologia_app`; con el superusuario, el 404 de S7.2 puede venir de un filtro de
   aplicación y no probar RLS.
9. **MEDIO — Tenancy, receta de mutación**: "desactivar la política (o el filtro de tenant)" no es
   una mutación válida de RLS. Receta válida: `ALTER TABLE … DISABLE ROW LEVEL SECURITY` o
   superusuario vs. `SET ROLE odontologia_app`, nunca `DROP POLICY`.
10. **BAJO — `platform-team` S6.2**: dice que borrar un `tenant` referenciado deja la referencia en
    `NULL`, pero la FK es `ON DELETE CASCADE` → el evento se borra; solo `user` es `SET NULL`.
11. **BAJO — `platform-rbac` R1**: "18 recursos" y a la vez "Los **15** recursos se toman 1:1"; la
    tabla de `03_actores_y_roles.md:33-48` tiene **16** filas (16 + desdoble + `membership_event` = 18).
12. **BAJO — `platform-team` R2**: `password_temporal` (mín. 12) solo vive en la requirement y en
    la tarea 6.3, sin escenario.
13. **BAJO — `platform-rbac` R4**: sin escenario propio de error (usuario sin memberships activas →
    `401` y sin permisos viejos).
14. **BAJO — Métrica**: 48 tareas, 37 con el literal `Verificación:`; las 11 RED usan "Verificar que
    falla".

### Desviaciones declaradas (no son huecos)

- US-005 "invitación con expiración de 7 días" y aceptación por email → diferidas por PQ-08.
- US-005 "rechaza `owner` a quien ya es owner de otro tenant (configurable)" → se sustituye por
  rechazo incondicional de `owner` en el alta.
- Restricción horizontal 3 (`billing.can_read_clinical`) → fija en `false`, deuda de C-09.

---

## Tenancy (RN-TEN-02)

- [x] El change toca `membership` (RLS `FORCE` de C-02) y `membership_event` (nueva, `tenant_id
      NOT NULL` + RLS `FORCE`). `user` es global y se declara como tal.
- [x] Escenario cross-tenant: S7.1–S7.3, más S2.5, S3.3 y S5.2.
- [x] El `tenant_id` sale del token/sesión. Caveat: contrato para `tenant_id` en body no único (G7).
- [x] `tasks.md` incluye el test de aislamiento como gate de merge (§9). Caveats: rol de la app HTTP
      no declarado (G8) y receta de mutación ambigua (G9).
- **`cross-tenant leak = 0`** como criterio de salida de 9.2.

---

## Próximo paso

Cerrar los huecos 1–3 (pueden producir un `500` o una vía no prevista hacia segundo owner),
unificar el contrato de `tenant_id` en body (G7) y endurecer 9.1/9.2; luego re-ejecutar el gate.
