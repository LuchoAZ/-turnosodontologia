# agenda/appointments Specification

## Purpose
Define el contrato de la creación de turnos en la agenda del tenant por profesional y sillón, con prevención de solapamientos, duración/buffers derivados, horarios UTC y aislamiento multi-tenant.

## Requirements

### Requirement: Crear turno reservando profesional y sillón

El sistema MUST aceptar `POST /api/v1/appointments` y crear el turno reservando simultáneamente un `professional` y un `chair` (RN-AG-01). Ambos recursos MUST existir en el tenant de la sesión y estar `activo = true`; si alguno está inactivo, la creación MUST rechazarse con `409` identificando el recurso y `motivo = recurso_inactivo`. El payload MUST aceptar `professional_id`, `chair_id`, `patient_id` (nullable: turno sin paciente identificado), `inicio` en RFC 3339 con offset obligatorio y `tipo_practica` opcional; MUST NOT aceptar `fin` ni `duracion_min`, porque el servidor los deriva (RN-AG-03): un campo desconocido MUST rechazarse con `422`. La operación MUST exigir sesión con membership activa y MUST derivar el `tenant_id` exclusivamente de la sesión/token, ignorando cualquier `tenant_id` recibido en body, query o header (RN-TEN-03). El payload MUST validarse contra el schema Pydantic v2 del backend y el estado inicial del turno MUST ser `pendiente`.

#### Scenario: Turno creado correctamente

- **WHEN** se envía un payload válido (`professional_id`, `chair_id`, `patient_id`, `inicio`, `tipo_practica`) sin conflictos en el tenant de la sesión
- **THEN** la respuesta es `201` e incluye el turno creado con `id`, `inicio`, `fin`, `duracion_min`, `estado = pendiente` y `origen = recepcion`

#### Scenario: Payload inválido

- **WHEN** el payload no cumple el schema Pydantic (campo faltante, UUID mal formado, `inicio` sin offset, `fin` o `duracion_min` enviados por el cliente)
- **THEN** la respuesta es `422` con el detalle de los campos inválidos y no se crea ningún turno

#### Scenario: Recurso inactivo

- **WHEN** el `professional_id` o el `chair_id` existe en el tenant pero tiene `activo = false`
- **THEN** la respuesta es `409` con `{ recurso, motivo: "recurso_inactivo" }` y no se crea ningún turno

#### Scenario: Operación sin sesión

- **WHEN** se invoca el endpoint sin una sesión válida
- **THEN** la respuesta es `401` y no se crea ningún turno

#### Scenario: Operación sin permiso
- **WHEN** la sesión es válida y tiene membership activa pero su rol no incluye `appointment.create`
- **THEN** la respuesta es `403` con `code = forbidden` (lo emite la guarda de RBAC, C-04) y no se crea ningún turno

#### Scenario: Sesión sin membership activa

- **WHEN** la sesión es válida pero no tiene una `membership` activa en el tenant
- **THEN** la respuesta es `401`, no se resuelve `tenant_id` y no se crea ningún turno

### Requirement: Prevenir solapamiento por profesional y por sillón

El sistema MUST rechazar con `409` la creación de un turno cuyo rango bloqueado `[inicio - buffer_previo_min, fin + buffer_posterior_min)` se solape con el de otro turno del mismo `professional` o del mismo `chair` del tenant cuyo estado NO sea `cancelado` ni `no_asistio` (mismo criterio que el `EXCLUDE`; RN-AG-02). El rechazo MUST identificar el recurso en conflicto (`professional` | `chair`) y el rango solapado. Los turnos en estado `cancelado` o `no_asistio` MUST NOT generar conflicto. La base de datos MUST ser la garantía final: bajo concurrencia, el `EXCLUDE USING gist` sobre el rango bloqueado rechaza el doble booking aunque la validación de aplicación no llegue a verlo. El `EXCLUDE` MUST comparar marcas UTC (`tsrange((inicio AT TIME ZONE 'UTC') - make_interval(...), ...)`): `timestamptz - interval` no es `IMMUTABLE` y Postgres lo rechaza en un índice.

#### Scenario: Solapamiento por profesional

