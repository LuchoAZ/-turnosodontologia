# Revisión de escenarios — c-06-patients (pre-archive)

> Gate `spec-scenario-review` (`.agents/skills/spec-scenario-review/SKILL.md`) ejecutado el 2026-11-12
> sobre el change **ya implementado**: `proposal.md`, `design.md`, `specs/clinic/patients/spec.md`,
> `specs/platform-rbac/spec.md` y `tasks.md`, cruzado con `knowledge-base/03_actores_y_roles.md`,
> `04_modelo_de_datos.md`, `05_reglas_de_negocio.md`, `06_funcionalidades.md` (§ US-030) y
> `10_preguntas_abiertas.md`.
>
> Este es el segundo gate del change. El primero (`revision-c-06-pre-apply.md`, 2026-11-11) verificó que
> la spec tuviera ≥3 escenarios por requisito y una tarea de verificación por escenario. Este verifica
> lo inverso: **que cada escenario tenga una prueba ejecutada**, no una promesa.

## Veredicto

**LISTO PARA ARCHIVAR**

- 11 requisitos / **57 escenarios** en la delta de `clinic/patients` + 2 `MODIFIED` de `platform-rbac`.
- **Ningún escenario queda sin prueba**: los 57 aparecen, por nombre o por bloque, en un test que se
  ejecutó en esta sesión (tabla §2).
- Tenancy (RN-TEN-02) completa y con **prueba de mutación** que falla sin la política (§3).
- Sin bloqueantes nuevos. Las 4 observaciones de §4 son desviaciones ya declaradas en el design o en
  `docs/patients.md` §12, no huecos.

## 1. Evidencia de ejecución (2026-11-12)

Corrida dirigida a los módulos del change, posterior a la última edición de código:

```text
$ uv run pytest tests/unit/patients \
    tests/integration/test_patients_http.py tests/integration/test_patients_service.py \
    tests/integration/test_patients_rls.py tests/integration/test_patients_migration.py \
    tests/unit/rbac/test_matrix.py -q
189 passed, 1 warning in 30.07s

$ npx vitest run src/features/patients src/api/patients.test.ts src/App.test.tsx
Test Files  3 passed (3)
     Tests  35 passed (35)

$ E2E_WEB_PORT=5180 npx playwright test
19 passed (25.0s)          # incluye los 4 de patients.spec.ts
```

Suite completa de la misma fecha (línea base del cierre): `ruff` limpio, `mypy app` 70 archivos,
**621 passed** en backend, **96 unit** y **19 e2e** en frontend. No se borró ni se salteó ningún test
respecto de la línea base de C-05 (444 / 67 / 15).

## 2. Correspondencia escenario → prueba ejecutada

`backend/tests/integration/test_patients_http.py` (72 tests) nombra cada test con el id del escenario;
por eso la mayoría de las filas son 1:1. Las columnas "Esperado / Error / Borde" muestran que cada
requisito tiene los tres tipos.

