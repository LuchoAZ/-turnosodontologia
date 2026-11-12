# clinic/patients Specification

## Purpose
Define la ficha demográfica del paciente de la clínica: alta, lectura, actualización, búsqueda y
detección de duplicados, con un número de historia clínica secuencial por tenant que nunca se recicla
(RN-CLI-01). Es la entidad que la agenda referencia al reservar un turno y la que separa, por permiso,
los datos administrativos que administra recepción de la historia clínica que solo leen los roles
clínicos (RN-CMP-04). Todo opera bajo RLS con el `tenant_id` resuelto del token (RN-TEN-02, RN-TEN-03).

## Requirements

### Requirement: Listado de pacientes del tenant

`GET /api/v1/patients` MUST exigir `patient.read` y devolver solo los pacientes del tenant de la
sesión, ordenados por `apellido`, `nombre` y `numero_historia_clinica`. Por defecto MUST excluir los
pacientes con `deleted_at` no nulo y MUST incluirlos con `incluir_inactivos=true`. La respuesta MUST
ser `{"patients": [...], "total": N}` y cada paciente MUST NOT exponer `tenant_id`, `deleted_at` ni
campos clínicos. `limit` MUST estar entre 1 y 100 (por defecto 20) y `offset` MUST ser mayor o igual a
0 (por defecto 0).

#### Scenario: S1.1 — El owner ve solo los pacientes de su tenant, ordenados y sin datos internos

- **WHEN** una sesión `owner` del tenant A invoca `GET /api/v1/patients` con dos pacientes activos y uno
  con `deleted_at`
- **THEN** responde `200` con los dos activos ordenados por apellido y nombre, y `total = 2`
- **AND** ningún ítem contiene `tenant_id`, `deleted_at`, `alergias` ni `alerta_clinica`

#### Scenario: S1.2 — Sin patient.read la lista no existe para el backend

- **WHEN** una sesión con un rol sin `patient.read` (por ejemplo `accountant`) invoca
  `GET /api/v1/patients`
- **THEN** responde `403` con `code = "forbidden"`
- **AND** el cuerpo no contiene nombres, DNI ni identificadores de pacientes

#### Scenario: S1.3 — Un tenant sin pacientes devuelve una lista vacía con total cero

- **WHEN** una sesión `owner` de un tenant recién creado invoca `GET /api/v1/patients`
- **THEN** responde `200` con `{"patients": [], "total": 0}` y no `404`

#### Scenario: S1.4 — Paginación y límites fuera de rango

- **WHEN** se invoca `GET /api/v1/patients?limit=1&offset=1` con tres pacientes
- **THEN** responde `200` con un único paciente y `total = 3`
- **AND** `limit=0`, `limit=101` u `offset=-1` responden `422` con `code = "invalid_request"`

#### Scenario: S1.5 — Un paciente de otro tenant nunca aparece

- **WHEN** el tenant A tiene un paciente y el tenant B tiene otro con el mismo DNI y el mismo nombre
- **THEN** la lista y el `total` del tenant A solo cuentan el suyo
- **AND** ninguna respuesta del tenant A contiene el `id` ni el `numero_historia_clinica` del tenant B

#### Scenario: S1.6 — incluir_inactivos trae las filas dadas de baja sin exponer deleted_at

- **WHEN** el tenant tiene un paciente activo y otro con `deleted_at` y se invoca
  `GET /api/v1/patients?incluir_inactivos=true`
- **THEN** responde `200` con los dos pacientes y `total = 2`
- **AND** sin `incluir_inactivos` el mismo listado devuelve `total = 1`
- **AND** el ítem del paciente dado de baja no expone `deleted_at` igual que el resto

### Requirement: Búsqueda de pacientes por nombre, DNI o teléfono

`GET /api/v1/patients?q=...` MUST exigir `patient.read` y buscar en el tenant de la sesión por
`apellido`/`nombre` (insensible a mayúsculas y acentos), por DNI exacto y por fragmento de teléfono.
`q` MUST recortarse; si queda vacío MUST comportarse como un listado sin filtro y si supera 60
caracteres MUST responder `422 invalid_request`. Los comodines de SQL (`%`, `_`) MUST tratarse como
texto literal, no como patrón.

#### Scenario: S2.1 — La búsqueda ignora mayúsculas y acentos

- **WHEN** existe el paciente `Pérez, Ana` y se invoca `GET /api/v1/patients?q=perez`
- **THEN** responde `200` con ese paciente y `total = 1`
- **AND** `q=PEREZ` y `q=Pérez` devuelven el mismo resultado