- **WHEN** se crea un turno cuyo rango se solapa con un turno activo del mismo `professional`
- **THEN** la respuesta es `409`, identifica el recurso `professional` y el rango en conflicto

#### Scenario: Solapamiento por sillón

- **WHEN** se crea un turno cuyo rango se solapa con un turno activo del mismo `chair`
- **THEN** la respuesta es `409`, identifica el recurso `chair` y el rango en conflicto

#### Scenario: Turno cancelado o no asistido no bloquea

- **WHEN** el único turno solapado del recurso está en estado `cancelado` o `no_asistio`
- **THEN** el turno se crea y la respuesta es `201`

#### Scenario: Turno contiguo no se considera solapamiento

- **WHEN** el rango bloqueado del turno nuevo empieza exactamente cuando termina el rango bloqueado de otro del mismo recurso (con buffers 0: `nuevo.inicio == existente.fin`)
- **THEN** la respuesta es `201`, porque el rango es `[inicio, fin)` y el extremo final es exclusivo

#### Scenario: Solapamiento producido solo por un buffer

- **WHEN** los rangos clínicos (`[inicio, fin)`) de dos turnos del mismo recurso no se tocan, pero el rango bloqueado del existente se extiende por su `buffer_posterior_min` (o el del nuevo por su `buffer_previo_min`) hasta alcanzarlos
- **THEN** la respuesta es `409`, porque el solape se evalúa sobre el rango **bloqueado**, no sobre el clínico (RN-AG-03)

#### Scenario: Doble booking concurrente rechazado por la base de datos

- **WHEN** dos requests simultáneos intentan crear turnos solapados para el mismo `professional` o `chair`
- **THEN** uno de ellos responde `201` y el otro responde `409` al fallar el `EXCLUDE USING gist` (garantía dura, no validación de aplicación)

### Requirement: Derivar duración y buffers del tipo de práctica

El sistema MUST derivar la duración base del turno en este orden: (1) `slot_min` de la `availability_rule` que matchee el `professional_id` (o `professional_id IS NULL`), el `chair_id` (o `chair_id IS NULL`), el día de la semana y la ventana horaria, y que declare el `tipo_practica` solicitado; (2) `duracion_default_min` del `professional`. El sistema MUST persistir `duracion_min` y calcular `fin = inicio + duracion_min`. El turno MUST heredar `buffer_previo_min` y `buffer_posterior_min` de la `availability_rule` aplicable (aunque no declare `tipo_practica`) y persistirlos como snapshot; el rango bloqueado MUST ser `[inicio - buffer_previo_min, fin + buffer_posterior_min)` y MUST ser el que usan tanto el pre-chequeo de aplicación como el `EXCLUDE` de la base (RN-AG-03). Un `tipo_practica` fuera del enum del dominio MUST rechazarse con `422`. Si la duración resuelta es `<= 0`, el sistema MUST rechazar la creación con `409` (`motivo = duracion_invalida`) en lugar de crear un turno de duración inválida.

#### Scenario: Duración por tipo de práctica con buffers

- **WHEN** el `tipo_practica` tiene una `availability_rule` aplicable con `slot_min` definido y buffers previo y posterior
- **THEN** `fin = inicio + slot_min`, se persisten ambos buffers y el rango bloqueado es `[inicio - buffer_previo, fin + buffer_posterior)`

#### Scenario: Sin tipo de práctica

- **WHEN** el payload no incluye `tipo_practica` y no hay `availability_rule` aplicable
- **THEN** se aplica `duracion_default_min` del profesional y ambos buffers se persisten en 0

#### Scenario: Tipo de práctica fuera del enum

- **WHEN** el payload envía un `tipo_practica` que no pertenece al enum del dominio
- **THEN** la respuesta es `422` con el detalle del campo y no se crea ningún turno

#### Scenario: Duración no derivable

- **WHEN** la duración resuelta (regla o `duracion_default_min`) es `<= 0` por configuración inválida del tenant
- **THEN** la respuesta es `409` con `{ motivo: "duracion_invalida" }` y no se crea ningún turno