| Requisito | Escenarios | Prueba ejecutada | Resultado |
|---|---|---|---|
| **Listado de pacientes del tenant** | S1.1–S1.6 (6) | `test_s1_1_el_owner_ve_solo_su_tenant_ordenado_y_sin_datos_internos`, `test_s1_2_sin_patient_read_la_lista_no_existe_para_el_backend`, `test_s1_3_un_tenant_sin_pacientes_devuelve_lista_vacia_con_total_cero`, `test_s1_4_paginacion_acota_la_pagina_pero_no_el_total`, `test_s1_4_limites_fuera_de_rango_responden_422`, `test_s1_5_un_paciente_de_otro_tenant_nunca_aparece` + `test_patients_rls.py::test_a_nunca_ve_los_pacientes_de_b`, `test_s1_6_incluir_inactivos_trae_la_baja_sin_exponer_deleted_at` | ✅ |
| **Búsqueda por nombre, DNI o teléfono** | S2.1–S2.6 (6) | `test_s2_1_la_busqueda_ignora_mayusculas_y_acentos`, `test_s2_2_la_busqueda_resuelve_dni_y_telefono`, `test_s2_3_los_comodines_se_escapan_y_no_hay_inyeccion_de_patron` (+ `test_search.py`: 14 unit del `ESCAPE`), `test_s2_4_la_busqueda_no_cruza_tenants`, `test_s2_5_un_q_de_61_caracteres_se_rechaza_antes_de_consultar`, `test_s2_6_un_q_en_blanco_equivale_a_listar_sin_filtro` | ✅ |
| **Alta de paciente con HCE** | S3.1–S3.6 (6) | `test_s3_1_el_alta_completa_devuelve_la_ficha_y_persiste_la_fila`, `test_s3_2_sin_patient_create_no_se_crea_nada`, `test_s3_3_los_campos_reservados_del_cuerpo_se_rechazan`, `test_s3_4_datos_invalidos_no_generan_historia_clinica`, `test_s3_5_recepcion_da_de_alta_la_ficha_y_sigue_fuera_de_lo_clinico`, `test_s3_6_los_espacios_se_recortan_y_el_apellido_vacio_se_rechaza` (+ `test_schemas.py`: 30 unit del contrato) | ✅ |
| **HCE secuencial y no reciclable** | S4.1–S4.6 (6) | `test_s4_1_tres_altas_consecutivas_dan_000001_000002_y_000003`, `test_s4_2_cada_tenant_arranca_su_propia_secuencia`, `test_s4_3_dar_de_baja_al_ultimo_no_recicla_su_numero`, `test_s4_6_el_formato_crece_por_encima_de_999999`; `test_patients_service.py::test_s4_4_dos_altas_concurrentes_no_colisionan`, `::test_s4_5_una_alta_fallida_por_dni_no_deja_hueco`; `test_hce.py` (8 unit del formato) | ✅ |
| **Duplicado por DNI** | S5.1–S5.6 (6) | `test_s5_1_el_mismo_dni_responde_409_con_el_existente`, `test_s5_2_confirmar_duplicado_no_vence_la_regla_del_dni`, `test_s5_3_el_mismo_dni_en_otro_tenant_es_valido`, `test_s5_4_varios_pacientes_sin_dni_conviven`, `test_s5_6_el_dni_de_un_paciente_dado_de_baja_sigue_bloqueando`; `test_patients_service.py::test_s5_5_la_carrera_chequeo_insert_se_traduce_en_409` | ✅ |
| **Posible duplicado por nombre o teléfono** | S6.1–S6.7 (7) | `test_s6_1_nombre_y_apellido_equivalentes_disparan_la_confirmacion`, `test_s6_2_el_telefono_repetido_tambien_dispara_la_confirmacion`, `test_s6_3_confirmar_el_duplicado_crea_la_segunda_ficha`, `test_s6_4_sin_coincidencias_el_alta_es_directa`, `test_s6_5_un_homonimo_de_otro_tenant_no_pide_confirmacion`, `test_s6_6_un_homonimo_dado_de_baja_no_dispara_la_confirmacion`, `test_s6_7_el_409_acota_los_candidatos_a_cinco` | ✅ |
| **Lectura de un paciente por id** | S7.1–S7.3 (3) | `test_s7_1_la_ficha_propia_se_lee_completa_sin_datos_internos`, `test_s7_2_un_id_ajeno_es_indistinguible_de_uno_inexistente`, `test_s7_3_sin_patient_read_no_hay_lectura` | ✅ |
| **Actualización de la ficha** | S8.1–S8.6 (6) | `test_s8_1_se_actualizan_los_datos_de_contacto`, `test_s8_2_los_campos_reservados_no_se_pueden_modificar`, `test_s8_3_cambiar_el_dni_a_uno_ya_usado_responde_409`, `test_s8_4_un_id_ajeno_responde_404_indistinguible`, `test_s8_5_cambiar_el_nombre_actualiza_la_busqueda`, `test_s8_6_sin_patient_update_no_hay_modificacion` (+ `test_schemas.py::test_el_patch_distingue_no_enviado_de_null`) | ✅ |
| **Frontera clínica de la ficha** | S9.1–S9.3 (3) | `test_s9_1_ninguna_respuesta_de_la_ficha_expone_campos_clinicos`, `test_s9_2_recepcion_administra_la_ficha_y_sigue_fuera_de_la_historia_clinica` + `test_4_6_los_roles_clinicos_siguen_recibiendo_501_en_la_sonda`, `test_s9_3_enviar_un_campo_clinico_es_un_error_de_contrato` | ✅ |
| **Permisos de pacientes en la matriz RBAC** | S10.1–S10.3 (3) | `test_matrix.py::test_pacientes_respetan_la_celda_de_cada_rol` + `::test_matriz_completa_coincide_con_la_kb`, `::test_catalogo_de_recursos_y_enum_coherentes` (19 recursos / 61 permisos), `::test_resolve_permissions_no_concede_pacientes_por_defecto` + `::test_resolve_permissions_es_la_union_y_falla_cerrado` | ✅ |
| **Pantalla de pacientes en el SPA** | S11.1–S11.5 (5) | S11.1 `PatientsPage.test.tsx::lista los pacientes que devuelve el backend con su total y su HCE` + `::busca con el término recortado contra el backend` + `patients.spec.ts::el listado consume el backend y muestra el paciente sembrado con su HCE`; S11.2 `::crea el paciente con el backend y lo muestra con su HCE` + `::sin patient.create no renderiza el alta` + `patients.spec.ts::administrativo clínico da de alta una ficha…`; S11.3 `::el DNI duplicado se informa sin diálogo y conserva lo cargado` + mismo e2e; S11.4 `::el posible duplicado lista los candidatos y se confirma con confirmar_duplicado` + `::cancelar el posible duplicado no crea la ficha y conserva el formulario`; S11.5 `::sin patient.read muestra sin permisos y no llama al backend`, `::un 403 del listado se informa como falta de permisos`, `::sin patient.update la tabla no ofrece editar`, `::un 403 al crear se informa como falta de permisos`, `App.test.tsx` (3 de ruta/enlace) y `patients.spec.ts::un profesional ve la lista pero no el alta…` | ✅ |
| **platform-rbac** (MODIFIED 1): catálogo y matriz | S1.1–S1.4 (4) | `test_matrix.py::test_matriz_completa_coincide_con_la_kb`, `::test_catalogo_de_recursos_y_enum_coherentes`, `::test_pacientes_respetan_la_celda_de_cada_rol` | ✅ |
| **platform-rbac** (MODIFIED 2): fronteras duras | S3.1–S3.5 (5) | `test_matrix.py::test_frontera_clinica_por_permiso`, `::test_ningun_rol_tiene_lectura_de_auditoria`, `test_rbac_clinical_boundary.py` (10 tests, preexistentes de C-04, sin cambio de comportamiento) | ✅ |