#### Scenario: S2.2 — La búsqueda también resuelve DNI y teléfono

- **WHEN** se invoca `?q=` con el DNI completo de un paciente y luego con los últimos dígitos de su
  teléfono
- **THEN** ambas búsquedas devuelven ese paciente y ningún otro

#### Scenario: S2.3 — Los comodines se escapan y no hay inyección de patrón

- **WHEN** se invoca `GET /api/v1/patients?q=%25` (un `%` literal), `q=_` (un guion bajo literal),
  `q=\` (una barra invertida literal) o `q=' OR 1=1 --`
- **THEN** todas responden `200` (con coincidencias literales o `total = 0`), sin error `500`
- **AND** no devuelve todos los pacientes por interpretar `%` o `_` como comodines
- **AND** el `\` no rompe el `LIKE ... ESCAPE '\'` ni genera un `invalid_request`

#### Scenario: S2.4 — La búsqueda no cruza tenants

- **WHEN** el tenant B tiene un `Pérez, Ana` y el tenant A busca `?q=perez`
- **THEN** el tenant A obtiene `total = 0` y nunca el `id` del paciente del tenant B

#### Scenario: S2.5 — Un q demasiado largo se rechaza antes de consultar

- **WHEN** se invoca `GET /api/v1/patients?q=` con 61 caracteres
- **THEN** responde `422` con `code = "invalid_request"`
- **AND** no se ejecuta ninguna consulta sobre `patient`

#### Scenario: S2.6 — Un q en blanco equivale a listar sin filtro

- **WHEN** se invoca `GET /api/v1/patients?q=` vacío y luego `?q=%20%20` (solo espacios)
- **THEN** ambas respuestas son `200` con el mismo `total` que el listado sin `q`
- **AND** el `q` se recorta antes de usarse y no se envía un patrón `%%` a la base

### Requirement: Alta de paciente con número de historia clínica

`POST /api/v1/patients` MUST exigir `patient.create` y crear la ficha con `nombre`, `apellido` y
`telefono` obligatorios; `dni`, `fecha_nacimiento`, `sexo`, `email` y `domicilio` son opcionales. MUST
generar el `numero_historia_clinica` en la misma transacción y responder `201` con la ficha creada. El
`tenant_id` MUST salir del token y un `tenant_id`, `numero_historia_clinica`, `deleted_at`, `alergias`
o `alerta_clinica` en el cuerpo MUST responder `422 invalid_request` sin crear fila (DTO con
`extra="forbid"`). `nombre` y `apellido` MUST recortarse y rechazarse si quedan vacíos.

#### Scenario: S3.1 — Alta completa devuelve la ficha y persiste la fila

- **WHEN** una sesión `owner` hace `POST /api/v1/patients` con nombre, apellido, teléfono, DNI y email
  válidos
- **THEN** responde `201` con la ficha, su `id` y un `numero_historia_clinica` de seis dígitos
- **AND** la fila existe en la base con `tenant_id` del token y sin `tenant_id` en la respuesta

#### Scenario: S3.2 — Sin patient.create no se crea nada

- **WHEN** una sesión `accountant` (sin `patient.create`) intenta el alta
- **THEN** responde `403` con `code = "forbidden"` y la tabla `patient` no gana filas

#### Scenario: S3.3 — Campos reservados en el cuerpo se rechazan

- **WHEN** el cuerpo incluye `tenant_id`, `numero_historia_clinica`, `deleted_at`, `alergias` o
  `alerta_clinica`
- **THEN** responde `422` con `code = "invalid_request"` y no se crea la fila

#### Scenario: S3.4 — Datos inválidos no generan historia clínica

- **WHEN** el cuerpo omite `telefono`, trae un DNI no numérico, un email inválido o un `sexo` fuera del
  enum
- **THEN** responde `422` con `code = "invalid_request"`
- **AND** el `patient_counter` del tenant no avanza

#### Scenario: S3.5 — Recepción da de alta la ficha (US-030)

- **WHEN** una sesión `front_desk` crea un paciente con datos demográficos
- **THEN** responde `201` y el paciente aparece en la lista de recepción y de dirección clínica
- **AND** la misma sesión sigue recibiendo `403` en `GET /api/v1/clinical/patients` (RN-CMP-04)

#### Scenario: S3.6 — Espacios sobrantes se recortan y un nombre vacío se rechaza

