# Gate de aislamiento cross-tenant — agenda (task 6.1)

> Evidencia del gate **bloqueante de merge** del change `agendar-turno-sin-solapamiento`
> (RN-TEN-02). Ejecutado el **2026-11-12** con Docker + Postgres 16 real
> (Testcontainers), con la cadena Alembic completa (`007_agenda`) y la API montada.
> Comandos:
>
> ```
> uv run pytest tests/integration/test_appointments_rls.py -q
> ```

## Resultado

```
8 passed
```

Cubre tres niveles (los 8 tests del archivo):

| Test | Qué prueba |
|---|---|
| `test_6_1_un_recurso_de_otro_tenant_es_404_y_no_crea_nada[professional_id/chair_id/patient_id]` | Con sesión de A, referenciar un recurso de B responde `404 recurso_no_encontrado` — nunca `403` ni `200` — y no crea nada en A ni en B. |
| `test_6_1_un_tenant_id_ajeno_con_recursos_ajenos_es_404_y_no_escribe_en_b` | `tenant_id` de B en body + query (`?tenant_id=`) + header (`X-Tenant-Id`) con recursos de B → `404`, sin filas en B. |
| `test_6_1_un_tenant_id_ajeno_con_recursos_propios_nace_en_el_tenant_de_la_sesion` | El mismo `tenant_id` ajeno con recursos de A → `201` **en A**; B queda vacío: el tenant sale del token, no del cliente (RN-TEN-03). |
| `test_6_1_turnos_homologos_de_dos_tenants_no_generan_conflicto_entre_si` | Mismos instantes en A y B con recursos homólogos → `201` en ambos: los `EXCLUDE` no cruzan tenants. |
| `test_6_1_el_rol_de_app_solo_ve_los_turnos_de_su_tenant` | Con `SET ROLE odontologia_app` + GUC del tenant, `SELECT` devuelve **solo** las filas de ese tenant. |
| `test_6_1_el_gate_corre_con_el_rol_de_app_no_con_el_superusuario` | El engine de la app es `odontologia_app` y `rolbypassrls = false`: el verde no es del superusuario del contenedor (RLS activa de verdad). |

## Prueba de mutación

La verificación exigida por la task no es solo "verde": es que el gate **se ponga
rojo** si se rompe el aislamiento. Se mutaron las dos capas a la vez (con RLS
activa el filtro de aplicación es redundante y la mutación no probaría nada):

1. `ALTER TABLE {appointment,professional,chair,patient} DISABLE ROW LEVEL SECURITY`
   (superusuario, inyectado como plugin temporal `-p mutacion_rls_agenda`).
2. Servicio mutado: se quitaron los **5** filtros `tenant_id` de
   `_get_professional`, `_get_chair`, `_get_patient` y de las dos consultas de
   solape (`_solape_de_recurso`, `_solape_de_paciente`).

Resultado de la corrida mutada:

```
5 failed, 3 passed
FAILED test_6_1_un_recurso_de_otro_tenant_es_404_y_no_crea_nada[professional_id]
FAILED test_6_1_un_recurso_de_otro_tenant_es_404_y_no_crea_nada[chair_id]
FAILED test_6_1_un_recurso_de_otro_tenant_es_404_y_no_crea_nada[patient_id]
FAILED test_6_1_un_tenant_id_ajeno_con_recursos_ajenos_es_404_y_no_escribe_en_b
FAILED test_6_1_el_rol_de_app_solo_ve_los_turnos_de_su_tenant
```

El caso `[professional_id]` demuestra el leak completo: el request autenticado
como A referenciando el profesional de B **crea** el turno y responde `201` con
el UUID ajeno en el cuerpo.

```
assert response.status_code == 404, response.text
E  assert 201 == 404
E   +  where 201 = <Response [201 Created]>.status_code
E  {"id":"ccd287cc-…","professional_id":"538f680c-…","chair_id":"46b9f875-…", …}
```

Restaurado el servicio y borrado el plugin, la corrida vuelve a `8 passed`:
**cross-tenant leak = 0** con las dos capas intactas.

## Notas de implementación

- El servicio filtra `tenant_id` **además** de RLS: el `404` indistinguible de un
  id inexistente (RN-EX-06) no depende del error de la base, y la consulta no gana
  nada con el scaneo cruzado.
- La mutación se aplicó con un script que **asserta** que cada filtro aparece
  exactamente una vez (dos en el caso de las consultas de solape): si el archivo
  cambia, la mutación falla en vez de pasar en silencio sin haber mutado nada.
- El plugin de RLS se borró al terminar y el servicio se restauró desde un backup
  byte a byte (verificado: 0 ocurrencias de `MUTACION` en el archivo final).
- El plugin temporal no quedó en el repo: la suite normal nunca corre con RLS
  apagada.
- Si este archivo se pone rojo, el change **no se puede archivar** (regla dura del
  proyecto: `cross-tenant leak = 0` es gate de merge, no sugerencia).
