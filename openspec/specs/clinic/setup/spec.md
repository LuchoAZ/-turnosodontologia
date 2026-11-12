# clinic/setup Specification

## Purpose
Define la configuración operativa de la clínica: los **sillones** como unidad de capacidad (RN-AG-01),
los **profesionales** con matrícula única por tenant y duración por defecto, y las **reglas de
disponibilidad** que fijan ventanas, `slot_min` y buffers (RN-AG-03). Es la capacidad que la agenda
consulta antes de reservar un turno. Incluye el **catálogo visible de especialidades** con el que el
alta de profesional resuelve `especialidad_id`. Todo opera bajo RLS con el `tenant_id` resuelto del
token (RN-TEN-02, RN-TEN-03) y toda baja es **lógica**, sin perder historial (RN-EX-03).

## Requirements

### Requirement: Lectura de los sillones del tenant

`GET /api/v1/clinic/chairs` MUST exigir `chair.read` y devolver los sillones del tenant de la sesión
con `id`, `nombre`, `tipo`, `ubicacion`, `equipamiento` y `activo`. MUST incluir los sillones inactivos
con `activo: false` para no perder el historial (RN-EX-03) y MUST NOT exponer `tenant_id` ni datos de
otro tenant. El orden MUST ser estable (por `tipo` y luego por `nombre`).

#### Scenario: S1.1 — El owner ve los sillones activos e inactivos de su tenant

- **WHEN** una sesión `owner` invoca `GET /api/v1/clinic/chairs` en un tenant con dos sillones activos y
  uno dado de baja
- **THEN** responde `200` con las tres filas, la dada de baja incluida con `activo: false`
- **AND** el JSON no contiene `tenant_id` y el orden es estable entre dos llamadas consecutivas

#### Scenario: S1.2 — Sin chair.read la lista no existe para el backend

- **WHEN** una sesión con un rol sin `chair.read` invoca `GET /api/v1/clinic/chairs`
- **THEN** responde `403` con `code = "forbidden"`
- **AND** el log registra el permiso faltante y la respuesta no incluye nombres de sillones

#### Scenario: S1.3 — Un tenant sin sillones devuelve una lista vacía

- **WHEN** una sesión `owner` de un tenant recién creado invoca `GET /api/v1/clinic/chairs`
- **THEN** responde `200` con `{"chairs": []}` y no `404`

### Requirement: Alta de sillón

`POST /api/v1/clinic/chairs` MUST exigir `chair.create` y aceptar `nombre` (1–60), `tipo`
(`consultorio` | `rx` | `cirugia` | `higiene` | `otro`), `ubicacion` (opcional, ≤120) y `equipamiento`
(objeto JSON, por defecto `{}`). MUST rechazar un `nombre` repetido en el mismo tenant con
`409 chair_name_taken` (índice único `(tenant_id, nombre)`). El `activo` nace en `true` y el
`tenant_id` sale siempre de la sesión.

#### Scenario: S2.1 — Alta de un sillón con todos sus atributos

- **WHEN** un `owner` envía `{"nombre": "Sillón RX", "tipo": "rx", "ubicacion": "Planta alta",
  "equipamiento": {"intraoral_camera": true}}`
- **THEN** responde `201` con `id`, `activo: true` y el `equipamiento` intacto
- **AND** una lectura posterior devuelve exactamente los mismos valores

#### Scenario: S2.2 — Nombre repetido en el tenant

- **WHEN** un `owner` intenta crear un segundo sillón con `nombre = "Sillón 1"` en el mismo tenant
- **THEN** responde `409` con `code = "chair_name_taken"`
- **AND** la cantidad de sillones del tenant no cambia

#### Scenario: S2.3 — Tipo fuera del catálogo

- **WHEN** un `owner` envía `"tipo": "resonador"`
- **THEN** responde `422` con `code = "invalid_request"`
- **AND** el mensaje no ecoa el valor recibido ni el nombre del campo interno de Pydantic

#### Scenario: S2.4 — Dos sillones de RX conviven; RN-AG-06 se evalúa por turno