- **WHEN** el cuerpo trae `nombre = "  Ana  "` y `apellido = "   "`
- **THEN** responde `422` por el apellido vacío y no crea la fila
- **AND** con `apellido = "  Pérez "` se persiste `Pérez` sin espacios en los extremos

### Requirement: Número de historia clínica secuencial y no reciclable

El `numero_historia_clinica` MUST ser único por tenant y MUST asignarse desde un contador por tenant
que solo avanza. MUST NOT calcularse como `MAX(numero) + 1`: dar de baja al paciente con el número más
alto MUST NOT liberar ese número (RN-CLI-01). Dos altas concurrentes del mismo tenant MUST obtener
números distintos sin violar la unicidad, y dos tenants MUST tener secuencias independientes. Un alta
que termina en error MUST NOT consumir un número: el incremento del contador y el `INSERT` del paciente
MUST confirmarse juntos o revertirse juntos, sin dejar huecos en la secuencia. El formato MUST ser
`f"{secuencia:06d}"` y, superado `999999`, MUST crecer a siete dígitos sin error.

#### Scenario: S4.1 — Tres altas consecutivas dan 000001, 000002 y 000003

- **WHEN** un tenant crea tres pacientes seguidos
- **THEN** los números son `000001`, `000002` y `000003`, en ese orden
- **AND** `GET /api/v1/patients` los devuelve ordenados por apellido y nombre, no por número

#### Scenario: S4.2 — Cada tenant arranca su propia secuencia

- **WHEN** el tenant A crea un paciente y el tenant B crea otro
- **THEN** ambos reciben `000001` y la unicidad se evalúa por `(tenant_id, numero_historia_clinica)`

#### Scenario: S4.3 — Dar de baja al último no recicla su número

- **WHEN** el paciente `000003` se marca con `deleted_at` y se crea otro paciente
- **THEN** el nuevo recibe `000004`, no `000003`
- **AND** el paciente dado de baja conserva su `000003` en la base

#### Scenario: S4.4 — Dos altas concurrentes no colisionan

- **WHEN** dos sesiones del mismo tenant crean un paciente en paralelo
- **THEN** ambas reciben `201` con números distintos y consecutivos
- **AND** no se produce una violación de `(tenant_id, numero_historia_clinica)`

#### Scenario: S4.5 — Un alta fallida no deja hueco en la secuencia

- **WHEN** dos sesiones del mismo tenant crean en paralelo un paciente con el **mismo DNI**
- **THEN** una recibe `201` y la otra `409 patient_dni_duplicado`
- **AND** la secuencia no salta ningún número: el siguiente alta recibe el número inmediatamente
  posterior al `201`, como si la fallida nunca hubiera reservado uno

#### Scenario: S4.6 — El formato crece por encima de 999999 sin romperse

- **WHEN** el contador del tenant está en `999999` y se crea otro paciente
- **THEN** el nuevo recibe `1000000`, sin error y sin truncarse
- **AND** la columna `varchar(20)` lo admite y la unicidad por tenant se mantiene

### Requirement: Duplicado por DNI

El alta MUST rechazar un DNI ya registrado en el mismo tenant con `409 patient_dni_duplicado`, sin
crear fila y devolviendo el `id` y el `numero_historia_clinica` del paciente existente. El índice único
MUST ser parcial (`WHERE dni IS NOT NULL`), de modo que varios pacientes sin DNI convivan. El mismo DNI
en otro tenant MUST NOT colisionar, y `confirmar_duplicado` MUST NOT habilitar un DNI repetido. Si dos
altas con el mismo DNI corren en paralelo, la que pierde la carrera MUST recibir `409
patient_dni_duplicado` (nunca `500`) y MUST NOT consumir un número de historia clínica. El DNI de un
paciente con `deleted_at` no nulo MUST seguir bloqueando: el índice no filtra por baja lógica, así que un
DNI nunca se recicla.

#### Scenario: S5.1 — El mismo DNI en el tenant responde 409 con el existente

- **WHEN** se intenta crear un paciente con un DNI que ya tiene otro paciente del mismo tenant
- **THEN** responde `409` con `code = "patient_dni_duplicado"` y el `id` del existente
- **AND** la tabla no gana filas y el contador no avanza

#### Scenario: S5.2 — confirmar_duplicado no vence la regla del DNI

- **WHEN** el mismo alta repetida se envía con `confirmar_duplicado = true`
- **THEN** sigue respondiendo `409 patient_dni_duplicado` y no crea fila

