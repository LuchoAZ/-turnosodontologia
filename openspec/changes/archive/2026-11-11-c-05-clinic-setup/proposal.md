# Proposal — c-05-clinic-setup

## Why

La agenda del TPI necesita tres cosas antes de poder reservar un turno: los **sillones** (la unidad de
capacidad escasa, RN-AG-01), los **profesionales** con su matrícula y duración por defecto, y las
**reglas de disponibilidad** que definen ventanas, `slot_min` y buffers (RN-AG-03). Hoy no existe
ninguna de las tres: `appointment` no puede crearse porque no hay a quién ni dónde asignarlo.

Vale la pena ahora porque es la dependencia dura de `agendar-turno-sin-solapamiento` (el entregable del
TP) y porque cierra el criterio 4 de la rúbrica por el lado de la configuración: sin sillones y
profesionales reales, la demo de reserva sería sobre datos inventados en memoria.

## What Changes

- **Modelos nuevos**: `chair`, `professional` y `availability_rule`, con `tenant_id NOT NULL`, RLS
  `ENABLE` + `FORCE` y política por tenant (RN-TEN-02).
- **Migración `005_clinic_setup`**: enums `chair_tipo`, tablas, índices únicos, FK a `specialty`,
  políticas y grants para `odontologia_app`.
- **API** bajo `/api/v1/clinic`:
  - `GET/POST /chairs`, `PATCH /chairs/{id}`, `DELETE /chairs/{id}` (baja **lógica**).
  - `GET/POST /professionals`, `PATCH /professionals/{id}` (incluye `activo = false`).
  - `GET /specialties` (catálogo visible: globales + propias; lo consume el alta de profesional).
  - `GET/POST /availability`, `PATCH /availability/{id}`.
- **Reglas de negocio**: unicidad de `(tenant_id, nombre)` en sillones y `(tenant_id, matricula)` en
  profesionales; ventana de disponibilidad cerrada (`hora_fin > hora_inicio`, múltiplo exacto de
  `slot_min`); buffers no negativos; reglas sin solape para el mismo alcance y día.
- **Frontend**: ruta `/clinica` con tres secciones (Sillones, Profesionales, Disponibilidad) que
  decide visibilidad solo por permiso (`chair.*`, `professional.*`) y muestra los `code` de error.
- **Auditoría**: no se agrega tabla nueva; los cambios de equipo siguen en `membership_event`.

**Fuera de alcance (explícito)**: `GET /chairs/{id}/utilization` (necesita `appointment`),
`POST /professionals/{id}/schedule` como alias (se reemplaza por `/availability`), activación real de
RN-AG-06 (requiere turnos, llega con la agenda), vínculo `membership.professional_id` (sigue nullable,
se completa cuando exista el flujo de "mi agenda"), cálculo de disponibilidad de slots
(`GET /availability/slots`) y cualquier UI de calendario.

## Capabilities

### New Capabilities

- `clinic/setup`: configuración operativa de la clínica — sillones como unidad de capacidad,
  profesionales con matrícula única y reglas de disponibilidad por día con slots y buffers. Es la
  capacidad que la agenda (`agenda/appointments`) consulta para saber qué recursos existen y en qué
  ventanas se puede reservar.

### Modified Capabilities

Ninguna. `platform-rbac` ya declara `chair.*` y `professional.*`; este change las **usa**, no cambia la
matriz de permisos.

## Impact

- **Base de datos**: migración `005_clinic_setup` (3 tablas + 1 enum + políticas RLS + índices).
- **Backend**: `app/models/clinic.py`, `app/domain/clinic/` (servicio + validaciones),
  `app/api/v1/clinic/` (router), `app/schemas/clinic.py`.
- **Frontend**: `src/api/clinic.ts`, `src/features/clinic/` (3 secciones + tests), ruta `/clinica` y
  enlace en la Home condicionado a `chair.read`.
- **Tests**: unitarios de validación (ventana/buffers/matrícula), integración con Postgres real (CRUD,
  unicidad, bajas lógicas, aislamiento cross-tenant como gate RN-TEN-02) y e2e del flujo de alta.
- **Dependencias**: C-01 (fundación), C-02 (`tenant`, RLS, rol de app, `specialty` seed), C-03 (sesión y
  tenant del token), C-04 (permisos `chair.*` / `professional.*`). Habilita
  `agendar-turno-sin-solapamiento`.
- **Deuda registrada**: la matriz de la KB no tiene un recurso `availability`; se reutiliza
  `professional.read` / `professional.update` y se anota en `docs/clinic.md` para revisar la matriz si
  la KB incorpora el recurso.