- **WHEN** un `owner` crea un segundo sillón con `tipo = "rx"` y ya existe otro activo del mismo tipo
- **THEN** responde `201`: la restricción de RN-AG-06 es sobre turnos solapados, no sobre la cantidad
  de sillones de RX
- **AND** queda anotado que la validación de RN-AG-06 se activa cuando exista `appointment` (C-07)

#### Scenario: S2.5 — El mismo nombre en otro tenant no colisiona

- **WHEN** el tenant A ya tiene un sillón llamado `"Sillón 1"` y un `owner` del tenant B crea otro con
  ese nombre
- **THEN** responde `201` y cada tenant ve solo su fila

### Requirement: Actualización y baja lógica de sillón

`PATCH /api/v1/clinic/chairs/{id}` MUST exigir `chair.update` y permitir cambiar `nombre`, `tipo`,
`ubicacion`, `equipamiento` y `activo`. `DELETE /api/v1/clinic/chairs/{id}` MUST exigir `chair.delete`
y MUST ser una **baja lógica** (`activo = false`): la fila y su historial se conservan (RN-EX-03) y
repetir la baja MUST ser idempotente. Un `id` de otro tenant MUST responder `404 chair_not_found`,
indistinguible de uno inexistente.

#### Scenario: S3.1 — El PATCH actualiza los atributos editables

- **WHEN** un `owner` cambia `ubicacion` y `equipamiento` de un sillón propio
- **THEN** responde `200` con los valores nuevos y el `id` sin cambios

#### Scenario: S3.2 — La baja es lógica y conserva la fila

- **WHEN** un `owner` invoca `DELETE /api/v1/clinic/chairs/{id}` sobre un sillón activo
- **THEN** responde `204`
- **AND** la fila sigue existiendo con `activo: false` en la siguiente lectura del tenant

#### Scenario: S3.3 — Repetir la baja es idempotente

- **WHEN** el `owner` repite el `DELETE` sobre un sillón ya inactivo
- **THEN** responde `204` y no hay error ni cambio de estado adicional

#### Scenario: S3.4 — Sin chair.delete no hay baja

- **WHEN** una sesión `clinical_admin` (tiene `chair.update`, no `chair.delete`) invoca el `DELETE`
- **THEN** responde `403` con `code = "forbidden"` y el sillón sigue activo

#### Scenario: S3.5 — El sillón de otro tenant es indistinguible de uno inexistente

- **WHEN** un `owner` del tenant A invoca `PATCH` y `DELETE` con el `id` de un sillón del tenant B
- **THEN** ambas respuestas son `404` con `code = "chair_not_found"`, igual que con un `id` aleatorio
- **AND** el sillón del tenant B no cambia

### Requirement: Lectura de los profesionales del tenant

`GET /api/v1/clinic/professionals` MUST exigir `professional.read` y devolver `id`, `user_id`
(nullable), `nombre`, `apellido`, `matricula`, `especialidad` (`id` y `nombre`),
`duracion_default_min`, `porcentaje_liquidacion`, `color_agenda` y `activo`. MUST incluir los
profesionales inactivos, MUST NOT exponer `tenant_id` y el orden MUST ser estable (por `apellido` y
`nombre`).

#### Scenario: S4.1 — La lista trae matrícula, especialidad y duración

- **WHEN** un `front_desk` invoca `GET /api/v1/clinic/professionals`
- **THEN** responde `200` con cada profesional incluyendo `matricula`, `especialidad.nombre` y
  `duracion_default_min`
- **AND** no aparece `tenant_id` ni datos de otro tenant

#### Scenario: S4.2 — Sin professional.read la lista se rechaza

- **WHEN** una sesión con un rol sin `professional.read` invoca el endpoint
- **THEN** responde `403` con `code = "forbidden"`

#### Scenario: S4.3 — Un profesional externo sin login aparece con user_id nulo

- **WHEN** el tenant tiene un profesional cargado sin `user_id` (externo)
- **THEN** la lista lo devuelve con `user_id: null` y su matrícula, sin error

### Requirement: Alta de profesional con matrícula única

