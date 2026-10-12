# Proposal

## Why

Este change entrega la funcionalidad central de la **Épica E2 — Agenda por profesional y sillón** (US-012 "Agendar un turno", **P0 Slice 2** del MVP según `knowledge-base/01_vision_y_objetivos.md` § Alcance v0.1): crear un turno (`POST /api/v1/appointments`) que verifica solapamientos por profesional **y** por sillón/box. Es un entregable de TP: una única funcionalidad de negocio con reglas verificables (RN-AG-01, RN-AG-02, RN-AG-03, RN-AG-09, RN-AG-10) y evidencia testable de punta a punta (API + formulario mínimo), en vertical slice (DD-03).

Vale la pena **ahora** porque es el primer valor demostrable de la "ruta del turno" del Sprint 1 dev (SU-02, deadline 2026-10-23): agrega el primer endpoint de negocio con garantía dura contra el doble booking (`EXCLUDE USING gist`), el ansatz de disponibilidad que reutilizarán C-07/C-08, y el gate de aislamiento cross-tenant (RN-TEN-02) que toda capacidad con `tenant_id` debe pasar.

> **Justificación de la elección**: la funcionalidad elegida es la creación de un turno con verificación de solapamientos, núcleo de la épica E2 (Agenda por sillón), una de las 10 capacidades imprescindibles del MVP (DD-01/DD-03). Su regla de negocio central — no solapar por profesional ni por sillón/box — es verificable (RN-AG-02) y constituye el primer valor demostrable de punta a punta. Se acota a una sola funcionalidad para garantizar su terminación en el sprint.

> **Contexto (Sección D del TP)**: la Sección D recomendó **5 competidores prioritarios para demo** (OdontoClinIA, DentalCore, Bilog, DentalSoft y Dentalink), **3 referencias de UX** (DentalSoft, DentalCore, Dentiqa) y un **MVP sugerido** con 10 funcionalidades imprescindibles, diferenciadores y funcionalidades diferidas (`discovery/discovery.md` §5–§6 y Anexos). Este change pertenece al imprescindible **#1 — "Agenda por profesional y por sillón/box"**: los 20 competidores la tienen como requisito de entrada, pero ninguno modela el sillón como unidad de capacidad bloqueable con anti-solapamiento garantizado por la base de datos — el diferenciador central del MVP (discovery §4.5).

## What Changes

- **Endpoint `POST /api/v1/appointments`** (NestJS 11): crea un turno reservando **dos recursos a la vez** (`professional_id` + `chair_id`, RN-AG-01). Responde `201` con el turno creado.
- **Validación de solapamiento en aplicación** dentro de una transacción: detecta conflicto y responde `409` identificando el recurso (`professional` | `chair`) y el **rango en conflicto** (RN-AG-02, RN-AG-10). Casos: profesional ya ocupado, sillón ya ocupado, paciente con turno solapado para el mismo profesional.
- **Validación de entrada con Zod** (schema compartido `packages/shared`, mismo esquema en frontend y backend): `422` con detalle de campos ante payload inválido.
- **Derivación de duración por tipo de práctica** con herencia de buffers previo/posterior de `availability_rule` (RN-AG-03): el turno ocupa duración + buffers; `inicio`/`fin` se almacenan como `timestamptz` UTC (RN-AG-09).
- **Aislamiento multi-tenant**: `tenant_id` se resuelve **solo de la sesión/token** (nunca del body, RN-TEN-03); RLS activa en `appointment`; acceso a un recurso de otro tenant responde `404` (aislado, no lista el recurso).
- **Formulario mínimo de UI** (Next.js 15, shadcn/ui) que consume el endpoint: elegir paciente, profesional, sillón, tipo de práctica y horario; mapa de errores `409` → conflicto visible, `422` → errores de campo, `404` → recurso inexistente.
- **Garantía dura en la base de datos**: el modelo `appointment` ya declara `EXCLUDE USING gist` sobre `chair_id` y `professional_id` con `tstzrange` (provisto por las dependencias C-02/C-07; este change la **ejerce y la testea**, no la reimplementa).

## Capabilities

### New Capabilities
- `agenda/appointments`: creación de turnos en la agenda del tenant — reserva simultánea de profesional y sillón, prevención de solapamientos (garantía de aplicación + de base de datos), derivación de duración/buffers, uso de horarios UTC y aislamiento por tenant. Es la capacidad durable que luego extenderán reprogramación, cancelación y check-in en C-07/C-08.

### Modified Capabilities
<!-- No hay capabilities existentes: `openspec list --specs` reporta inventario vacío; este change crea la primera. -->

## Impact

- **API (`apps/api`)**: nuevo módulo de feature `appointments` (controlador + servicio + DTO Zod + guard de tenant) dentro del slice vertical de la capacidad.
- **Schemas compartidos (`packages/shared`)**: contrato Zod del payload `CreateAppointment` y el schema de respuesta/errores, compartido web↔api.
- **UI (`apps/web`)**: página/formulario mínimo de agendamiento (ruta `/turnos/nuevo`), consumiendo el mismo schema Zod para validar antes del submit.
- **Tests**: suite de integración con Postgres real (Testcontainers) — alta ok, solape por `professional_id`, solape por `chair_id`, solape RN-AG-10 del paciente, doble booking bajo concurrencia rechazado por la BD, `422` de Zod, y **test de aislamiento cross-tenant (gate RN-TEN-02)**. E2E mínimo con Playwright del formulario.
- **Dependencias listadas, NO implementadas**: C-01 (foundation-setup), C-02 (core-models-tenancy, aporta modelo `appointment` con `EXCLUDE` + RLS), C-03 (auth-sessions, aporta sesión y scoping de tenant), C-05 (clinic-setup, aporta `chair`, `professional`, `availability_rule`), C-06 (patients, aporta `patient`).
- **Fuera de alcance (explícito)**: reprogramar (PATCH/reschedule), cancelar, check-in/complete, lista de espera, cálculo de disponibilidad/grilla (`GET /availability`), portal paciente y WhatsApp — pertenecen a C-07/C-08/C-19/C-20 y no entran en este change.