> Guarda defensiva: los `CHECK` vigentes (`duracion_default_min BETWEEN 5 AND 480`, `slot_min > 0`)
> la hacen inalcanzable por API. El caso se testea mutando el esquema (drop/re-add del `CHECK`) y
> restaurándolo en `finally`; se conserva por si un change futuro relaja los `CHECK`.

### Requirement: Almacenar horarios en UTC

El sistema MUST almacenar `inicio` y `fin` como `timestamptz` (UTC) y MUST aceptar horarios en el payload como `RFC 3339`. Ninguna lógica de negocio MUST operar sobre strings de fecha/hora y toda presentación en la UI MUST convertir al `timezone` del tenant (RN-AG-09).

#### Scenario: Rango en UTC persistido

- **WHEN** el payload envía `inicio` en `RFC 3339` con zona horaria
- **THEN** se almacena como `timestamptz`, el servidor deriva `fin` y la respuesta devuelve ambos en UTC

#### Scenario: Fecha sin offset de zona

- **WHEN** `inicio` llega sin offset (por ejemplo `2026-11-20T09:00:00`)
- **THEN** la respuesta es `422`, no se asume la zona del servidor y no se crea ningún turno

#### Scenario: Turno que cruza la medianoche

- **WHEN** el turno empieza a las 23:30 en la zona del tenant y dura 60 minutos
- **THEN** se persiste en UTC con `fin` en el día siguiente y la respuesta no recorta ni desplaza el rango

### Requirement: Prevenir turnos solapados del mismo paciente con el mismo profesional

El sistema MUST rechazar con `409` un turno si el `patient_id` ya tiene otro turno en estado `pendiente`, `confirmado` o `en_curso` cuyo rango se solape para el mismo `professional` (RN-AG-10). Si `patient_id` es `NULL` (turno sin paciente identificado), la regla MUST NOT aplicarse.

#### Scenario: Paciente con turno solapado para el mismo profesional

- **WHEN** el paciente ya tiene un turno en estado `pendiente`, `confirmado` o `en_curso` solapado con ese `professional`
- **THEN** la respuesta es `409` y no se crea el turno

#### Scenario: Paciente con turno en otro rango o con otro profesional

- **WHEN** el paciente solo tiene turnos en otros rangos, con otros profesionales, o en estado `cancelado`/`no_asistio`
- **THEN** el turno se crea y la respuesta es `201`

#### Scenario: Turno sin paciente identificado

- **WHEN** `patient_id` es `NULL` y ya existe otro turno solapado del mismo `professional`
- **THEN** RN-AG-10 no se evalúa (nunca responde `paciente_solapado`), pero el turno **no** se crea si el recurso está ocupado: RN-AG-02 es regla dura y responde `409 turno_solapado`

### Requirement: Aislar la agenda por tenant

El sistema MUST aislar los datos de la agenda del tenant con Row Level Security activa en `appointment` y las entidades referenciadas (`chair`, `professional`, `patient`). Todo intento de crear un turno referenciando un `professional_id`, `chair_id` o `patient_id` que no pertenezca al tenant de la sesión MUST resolverse como `404` y MUST NOT crear el turno (RN-TEN-02, RN-EX-06).

#### Scenario: Recurso de otro tenant

- **WHEN** el payload referencia un `professional`, `chair` o `patient` que pertenece a otro tenant
- **THEN** la respuesta es `404` y no se crea ningún turno

#### Scenario: Turnos de un tenant invisibles para otro

- **WHEN** dos tenants tienen turnos en el mismo rango para recursos homólogos
- **THEN** cada tenant solo ve y puede reclamar conflictos sobre sus propios turnos; ninguno puede crear un turno sobre un recurso del otro

#### Scenario: `tenant_id` en el body se ignora

- **WHEN** el payload, la query o un header incluyen un `tenant_id` del tenant B mientras la sesión es del tenant A y los recursos son del tenant A
- **THEN** el campo se ignora, el turno se crea en el tenant A con `201` y en el tenant B no existe

#### Scenario: `tenant_id` del body no habilita recursos ajenos

- **WHEN** el payload incluye un `tenant_id` del tenant B y referencia recursos del tenant B, con sesión del tenant A
- **THEN** la respuesta es `404` y no se crea ningún turno en el tenant B