`POST /api/v1/clinic/professionals` MUST exigir `professional.create` y aceptar `nombre`, `apellido`,
`matricula` (1–32), `especialidad_id`, `user_id` (opcional), `duracion_default_min` (5–480),
`porcentaje_liquidacion` (0–100) y `color_agenda` (`#RRGGBB`). MUST rechazar una `matricula` repetida
en el tenant con `409 professional_matricula_taken` (RN-TEN-04, índice único `(tenant_id, matricula)`).
`especialidad_id` MUST existir en el catálogo visible (global con `tenant_id NULL` o del propio
tenant): si no, `404 specialty_not_found`. Un `user_id` que no tenga membership activa en el tenant
MUST rechazarse con `422 user_not_member`.

#### Scenario: S5.1 — Alta completa de un profesional

- **WHEN** un `owner` envía `{"nombre": "Paula", "apellido": "Pérez", "matricula": "MP-1234",
  "especialidad_id": "<uuid del catálogo>", "duracion_default_min": 30,
  "porcentaje_liquidacion": 40, "color_agenda": "#2563EB"}`
- **THEN** responde `201` con `activo: true` y los valores enviados
- **AND** una lectura posterior devuelve la especialidad resuelta con su nombre

#### Scenario: S5.2 — Matrícula repetida en el tenant

- **WHEN** se intenta dar de alta otro profesional con la misma `matricula` en el mismo tenant
- **THEN** responde `409` con `code = "professional_matricula_taken"` y no se crea la fila

#### Scenario: S5.3 — Rangos inválidos de duración y porcentaje

- **WHEN** se envía `duracion_default_min = 0` o `porcentaje_liquidacion = 120`
- **THEN** responde `422` con `code = "invalid_request"` antes de escribir cualquier fila

#### Scenario: S5.4 — Especialidad inexistente o de otro tenant

- **WHEN** se envía un `especialidad_id` que no existe o pertenece a otro tenant
- **THEN** responde `404` con `code = "specialty_not_found"`, sin distinguir entre ambos casos

#### Scenario: S5.5 — Un user_id sin membership en el tenant se rechaza

- **WHEN** se envía el `user_id` de una persona que no tiene membership activa en el tenant
- **THEN** responde `422` con `code = "user_not_member"` y no se crea el profesional

#### Scenario: S5.6 — La misma matrícula en otro tenant no colisiona

- **WHEN** el tenant A ya tiene `MP-1234` y el tenant B da de alta otro con la misma matrícula
- **THEN** responde `201` en el tenant B: la unicidad es por tenant, no global

### Requirement: Desactivación de profesional

`PATCH /api/v1/clinic/professionals/{id}` MUST exigir `professional.update` y permitir cambiar los
datos del profesional y `activo`. No existe `professional.delete` en la matriz, así que la baja se hace
con `activo = false` y MUST conservar la fila y sus reglas de disponibilidad (RN-EX-03). Un `id` de
otro tenant MUST responder `404 professional_not_found`.

#### Scenario: S6.1 — Desactivar conserva la fila y sus datos

- **WHEN** un `owner` cambia `activo` a `false` en un profesional propio
- **THEN** responde `200` con `activo: false`
- **AND** la fila sigue apareciendo en la lista del tenant con matrícula y especialidad intactas

#### Scenario: S6.2 — Sin professional.update no hay modificación

- **WHEN** una sesión `front_desk` (solo `professional.read`) intenta el `PATCH`
- **THEN** responde `403` con `code = "forbidden"` y la fila no cambia

#### Scenario: S6.3 — Desactivar no borra la disponibilidad cargada

- **WHEN** el profesional tenía dos reglas de disponibilidad y se lo desactiva
- **THEN** `GET /api/v1/clinic/availability` sigue devolviendo sus dos reglas
- **AND** la agenda futura decidirá no ofrecerlas (regla de C-07, no de este change)

#### Scenario: S6.4 — El profesional de otro tenant es indistinguible de uno inexistente

- **WHEN** un `owner` del tenant A hace `PATCH` con el `id` de un profesional del tenant B
- **AND** repite el `PATCH` con un `id` que no existe en ningún tenant
- **THEN** ambas respuestas son `404` con el mismo cuerpo (`code = "professional_not_found"`)
- **AND** la fila del tenant B no cambia

### Requirement: Reglas de disponibilidad con slots y buffers

