# Proposal — c-06-patients

## Why

La agenda necesita reservar turnos **a nombre de alguien**. Hoy no existe la ficha del paciente: no hay
tabla `patient`, no hay permisos `patient.*` en la matriz y la única sonda que toca el tema
(`GET /api/v1/clinical/patients`) responde `501` a propósito porque pertenece al dominio **clínico**
(`clinical_record.read`), que llega en C-09. Sin pacientes, `agendar-turno-sin-solapamiento` no puede
crear un turno real y el criterio 4 del TPI queda sin sustento.

Vale la pena ahora por dos motivos. Primero, es la dependencia dura del entregable. Segundo, el criterio
2 de la rúbrica pide una entidad de negocio con reglas propias verificables: el
`numero_historia_clinica` secuencial y **no reciclable** (RN-CLI-01) es exactamente esa regla, y se puede
demostrar con tests de concurrencia y de baja lógica, no con una diapositiva.

## What Changes

- **Modelos nuevos**: `patient` (ficha demográfica) y `patient_counter` (secuencia de HCE por tenant),
  ambos con `tenant_id NOT NULL`, RLS `ENABLE` + `FORCE` y política por tenant (RN-TEN-02).
- **Migración `006_patients`**: enum `sexo_paciente`, tablas, índices únicos, índice funcional de
  búsqueda con `pg_trgm`, políticas y grants para `odontologia_app`.
- **API** bajo `/api/v1/patients`:
  - `GET /patients` — listado con búsqueda (`q`), paginación (`limit`/`offset`) e `incluir_inactivos`.
  - `GET /patients/{id}` — ficha por id.
  - `POST /patients` — alta; genera el número de HCE y detecta duplicados.
  - `PATCH /patients/{id}` — actualización parcial de datos demográficos.
  - **Sin `DELETE`**: la baja lógica con justificación pertenece a C-13 (derecho de supresión, Ley 25.326).
- **Reglas de negocio**:
  - `numero_historia_clinica` `000001`, `000002`… por tenant, único, **nunca reciclado** aunque el
    paciente se dé de baja (RN-CLI-01).
  - DNI único por tenant con índice parcial: dos pacientes pueden no tener DNI, pero dos con el mismo
    DNI en el mismo tenant no (RN-CLI-01/RN-EX-03).
  - Dedupe **duro** por DNI (`409 patient_dni_duplicado`) y **blando** por nombre/apellido/teléfono
    normalizados (`409 patient_posible_duplicado`, confirmable con `confirmar_duplicado: true`).
  - Búsqueda por nombre/apellido (insensible a mayúsculas y acentos), DNI y teléfono.
- **Matriz RBAC**: nueva fila `patient` en `knowledge-base/03_actores_y_roles.md` y en
  `backend/app/domain/rbac/matrix.py` → **19 recursos / 61 permisos**. Dirección clínica y recepción
  crean y editan la ficha; odontología, higienista y facturación la leen; el owner además podría darla
  de baja (permiso reservado para C-13, sin endpoint en este change).
- **Frontera clínica**: `PatientOut` **no** expone `alergias`, `alerta_clinica` ni ningún dato de
  historia clínica. Recepción administra la ficha demográfica y sigue sin leer la HC (RN-CMP-04). La
  sonda `GET /api/v1/clinical/patients` **no se toca**: es la frontera de C-09, no la de pacientes.
- **Frontend**: ruta `/pacientes` con listado, búsqueda, alta y edición; diálogo de confirmación de
  posible duplicado; visibilidad por `patient.*`; errores por `code` (nunca por texto).

**Fuera de alcance (explícito)**: `GET /patients/{id}/timeline` (C-09), baja lógica con justificación
(C-13), exposición de `alergias`/`alerta_clinica` (C-09, ver deuda), catálogo de obras sociales
(`obra_social_id` se persiste nullable sin FK hasta la migración de datos), portal del paciente y
`patient.read_own` (post-deadline), importación CSV/XLSX (C-08), adjuntos y auditoría de lecturas
(C-13).

## Capabilities

### New Capabilities

- `clinic/patients`: ficha demográfica del paciente con número de historia clínica por tenant,
  detección de duplicados, búsqueda y frontera clínica. Es la entidad que la agenda referencia al
  reservar un turno.

### Modified Capabilities

- `platform-rbac`: la matriz de permisos suma el recurso `patient` (4 permisos) y pasa de 18 a 19
  recursos y de 57 a 61 permisos. No cambia el mecanismo de guarda ni la resolución de permisos.

## Impact

- **Base de datos**: migración `006_patients` (2 tablas, 1 enum, índices, `CREATE EXTENSION pg_trgm`,
  políticas RLS y grants).
- **Backend**: `app/models/patients.py`, `app/domain/patients/` (errores, normalización, servicio),
  `app/schemas/patients.py`, `app/api/v1/patients/` (router); cambio acotado en
  `app/domain/rbac/matrix.py` y registro del router y del handler en `app/main.py`.
- **Frontend**: `src/api/patients.ts`, `src/features/patients/` (página + diálogos + tests), ruta
  `/pacientes` y enlace en la Home condicionado a `patient.read`.
- **Knowledge base**: fila `Pacientes` en `03_actores_y_roles.md`; preguntas abiertas PQ-17 (US-030 vs
  RN-CMP-04) y deudas registradas en `docs/patients.md`.
- **Tests**: unitarios de normalización/HCE/errores; integración con Postgres real (CRUD, secuencia y
  concurrencia, dedupe, búsqueda, aislamiento cross-tenant como gate RN-TEN-02); unit de la matriz
  (19 recursos/61 permisos); unit y e2e del frontend.
- **Dependencias**: C-01 (fundación), C-02 (`tenant`, RLS, rol de app), C-03 (sesión y tenant del
  token), C-04 (guarda `require_permission` y matriz). Habilita `agendar-turno-sin-solapamiento`.
- **Deuda registrada**: US-030 pide a recepción capturar `alergias` y `alerta_clinica`, pero RN-CMP-04
  le prohíbe leer historia clínica; se difieren a C-09 y se documenta la contradicción. La búsqueda
  insensible a acentos se resuelve con columnas normalizadas calculadas por la aplicación
  (`apellido_norm`, `nombre_norm`), no con `unaccent` en la base.
