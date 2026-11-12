# Gate de aislamiento cross-tenant — C-06 (tasks 2.5, 4.8 y 4.9)

> Evidencia del gate **bloqueante de merge** de C-06 (RN-TEN-02). Ejecutado el
> **2026-11-12** con Docker + Postgres 16 real (Testcontainers), con las tablas
> `patient` y `patient_counter` ya migradas (`006_patients`) y la API montada.
> Comandos:
>
> ```
> uv run pytest tests/integration/test_patients_rls.py -q -s
> uv run pytest tests/integration/test_patients_http.py -q
> ```

## Resultado

```
9 passed
[4.9] patient RLS ON  -> la app ve solo el tenant A
[4.9] patient RLS OFF -> la app ve 2 tenants: el ajeno se filtra
[4.9] patient RLS ON  -> gate VERDE otra vez: cross-tenant leak = 0
[4.9] patient_counter RLS ON  -> la app ve solo el tenant A
[4.9] patient_counter RLS OFF -> la app ve 2 tenants: el ajeno se filtra
[4.9] patient_counter RLS ON  -> gate VERDE otra vez: cross-tenant leak = 0
```

```
72 passed
```

## Qué congela

### Nivel SQL (`test_patients_rls.py`, task 2.5)

| Test | Escenario | Qué prueba |
|---|---|---|
| `test_a_nunca_ve_los_pacientes_de_b` | S1.5 | Con `SET ROLE odontologia_app` y `app.current_tenant = A`, `SELECT` devuelve solo el paciente de A (`current_user = odontologia_app`). |
| `test_cada_tenant_ve_solo_su_contador` | S4.2 | El contador también es tabla de negocio: A ve una fila, la suya, y su `ultimo_numero` real. |
| `test_update_y_delete_con_id_de_b_afectan_cero_filas` | S8.4 | `UPDATE`/`DELETE` del id de B afecta **0 filas**; la fila de B queda intacta (verificado con el superusuario). |
| `test_sin_contexto_rls_es_fail_closed[patient/patient_counter]` | — | Sin GUC, ambas tablas devuelven 0 filas: fail-closed, nunca "todas". |
| `test_insert_de_paciente_sin_contexto_lo_frena_el_with_check` | — | Un `INSERT` sin GUC es rechazado por RLS (`row-level security`). |
| `test_con_contexto_de_a_no_se_puede_insertar_un_paciente_en_b` | S5.3 | El `WITH CHECK` impide insertar una fila con `tenant_id` de B desde A; B queda con una sola fila. |

### Nivel HTTP (`test_patients_http.py`, task 4.8)

Un test por cruce y por mutación "crear en B, leer desde A":

| Test | Escenario | Qué prueba |
|---|---|---|
| `test_s1_5_un_paciente_de_otro_tenant_nunca_aparece` | S1.5 | A y B con el **mismo DNI y el mismo nombre**: la lista y el `total` de A solo cuentan el suyo y el `id` de B no aparece en la respuesta. |
| `test_s2_4_la_busqueda_no_cruza_tenants` | S2.4 | B tiene `Pérez, Ana` y A busca `?q=perez` → `total = 0`, sin el `id` ajeno. |
| `test_s5_3_el_mismo_dni_en_otro_tenant_es_valido` | S5.3 | El mismo DNI en B responde `201` y arranca su propia secuencia (`000001`). |
| `test_s6_5_un_homonimo_de_otro_tenant_no_pide_confirmacion` | S6.5 | El dedupe blando no cruza tenants: el alta de A responde `201`, no `409`. |
| `test_s7_2_un_id_ajeno_es_indistinguible_de_uno_inexistente` | S7.2 | `GET /{id}` de B y un UUID inventado devuelven **el mismo cuerpo** `404 patient_not_found`. |
| `test_s8_4_un_id_ajeno_responde_404_indistinguible` | S8.4 | `PATCH /{id}` de B y un UUID inventado devuelven el mismo `404`; la fila de B conserva su `nombre`. |
| `test_s1_2_sin_patient_read_la_lista_no_existe_para_el_backend` | S1.2 | `accountant` sin `patient.read` → `403 forbidden`, sin nombres, DNI ni identificadores en el cuerpo. |
| `test_s3_3_los_campos_reservados_del_cuerpo_se_rechazan` | S3.3 | `tenant_id` en el body → `422 invalid_request`, sin fila. |

### Prueba de mutación (task 4.9)

`test_mutar_rls_desactivada_rompe_el_gate_y_restaurarla_lo_deja_verde[patient]`
y `[patient_counter]`:

1. Con RLS activa, la app ve **solo** el tenant A.
2. `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` (superusuario) → la app ve los
   **dos** tenants: el ajeno se filtra, el gate se pone rojo.
3. `ENABLE` + `FORCE` en el `finally` → vuelve a ver solo A: **cross-tenant leak = 0**.

## Notas de implementación

- La mutación corre con el engine **superusuario** (`db_engine`): el engine de la
  app se conecta como `odontologia_app` y no es dueño de las tablas, lo que
  confirma de paso que el rol de app no puede alterar la política.
- Nunca se hace `DROP POLICY`: se muta el flag y se restaura en `finally`
  (`ENABLE` + `FORCE`), de modo que un fallo a mitad de test no deja la suite
  mintiendo.
- `patient_counter` se prueba igual que `patient` porque también tiene
  `tenant_id NOT NULL`: sin RLS, la clínica A podría leer o pisar el contador de B
  y la secuencia de historia clínica dejaría de ser confiable.
- El `tenant_id` nunca viaja en body ni en query: sale del token y RLS lo vuelve
  a exigir en el `WITH CHECK`. El `422` por `tenant_id` en el body lo produce
  `extra="forbid"` antes de llegar al servicio.
- `cross-tenant leak = 0` es el criterio de aceptación de la regla dura del
  proyecto. Si este archivo se pone rojo, C-06 no se puede archivar.
