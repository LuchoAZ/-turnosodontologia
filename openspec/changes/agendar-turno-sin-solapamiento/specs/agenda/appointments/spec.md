# Spec Delta

## Purpose

Define el contrato de la creación de turnos en la agenda del tenant por profesional y sillón, con prevención de solapamientos, duración/buffers derivados, horarios UTC y aislamiento multi-tenant.

## ADDED Requirements

### Requirement: Crear turno reservando profesional y sillón

El sistema MUST aceptar `POST /api/v1/appointments` y crear el turno reservando simultáneamente un `professional` y un `chair` (RN-AG-01). La operación MUST exigir sesión con membership activa y MUST derivar el `tenant_id` exclusivamente de la sesión/token, ignorando cualquier `tenant_id` recibido en el body (RN-TEN-03). El payload MUST validarse contra el schema Zod compartido frontend↔backend y el estado inicial del turno MUST ser `pendiente`.

#### Scenario: Turno creado correctamente

- **WHEN** se envía un payload válido (`professional_id`, `chair_id`, `patient_id`, horario, `tipo_practica`) sin conflictos en el tenant de la sesión
- **THEN** la respuesta es `201` e incluye el turno creado con `id`, `inicio`, `fin`, `estado = pendiente` y `origen = recepcion`

#### Scenario: Payload inválido

- **WHEN** el payload no cumple el schema Zod compartido (campo faltante, UUID mal formado, `fin <= inicio`)
- **THEN** la respuesta es `422` con el detalle de los campos inválidos y no se crea ningún turno

#### Scenario: Operación sin sesión

- **WHEN** se invoca el endpoint sin una sesión válida
- **THEN** la respuesta es `401` y no se crea ningún turno

### Requirement: Prevenir solapamiento por profesional y por sillón

El sistema MUST rechazar con `409` la creación de un turno cuyo rango `[inicio, fin)` se solape con otro turno activo del mismo `professional` o del mismo `chair` del tenant (RN-AG-02). El rechazo MUST identificar el recurso en conflicto (`professional` | `chair`) y el rango solapado. Los turnos en estado `cancelado` o `no_asistio` MUST NOT generar conflicto. La base de datos MUST ser la garantía final: bajo concurrencia, el `EXCLUDE USING gist` sobre `tstzrange` rechaza el doble booking aunque la validación de aplicación no llegue a verlo.

#### Scenario: Solapamiento por profesional

- **WHEN** se crea un turno cuyo rango se solapa con un turno activo del mismo `professional`
- **THEN** la respuesta es `409`, identifica el recurso `professional` y el rango en conflicto

#### Scenario: Solapamiento por sillón

- **WHEN** se crea un turno cuyo rango se solapa con un turno activo del mismo `chair`
- **THEN** la respuesta es `409`, identifica el recurso `chair` y el rango en conflicto

#### Scenario: Turno cancelado o no asistido no bloquea

- **WHEN** el único turno solapado del recurso está en estado `cancelado` o `no_asistio`
- **THEN** el turno se crea y la respuesta es `201`

#### Scenario: Doble booking concurrente rechazado por la base de datos

- **WHEN** dos requests simultáneos intentan crear turnos solapados para el mismo `professional` o `chair`
- **THEN** uno de ellos responde `201` y el otro responde `409` al fallar el `EXCLUDE USING gist` (garantía dura, no validación de aplicación)

### Requirement: Derivar duración y buffers del tipo de práctica

El sistema MUST derivar el `fin` del turno a partir de la duración del `tipo_practica` y MUST heredar `buffer_previo_min` y `buffer_posterior_min` de la `availability_rule` aplicable; el rango ocupado por el turno MUST incluir duración y buffers al resolver solapamientos (RN-AG-03). Sin `tipo_practica` ni regla aplicable, el sistema MUST usar la duración por defecto del profesional.

#### Scenario: Duración por tipo de práctica con buffers

- **WHEN** el `tipo_practica` tiene duración definida y la `availability_rule` aplicable define buffers previo y posterior
- **THEN** `fin = inicio + duración + buffer_previo + buffer_posterior` y el rango ocupado cubre también los buffers

#### Scenario: Sin tipo de práctica

- **WHEN** el payload no incluye `tipo_practica` y no hay `availability_rule` aplicable
- **THEN** se aplica `duracion_default_min` del profesional y los buffers se consideran 0

### Requirement: Almacenar horarios en UTC

El sistema MUST almacenar `inicio` y `fin` como `timestamptz` (UTC) y MUST aceptar horarios en el payload como `RFC 3339`. Ninguna lógica de negocio MUST operar sobre strings de fecha/hora y toda presentación en la UI MUST convertir al `timezone` del tenant (RN-AG-09).

#### Scenario: Rango en UTC persistido

- **WHEN** el payload envía `inicio` y `fin` en `RFC 3339` con zona horaria
- **THEN** se almacenan como `timestamptz` y la respuesta los devuelve en UTC

### Requirement: Prevenir turnos solapados del mismo paciente con el mismo profesional

El sistema MUST rechazar con `409` un turno si el `patient_id` ya tiene otro turno en estado `pendiente`, `confirmado` o `en_curso` cuyo rango se solape para el mismo `professional` (RN-AG-10).

#### Scenario: Paciente con turno solapado para el mismo profesional

- **WHEN** el paciente ya tiene un turno activo solapado con ese `professional`
- **THEN** la respuesta es `409` y no se crea el turno

#### Scenario: Paciente con turno en otro rango o con otro profesional

- **WHEN** el paciente solo tiene turnos en otros rangos, con otros profesionales, o en estado `cancelado`/`no_asistio`
- **THEN** el turno se crea y la respuesta es `201`

### Requirement: Aislar la agenda por tenant

El sistema MUST aislar los datos de la agenda del tenant con Row Level Security activa en `appointment` y las entidades referenciadas (`chair`, `professional`, `patient`). Todo intento de crear un turno referenciando un `professional_id`, `chair_id` o `patient_id` que no pertenezca al tenant de la sesión MUST resolverse como `404` y MUST NOT crear el turno (RN-TEN-02, RN-EX-06).

#### Scenario: Recurso de otro tenant

- **WHEN** el payload referencia un `professional`, `chair` o `patient` que pertenece a otro tenant
- **THEN** la respuesta es `404` y no se crea ningún turno

#### Scenario: Turnos de un tenant invisibles para otro

- **WHEN** dos tenants tienen turnos en el mismo rango para recursos homólogos
- **THEN** cada tenant solo ve y puede reclamar conflictos sobre sus propios turnos; ninguno puede crear un turno sobre un recurso del otro