`POST /api/v1/clinic/availability` MUST exigir `professional.update` y aceptar `professional_id`
(opcional; `null` = toda la clínica), `chair_id` (opcional), `dia_semana` (0–6), `hora_inicio`,
`hora_fin`, `slot_min` (>0), `buffer_previo_min` y `buffer_posterior_min` (≥0), `fecha_desde`,
`fecha_hasta` (opcional) y `tipo_practica` (opcional). MUST rechazar con `422 invalid_request`:
`hora_fin <= hora_inicio`, `fecha_hasta < fecha_desde`, buffers negativos, `slot_min <= 0` y una
ventana que no sea múltiplo exacto de `slot_min` (RN-AG-03: los slots cierran exactamente en la
ventana). MUST rechazar con `409 availability_overlap` una regla que se solape en día y rango de fechas
con otra del mismo alcance (`professional_id` y `chair_id`). `GET` MUST exigir `professional.read` y
`PATCH` MUST exigir `professional.update`.

#### Scenario: S7.1 — Alta de una regla completa

- **WHEN** un `owner` envía `{"professional_id": "<uuid>", "dia_semana": 1, "hora_inicio": "09:00",
  "hora_fin": "12:00", "slot_min": 30, "buffer_previo_min": 10, "buffer_posterior_min": 15,
  "fecha_desde": "2026-11-16"}`
- **THEN** responde `201` y una lectura devuelve los buffers y el slot persistidos sin cambios

#### Scenario: S7.2 — Ventana invertida o nula

- **WHEN** se envía `hora_inicio = "12:00"` y `hora_fin = "12:00"` (o una `hora_fin` anterior)
- **THEN** responde `422` con `code = "invalid_request"` y no se crea la regla

#### Scenario: S7.3 — La ventana no cierra en slots completos

- **WHEN** se envía una ventana de 09:00 a 10:10 con `slot_min = 30`
- **THEN** responde `422` con `code = "invalid_request"`
- **AND** el mensaje explica que la ventana debe ser múltiplo del slot

#### Scenario: S7.4 — Buffers negativos o slot no positivo

- **WHEN** se envía `buffer_posterior_min = -5` o `slot_min = 0`
- **THEN** responde `422` con `code = "invalid_request"`

#### Scenario: S7.5 — Dos reglas del mismo alcance no pueden solaparse

- **WHEN** existe una regla del profesional P el lunes de 09:00 a 12:00 y se intenta crear otra del
  mismo profesional el lunes de 11:00 a 14:00 con fechas que se intersectan
- **THEN** responde `409` con `code = "availability_overlap"`
- **AND** la primera regla queda intacta

#### Scenario: S7.6 — Regla sin professional_id aplica a toda la clínica

- **WHEN** un `owner` crea una regla con `professional_id: null`
- **THEN** responde `201` y la lista la muestra sin profesional asociado

#### Scenario: S7.7 — Profesional o sillón de otro tenant

- **WHEN** se envía el `professional_id` o el `chair_id` de otro tenant
- **THEN** responde `404` con `code = "professional_not_found"` (o `chair_not_found`)
- **AND** no se crea la regla

#### Scenario: S7.8 — fecha_hasta anterior a fecha_desde

- **WHEN** se envía `fecha_desde = "2026-12-01"` y `fecha_hasta = "2026-11-01"`
- **THEN** responde `422` con `code = "invalid_request"`

### Requirement: Aislamiento cross-tenant de la configuración (RN-TEN-02)

Las tres tablas nuevas MUST tener `tenant_id NOT NULL`, RLS `ENABLE` + `FORCE` y política
`tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid` para `USING` y `WITH
CHECK`, con el rol de aplicación `odontologia_app` (`NOBYPASSRLS`). El `tenant_id` MUST salir del
token y MUST NOT aceptarse en el body (`extra = "forbid"` → `422 invalid_request`); en query o header
MUST ignorarse. El gate de merge MUST incluir el test cross-tenant.

#### Scenario: S8.1 — El tenant A no ve la configuración del tenant B

- **WHEN** la app corre con el contexto del tenant A y consulta sillones, profesionales y reglas
- **THEN** obtiene solo filas de A, y un `SELECT` directo de las filas de B devuelve cero

