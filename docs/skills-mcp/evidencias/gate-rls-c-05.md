# Gate de aislamiento cross-tenant — C-05 (tasks 6.1–6.4)

> Evidencia del gate **bloqueante de merge** de C-05 (RN-TEN-02). Ejecutado el
> **2026-11-11** con Docker + Postgres 16 real (Testcontainers).
> Comando: `uv run pytest tests/integration/test_clinic_rls.py -q -s`.

## Resultado

```
13 passed
[6.4] RLS ON  -> la app ve 1 sillon(es) de A, 0 de B
[6.4] RLS OFF -> la app ve 2 sillon(es): el ajeno se filtra (6.1a ROJO)
[6.4] RLS ON  -> gate VERDE otra vez: cross-tenant leak = 0
```

## Qué congela

| Nivel | Test | Escenario | Qué prueba |
|---|---|---|---|
| SQL | `test_a_nunca_ve_las_filas_de_b[chair/professional/availability_rule]` | S8.1 | Con `SET ROLE odontologia_app` y `app.current_tenant = A`, `SELECT` devuelve solo las filas de A. `current_user = odontologia_app`. |
| SQL | `test_update_y_delete_con_id_de_b_afectan_cero_filas` | S8.2 | `UPDATE`/`DELETE` del id de B afecta **0 filas**; la fila de B queda intacta (verificado con el superusuario). |
| SQL | `test_sin_contexto_rls_es_fail_closed[*]` | S8.3 | Sin GUC, las tres tablas devuelven 0 filas y un `INSERT` es rechazado por RLS (`row-level security`). |
| SQL | `test_con_contexto_de_a_no_se_puede_insertar_en_b` | S8.3 | El `WITH CHECK` impide insertar una fila con `tenant_id` de B desde A. |
| HTTP | `test_http_no_devuelve_datos_de_b` | S8.1 | `GET /chairs`, `/professionals`, `/availability` con sesión de A no traen nada de B. |
| HTTP | `test_http_patch_y_delete_con_id_de_b_responden_404` | S8.2 | Un id ajeno responde **el mismo** `404` y `code` que un UUID inventado (`chair_not_found`, `professional_not_found`, `availability_not_found`). |
| HTTP | `test_tenant_id_en_el_body_es_422_invalid_request` | S8.4 | `tenant_id` en el body → `422 invalid_request` con mensaje genérico (sin `detail`), sin escribir fila. |
| HTTP | `test_tenant_id_en_query_o_header_se_ignora` | S8.4 | `?tenant_id=` y `X-Tenant-Id` con otro tenant se ignoran: la operación sigue con el de la sesión. |
| Mutación | `test_mutar_rls_desactivada_rompe_el_gate_y_restaurarla_lo_deja_verde` | 6.4 | `ALTER TABLE chair DISABLE ROW LEVEL SECURITY` → la app ve las filas de B (gate ROJO); restaurar `ENABLE` + `FORCE` → verde otra vez. |

## Notas de implementación

- La política de las tres tablas ya estaba en `005_clinic_setup.py` (task 1.4), así
  que `6.2` fue verificación, no corrección: el mismo archivo de test cubre
  `ENABLE` + `FORCE` + `WITH CHECK` a nivel de catálogo en
  `test_clinic_migration.py::test_rls_habilitada_y_forzada_con_politica_por_tenant`.
- La mutación corre con el engine **superusuario** (`db_engine`): el engine de la
  app se conecta como `odontologia_app` y no es dueño de la tabla (`must be owner
  of table chair`), lo que confirma de paso que el rol de app no puede alterar la
  política.
- Nunca se hace `DROP POLICY`: se muta el flag y se restaura en `finally`
  (`ENABLE` + `FORCE`), de modo que un fallo a mitad de test no deja la suite
  mintiendo.
- `cross-tenant leak = 0` es el criterio de aceptación de la regla dura del
  proyecto. Si este archivo se pone rojo, C-05 no se puede archivar.