Chequeo de tipos de escenario por requisito (el criterio del gate):

| Requisito | Esperado | Error de negocio | Borde |
|---|---|---|---|
| Listado | S1.1 | S1.2 (403) | S1.3 vacío, S1.4 paginación, S1.5 cross-tenant, S1.6 inactivos |
| Búsqueda | S2.1, S2.2 | S2.5 (422) | S2.3 comodines, S2.4 cross-tenant, S2.6 `q` vacío |
| Alta | S3.1, S3.5 | S3.2 (403), S3.3 reservados | S3.4 inválidos, S3.6 trim |
| HCE | S4.1, S4.2 | S4.5 (rollback, red = `UNIQUE`) | S4.3 no reciclado, S4.4 concurrencia, S4.6 desborde |
| DNI | S5.1 | S5.2, S5.5, S5.6 | S5.3 cross-tenant, S5.4 varios `NULL` |
| Dedupe blando | S6.3, S6.4 | S6.1, S6.2 | S6.5 cross-tenant, S6.6 inactivo, S6.7 tope 5 |
| Lectura | S7.1 | S7.3 (403) | S7.2 404 indistinguible |
| Actualización | S8.1, S8.5 | S8.3 (409), S8.6 (403) | S8.2 reservados, S8.4 cross-tenant |
| Frontera clínica | S9.1, S9.2 | S9.3 (422) | S9.1 recorre los 4 endpoints |
| RBAC | S10.1 | S10.2 | S10.3 fail-closed |
| Pantalla | S11.1, S11.2, S11.4 | S11.3, S11.5 | S11.5 sin `patient.read` y sin `patient.update` |

## 3. Tenancy (RN-TEN-02)