#### Scenario: S5.3 — El mismo DNI en otro tenant es válido

- **WHEN** el tenant B crea un paciente con un DNI que ya existe en el tenant A
- **THEN** responde `201`
- **AND** el número de HCE del tenant B es independiente del de A

#### Scenario: S5.4 — Varios pacientes sin DNI conviven

- **WHEN** el tenant crea dos pacientes con `dni = null`
- **THEN** ambos reciben `201` con números distintos
- **AND** el índice parcial no los trata como duplicados

#### Scenario: S5.5 — La carrera chequeo→INSERT se traduce en 409, no en 500

- **WHEN** dos sesiones del mismo tenant pasan el chequeo de DNI a la vez e insertan el mismo DNI
- **THEN** la que choca con el índice único recibe `409 patient_dni_duplicado`
- **AND** la respuesta no es `500`, no deja filas duplicadas y su transacción revierte el contador

#### Scenario: S5.6 — El DNI de un paciente dado de baja sigue bloqueando

- **WHEN** un paciente con DNI `30111222` tiene `deleted_at` y se intenta crear otro con el mismo DNI
- **THEN** responde `409 patient_dni_duplicado` con el `id` del paciente dado de baja
- **AND** el DNI no se recicla ni aparece un segundo paciente con ese documento en el tenant

### Requirement: Posible duplicado por nombre o teléfono

Antes de crear, el sistema MUST buscar coincidencias **entre los pacientes activos del tenant**
(`deleted_at IS NULL`) por `apellido` y `nombre` normalizados (mayúsculas, acentos y espacios
colapsados) o por teléfono normalizado. Un homónimo dado de baja MUST NOT disparar la confirmación. Si
hay coincidencias y `confirmar_duplicado` es `false`, MUST responder `409 patient_posible_duplicado` con
`candidatos: [{id, numero_historia_clinica, nombre, apellido, dni, telefono}]` —como máximo **5**
candidatos— y sin crear fila. Con `confirmar_duplicado = true` MUST crear la ficha. La detección MUST
limitarse al tenant de la sesión.

#### Scenario: S6.1 — Nombre y apellido equivalentes disparan la confirmación

- **WHEN** existe `Pérez, Ana` y se intenta crear `PEREZ, ANA` con otro teléfono
- **THEN** responde `409` con `code = "patient_posible_duplicado"` y un candidato `Pérez, Ana`
- **AND** la ficha no se crea

#### Scenario: S6.2 — El teléfono repetido también dispara la confirmación

- **WHEN** se intenta crear un paciente con el mismo teléfono normalizado que otro y distinto nombre
- **THEN** responde `409 patient_posible_duplicado` con el candidato por teléfono

#### Scenario: S6.3 — Confirmar el duplicado crea la segunda ficha

- **WHEN** el mismo alta se repite con `confirmar_duplicado = true`
- **THEN** responde `201` y quedan dos pacientes con números de HCE distintos
- **AND** la respuesta no incluye el campo `confirmar_duplicado`

#### Scenario: S6.4 — Sin coincidencias el alta es directa

- **WHEN** se crea un paciente con nombre, apellido, DNI y teléfono que no existen en el tenant
- **THEN** responde `201` con la ficha y su `numero_historia_clinica` y no se pide confirmación

#### Scenario: S6.5 — Un homónimo de otro tenant no pide confirmación

- **WHEN** el tenant B tiene `Pérez, Ana` y el tenant A crea la misma persona
- **THEN** responde `201` sin `409`, porque la búsqueda de candidatos no cruza tenants

#### Scenario: S6.6 — Un homónimo dado de baja no dispara la confirmación

- **WHEN** el único `Pérez, Ana` del tenant tiene `deleted_at` y se crea otra `Pérez, Ana`
- **THEN** responde `201` sin `409 patient_posible_duplicado`
- **AND** el dedupe blando solo considera pacientes activos

#### Scenario: S6.7 — El 409 acota los candidatos a cinco aunque haya más coincidencias

- **WHEN** hay siete pacientes activos que coinciden por teléfono y se intenta crear otro con ese
  teléfono
- **THEN** responde `409 patient_posible_duplicado` con `len(candidatos) == 5`
- **AND** el `code` es el mismo que con una sola coincidencia y no se crea fila

### Requirement: Lectura de un paciente por id