#### Scenario: S8.2 — Modificar o borrar un id ajeno afecta cero filas

- **WHEN** la app, con contexto de A, ejecuta `UPDATE` y `DELETE` sobre el `id` de un sillón de B
- **THEN** afecta `0` filas y el endpoint responde `404`

#### Scenario: S8.3 — Sin contexto de tenant el predicado es NULL

- **WHEN** la app consulta las tres tablas sin `app.current_tenant` fijado
- **THEN** devuelve cero filas (fail-closed) y un `INSERT` sin `tenant_id` válido es rechazado

#### Scenario: S8.4 — tenant_id en el body se rechaza con el contrato único

- **WHEN** un `owner` agrega `"tenant_id"` al body de un alta
- **THEN** responde `422` con `code = "invalid_request"` y no se crea la fila
- **AND** el `tenant_id` puesto en query o en un header se ignora y la operación sigue con el de la
  sesión

### Requirement: Pantalla de configuración de la clínica

La ruta `/clinica` MUST listar sillones, profesionales y reglas de disponibilidad, y MUST decidir su
visibilidad **solo por permiso** (`chair.read`, `chair.create`, `chair.delete`, `professional.create`,
`professional.update`), nunca comparando `session.roles`. El enlace de la Home MUST aparecer solo con
`chair.read`. Un `403` de la API MUST mostrarse como acceso denegado y un error de negocio MUST mostrar
su `code`.

#### Scenario: S9.1 — Con chair.read la pantalla lista los tres recursos

- **WHEN** una sesión con `chair.read` abre `/clinica`
- **THEN** ve la tabla de sillones con tipo y estado, la de profesionales con matrícula y las reglas de
  disponibilidad
- **AND** el enlace "Clínica" aparece en la Home

#### Scenario: S9.2 — Sin chair.read no hay enlace ni pantalla

- **WHEN** una sesión sin `chair.read` abre `/clinica`
- **THEN** la Home no muestra el enlace y la ruta muestra "No tenés permiso para ver esta sección."

#### Scenario: S9.3 — La UI no ofrece acciones sin permiso y la API las rechaza igual

- **WHEN** una sesión con `chair.read` y `clinical_admin` (sin `chair.delete`) abre `/clinica`
- **THEN** ve **Nuevo sillón** y **Guardar** pero no el botón de baja
- **AND** si fuerza `DELETE /api/v1/clinic/chairs/{id}`, la API responde `403 forbidden`

### Requirement: Catálogo visible de especialidades

`GET /api/v1/clinic/specialties` MUST exigir `professional.read` y devolver las especialidades
visibles para el tenant: las globales (`tenant_id IS NULL`, sembradas por C-02) y las propias.
MUST NOT exponer especialidades de otro tenant ni el `tenant_id`, y el orden MUST ser estable por
`nombre`. Es el catálogo con el que el alta de profesional resuelve `especialidad_id`; la `specialty`
no tiene RLS, así que la visibilidad se resuelve en la consulta (`tenant_id IS NULL OR tenant_id =
:tid`) y no en una política.

#### Scenario: S10.1 — El catálogo trae las globales y las propias de la clínica

- **WHEN** una sesión `professional` invoca `GET /api/v1/clinic/specialties` en un tenant que tiene una
  especialidad propia y el seed global de C-02
- **THEN** responde `200` con las dos entradas (`id`, `nombre`), ordenadas por `nombre`
- **AND** el JSON no contiene `tenant_id` y dos llamadas consecutivas devuelven el mismo orden

#### Scenario: S10.2 — Sin professional.read el catálogo no existe para el backend

- **WHEN** una sesión sin `professional.read` invoca `GET /api/v1/clinic/specialties`
- **THEN** responde `403` con `code = "forbidden"`

#### Scenario: S10.3 — Una especialidad de otro tenant no se lista ni se puede usar

- **WHEN** el tenant B tiene una especialidad propia y el tenant A pide el catálogo
- **THEN** la especialidad de B no aparece en la respuesta de A
- **AND** usarla en `POST /professionals` responde `404 specialty_not_found`, sin fila creada