- [x] Tablas nuevas con `tenant_id NOT NULL`: `patient` y `patient_counter`; ambas con `ENABLE` +
      **`FORCE` `ROW LEVEL SECURITY`** y política `USING`/`WITH CHECK (tenant_id = current_setting(
      'app.current_tenant')::uuid)`, verificado en `test_patients_migration.py`
      (`test_rls_habilitada_y_forzada_con_politica_por_tenant`, parametrizado por tabla).
- [x] `test_patients_rls.py` corre con `SET ROLE odontologia_app` y GUC fijado: leer, actualizar y
      borrar filas de B afecta **0 filas**; sin GUC ambas tablas devuelven 0 (fail-closed); con contexto
      de A no se puede insertar una fila de B; el contador es independiente por tenant.
- [x] **Prueba de mutación** (`test_mutar_rls_desactivada_rompe_el_gate_y_restaurarla_lo_deja_verde`,
      parametrizada para `patient` y `patient_counter`): con `ALTER TABLE … DISABLE ROW LEVEL SECURITY`
      el test cross-tenant ve filas de B y **falla**; al restaurarla vuelve a verde. Evidencia en
      `docs/skills-mcp/evidencias/gate-rls-c-06.md`.
- [x] `tenant_id` sale del token, nunca del body/query: `extra="forbid"` (S3.3) y los tests de HTTP
      confirman que `?tenant_id=` y headers ajenos se ignoran.
- [x] Escenarios cross-tenant ejecutados en las cinco operaciones: listar (S1.5), buscar (S2.4), crear
      (S5.3, S6.5), leer (S7.2), actualizar (S8.4) y HCE por tenant (S4.2).
- [x] El seed e2e corre como superusuario a propósito (ignora RLS) pero **nunca** toca
      `patient_counter`, así que el gate no se puede "aprobar" reciclando números.

Sin bloqueantes de aislamiento.

## 4. Observaciones (desviaciones declaradas, no huecos)

1. **S4.3 se monta con fixture/SQL directo, no por HTTP** — C-06 no expone `DELETE /patients`; dar de
   baja es C-13. El test setea `deleted_at` y verifica que el número no se recicla. Consistente con
   `docs/patients.md` §12.
2. **`patient.delete` está en la matriz y no tiene endpoint** — decisión de C-06 para no tocar la matriz
   dos veces; `patient` no entra en `_NO_PHYSICAL_DELETE` (esa lista es de HC/odontograma, RN-CMP-02).
3. **La carrera del dedupe blando no se prueba como regla dura** — solo el DNI es duro; dos altas
   simultáneas con el mismo nombre pueden pasar. Está declarado en `docs/patients.md` §12 y en `D10`.
4. **S11.1–S11.4 usan `clinical_admin` en e2e, no `owner`** — `owner` exige TOTP y está cubierto por
   `team.spec.ts`; el permiso efectivo sobre `patient.*` es el mismo para la pantalla.

Ninguna de las cuatro cambia el contrato ni deja un escenario sin prueba.

## 5. Checklist final de archivado

| Ítem | Estado |
|---|---|
| 11 requisitos / 57 escenarios en la delta `clinic/patients` | ✅ |
| Cada escenario con una prueba ejecutada (§2) | ✅ |
| Cada requisito con esperado + error de negocio + borde | ✅ |
| Tenancy completa con mutación (§3) | ✅ |
| `MODIFIED` de `platform-rbac` aplicado: 19 recursos / 61 permisos | ✅ (`test_matrix.py`) |
| Suite completa verde y sin tests borrados: 621 / 96 / 19 | ✅ |
| Documentación (`docs/patients.md` 12 secciones) con demo y deudas | ✅ |
| PQ-17 registrada (US-030 vs RN-CMP-04) | ✅ |

## Próximo paso

- Archivar: `openspec validate c-06-patients --strict` → `openspec archive c-06-patients --yes`.
- Verificar post-archive: `openspec/specs/clinic/patients/spec.md` existe con los 11 requisitos,
  `platform-rbac` queda en 19 recursos / 61 permisos, `openspec validate --specs --strict` y
  `--archived --strict` en verde.
- Después: `agendar-turno-sin-solapamiento` (criterio 4 del TPI) con el mismo ciclo de 4 gates.