`GET /api/v1/patients/{id}` MUST exigir `patient.read` y devolver la ficha del tenant de la sesión con
los mismos campos que el listado. Un `id` de otro tenant y un `id` inexistente MUST responder `404
patient_not_found` con cuerpos idénticos, sin distinguir si la fila existe en otro tenant.

#### Scenario: S7.1 — La ficha propia se lee completa y sin datos internos

- **WHEN** una sesión `owner` pide el `id` de un paciente de su tenant
- **THEN** responde `200` con número de HCE, datos demográficos y `activo`
- **AND** el JSON no contiene `tenant_id`, `deleted_at`, `alergias` ni `alerta_clinica`

#### Scenario: S7.2 — Un id ajeno es indistinguible de uno inexistente

- **WHEN** el tenant A pide el `id` de un paciente del tenant B y luego un `id` aleatorio
- **THEN** ambas respuestas son `404` con el mismo `code = "patient_not_found"` y el mismo cuerpo

#### Scenario: S7.3 — Sin patient.read no hay lectura

- **WHEN** una sesión `external_lab` (sin `patient.read`) pide un paciente
- **THEN** responde `403` con `code = "forbidden"` y ningún campo de la ficha

### Requirement: Actualización de la ficha del paciente

`PATCH /api/v1/patients/{id}` MUST exigir `patient.update` y permitir cambiar solo los campos
demográficos (`nombre`, `apellido`, `dni`, `fecha_nacimiento`, `sexo`, `telefono`, `email`,
`domicilio`). MUST rechazar con `422 invalid_request` cualquier intento de cambiar
`numero_historia_clinica`, `tenant_id`, `deleted_at`, `alergias` o `alerta_clinica`. Un DNI que ya
tiene otro paciente del tenant MUST responder `409 patient_dni_duplicado` sin modificar la fila, y un
`id` ajeno o inexistente MUST responder `404 patient_not_found` indistinguible. Al cambiar `nombre` o
`apellido` MUST recalcularse los valores normalizados de búsqueda.

#### Scenario: S8.1 — Se actualizan los datos de contacto

- **WHEN** una sesión `front_desk` cambia `telefono` y `email` de un paciente propio
- **THEN** responde `200` con los nuevos valores y la fila queda persistida

#### Scenario: S8.2 — Los campos reservados no se pueden modificar

- **WHEN** el cuerpo del `PATCH` incluye `numero_historia_clinica`, `tenant_id`, `deleted_at`,
  `alergias` o `alerta_clinica`
- **THEN** responde `422` con `code = "invalid_request"` y la fila no cambia

#### Scenario: S8.3 — Cambiar el DNI a uno ya usado responde 409

- **WHEN** se actualiza el DNI de un paciente al DNI de otro del mismo tenant
- **THEN** responde `409 patient_dni_duplicado` y el DNI original se conserva

#### Scenario: S8.4 — Un id ajeno responde 404 indistinguible

- **WHEN** se intenta actualizar un paciente del tenant B desde el tenant A
- **THEN** responde `404 patient_not_found`, igual que con un `id` inexistente, y no cambia la fila

#### Scenario: S8.5 — Cambiar el nombre actualiza la búsqueda

- **WHEN** se cambia `apellido` de `Pérez` a `Gómez` y luego se busca `?q=gomez`
- **THEN** el paciente aparece con el nuevo apellido
- **AND** `?q=perez` ya no lo devuelve

#### Scenario: S8.6 — Sin patient.update no hay modificación

- **WHEN** una sesión `professional` (solo `patient.read`) intenta el `PATCH`
- **THEN** responde `403` con `code = "forbidden"` y la fila no cambia

### Requirement: Frontera clínica de la ficha

Ninguna respuesta de `/api/v1/patients` MUST incluir `alergias`, `alerta_clinica` ni datos de historia
clínica. Los DTO de entrada MUST rechazar esos campos con `422` (`extra="forbid"`), aunque la tabla los
tenga. Recepción MUST poder administrar la ficha demográfica sin obtener `clinical_record.read`, y la
sonda `GET /api/v1/clinical/patients` MUST seguir respondiendo `403` a recepción (RN-CMP-04).

#### Scenario: S9.1 — El contrato de la ficha no expone campos clínicos

- **WHEN** se recorren las respuestas de listar, leer, crear y actualizar un paciente
- **THEN** ninguna contiene las claves `alergias`, `alerta_clinica`, `clinical_record` ni
  `historia_clinica`

#### Scenario: S9.2 — Recepción administra la ficha y sigue fuera de la historia clínica

- **WHEN** una sesión `front_desk` crea, lee y actualiza un paciente
- **THEN** las tres operaciones responden `2xx`
- **AND** `GET /api/v1/clinical/patients` con la misma sesión responde `403 forbidden`

#### Scenario: S9.3 — Enviar un campo clínico es un error de contrato

- **WHEN** el alta o la actualización incluye `alergias` o `alerta_clinica`
- **THEN** responde `422 invalid_request` y la columna permanece en su valor por defecto

### Requirement: Permisos de pacientes en la matriz RBAC

La matriz de `knowledge-base/03_actores_y_roles.md` y `backend/app/domain/rbac/matrix.py` MUST incluir
la fila `patient` con las acciones `create`, `read`, `update` y `delete`. `owner` MUST tener las cuatro;
`clinical_admin` y `front_desk`, `create`/`read`/`update`; `professional`, `assistant` y `billing`,
`read`; `patient`, `external_lab` y `accountant`, ninguna. El catálogo MUST pasar a 19 recursos y 61
permisos, y `RESOURCE_ACTIONS["patient"]` MUST declarar las cuatro acciones.

#### Scenario: S10.1 — Cada rol recibe exactamente las acciones de su celda

- **WHEN** se resuelven los permisos de cada uno de los 9 roles
- **THEN** `owner` tiene `patient.create/read/update/delete`, `front_desk` no tiene `patient.delete` y
  `external_lab` no tiene ningún permiso `patient.*`
- **AND** no hay permisos `patient.*` fuera del catálogo

#### Scenario: S10.2 — El catálogo crece de forma coherente

- **WHEN** se inspeccionan `DOMAIN_RESOURCES`, `RESOURCE_ACTIONS` y `Permission`
- **THEN** hay 19 recursos, `RESOURCE_ACTIONS["patient"]` contiene las cuatro acciones y el enum tiene
  61 permisos
- **AND** `platform-rbac` valida con su requisito modificado

#### Scenario: S10.3 — La resolución sigue fallando cerrado

- **WHEN** se resuelven permisos de un rol inexistente o de una lista vacía
- **THEN** el conjunto es vacío y nunca incluye `patient.read` por defecto

### Requirement: Pantalla de pacientes en el SPA

La ruta `/pacientes` MUST exigir `patient.read` para mostrar el listado y la búsqueda, y MUST ocultar
el botón de alta sin `patient.create` y el de edición sin `patient.update`. Los errores MUST mostrarse
por `code`: `patient_dni_duplicado` como conflicto no confirmable, `patient_posible_duplicado` con la
lista de candidatos y una acción de confirmación que reintenta con `confirmar_duplicado=true`, y
`forbidden` como falta de permisos. La pantalla MUST hablar con el backend real, sin datos mock.

#### Scenario: S11.1 — El listado y la búsqueda consumen el backend real

- **WHEN** un usuario con `patient.read` entra a `/pacientes` y busca `perez`
- **THEN** ve los pacientes que devuelve el backend y el total
- **AND** la petición incluye el `q` recortado y la sesión httpOnly, sin datos mock

#### Scenario: S11.2 — El alta aparece en la tabla con su número de HCE

- **WHEN** un usuario con `patient.create` completa el formulario y confirma
- **THEN** la tabla muestra la ficha nueva con su `numero_historia_clinica`
- **AND** sin `patient.create` el botón de alta no se renderiza

#### Scenario: S11.3 — El DNI duplicado se informa y no se pierde el formulario

- **WHEN** el alta responde `409 patient_dni_duplicado`
- **THEN** la pantalla muestra el mensaje del `code` y conserva los valores cargados
- **AND** no muestra el diálogo de confirmación, porque esa regla no se puede vencer

#### Scenario: S11.4 — El posible duplicado se confirma desde la pantalla

- **WHEN** el alta responde `409 patient_posible_duplicado` con candidatos
- **THEN** la pantalla lista los candidatos y ofrece "Confirmar alta"
- **AND** al confirmar reintenta con `confirmar_duplicado=true` y la ficha queda creada

#### Scenario: S11.5 — La pantalla respeta los permisos y trata forbidden como tal

- **WHEN** un usuario sin `patient.read` abre `/pacientes`
- **THEN** la pantalla muestra "sin permisos" y no ejecuta la petición de listado
- **AND** un usuario con `patient.read` pero sin `patient.update` ve la tabla sin la acción de edición
- **AND** si el backend responde `403 forbidden`, la pantalla lo informa como falta de permisos y no
  como error genérico
