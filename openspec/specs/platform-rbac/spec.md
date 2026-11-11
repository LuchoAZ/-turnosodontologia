# platform-rbac Specification

## Purpose
Define la autorización por permisos de los usuarios internos: un catálogo de permisos atómicos por
recurso y acción derivado de `knowledge-base/03_actores_y_roles.md` § RBAC — Matriz de permisos, la
resolución de permisos efectivos del tenant activo (unión de memberships, RN-TEN-05), la guarda HTTP
que exige un permiso y responde `403 forbidden`, las fronteras duras clínicas (RN-CMP-04) y la
proyección de permisos al SPA a través del contrato de sesión.

## Requirements

### Requirement: Catálogo de permisos atómicos y matriz rol→permiso completa

El sistema MUST declarar la matriz RBAC como constantes de aplicación: **18 recursos** × **9 roles**
con permisos atómicos nombrados `recurso.accion`. Los **16 recursos** se toman 1:1 de la tabla de
`knowledge-base/03_actores_y_roles.md` (líneas 33-48); la fila "Usuarios y roles" se desdobla en dos
recursos —`team` (CRUD de memberships) y `ownership` (`ownership.transfer`)—, lo que da 17, y se
agrega `membership_event` para la auditoría de RBAC (18), que no tiene lectores en la aplicación.
Cada celda de la matriz de la KB MUST traducirse a la misma
cantidad de acciones (`C`→`create`, `R`→`read`, `U`→`update`, `D`→`delete`), y los accesos
"propios" del paciente MUST declararse con el sufijo `_own` (nunca como `read` pleno). Los permisos
efectivos de un usuario en un tenant MUST ser la **unión** de los permisos de sus memberships
activas, y un rol o permiso desconocido MUST resolver a conjunto vacío (fail-closed), nunca a
"permitir todo". Ningún endpoint ni componente de UI MUST comparar el nombre del rol para decidir un
acceso: la decisión MUST salir del conjunto de permisos.

#### Scenario: S1.1 — El owner obtiene exactamente el conjunto de su fila de la matriz

- **WHEN** se resuelven los permisos efectivos de un usuario con una única membership activa
  `owner` en el tenant
- **THEN** el conjunto incluye `tenant_settings.create`, `tenant_settings.read`,
  `tenant_settings.update`, `chair.create`, `chair.read`, `chair.update`, `chair.delete`,
  `professional.create`, `professional.read`, `professional.update`, `team.create`, `team.read`,
  `team.update`, `team.delete`, `appointment.create`, `appointment.read`, `appointment.update`,
  `appointment.delete`, `cash.create`, `cash.read`, `cash.update`, `invoice.create`, `invoice.read`,
  `invoice.update`, `settlement.create`, `settlement.read`, `settlement.update`,
  `report_financial.read`, `report_usage.read`, `migration.create`, `migration.read`,
  `migration.update`, `aaip_request.create`, `aaip_request.read`, `whatsapp_config.create`,
  `whatsapp_config.read`, `whatsapp_config.update`, `clinical_record.read`, `chart.read`,
  `consent.read` y `ownership.transfer`
- **AND** no incluye `chart.finalize`, `clinical_record.create` ni `clinical_record.update`, que no
  figuran para `owner` en la matriz

#### Scenario: S1.2 — Dos memberships en el mismo tenant suman permisos

- **WHEN** un usuario tiene memberships activas `professional` y `clinical_admin` en el mismo tenant
- **THEN** sus permisos son la unión de ambas filas e incluyen `chart.finalize` (solo
  `professional`), `chair.create` (solo `clinical_admin`) y `appointment.read` (ambas)
- **AND** no obtiene `team.create` ni `ownership.transfer`, que no pertenecen a ninguno de los dos
  roles

#### Scenario: S1.3 — Un recurso sin letra para el rol no concede el permiso

- **WHEN** se resuelven los permisos de una membership activa `front_desk` (recepcionista)
- **THEN** el conjunto no incluye `clinical_record.read`, `chart.read`, `team.read`, `cash.delete`
  ni `ownership.transfer`
- **AND** sí incluye `appointment.create`, `appointment.read`, `appointment.update`,
  `appointment.delete`, `cash.create`, `cash.read`, `cash.update` e `invoice.create`/`invoice.read`

#### Scenario: S1.4 — Un rol o permiso fuera del catálogo falla cerrado

- **WHEN** la resolución de permisos recibe un valor que no pertenece al enum `Role` o un permiso
  que no está en el catálogo
- **THEN** devuelve conjunto vacío o lanza un error de dominio, pero nunca concede un permiso no
  declarado
- **AND** el test parametrizado de la matriz recorre las 9 filas × 18 recursos y falla si una celda
  de la KB no coincide con el catálogo declarado

### Requirement: Guarda HTTP por permiso y catálogo estable de errores de autorización

Todo endpoint protegido MUST declarar el permiso que exige y ejecutar la cadena
`require_auth` → `require_tenant` → `require_permission` en ese orden, con el `tenant_id` resuelto
del token/sesión (RN-TEN-03). Si el usuario autenticado no tiene el permiso, la respuesta MUST ser
`403` con `code = "forbidden"` y un `message` genérico, sin datos del recurso, sin distinguir si el
recurso existe y sin crear ni modificar filas. El catálogo de autorización MUST ser estable y
convivir con el de C-03: `forbidden` se agrega a los `code` de `docs/auth.md`; `mfa_required` sigue
siendo un `403` distinto y previo. La guarda MUST evaluarse antes de cualquier escritura o efecto de
negocio.

#### Scenario: S2.1 — Un permiso concedido deja pasar la operación

- **WHEN** un usuario con `team.read` invoca `GET /api/v1/team/members` con sesión válida y
  membership activa
- **THEN** responde `200` con la lista de miembros del tenant de la sesión
- **AND** la respuesta no incluye `permissions`, `password_hash`, `mfa_secret` ni tokens

#### Scenario: S2.2 — Un permiso ausente devuelve 403 forbidden y no filtra el recurso

- **WHEN** un usuario autenticado sin el permiso exigido invoca un endpoint protegido, incluso con
  un `membership_id` o `user_id` de otro tenant en la ruta o el body
- **THEN** responde `403` con `{"code": "forbidden", "message": …}` y ningún campo del recurso
- **AND** no se ejecuta la lógica del endpoint: no hay filas nuevas, modificadas ni eliminadas, y
  tampoco un evento de auditoría de negocio

#### Scenario: S2.3 — La cadena previa y el contrato de tenant_id

- **WHEN** se invoca un endpoint protegido sin cookie de sesión, con sesión vencida o con la
  membership desactivada
- **THEN** responde `401 not_authenticated` (o `401 session_expired` si corresponde) antes de
  evaluar el permiso, sin emitir `403 forbidden`
- **AND** la guarda evalúa contra el tenant de la sesión y nunca concede permisos de otro tenant: un
  `tenant_id` ajeno en **body** se rechaza con `422 invalid_request` (los DTO usan
  `extra="forbid"`), y en query o header no se lee. La guarda (`403`) corre antes de la validación
  del body (`422`): un actor sin permiso recibe `403` aunque el body sea inválido.

#### Scenario: S2.4 — El SPA no replica la matriz

- **WHEN** el frontend decide si muestra la sección de Equipo o un botón de acción
- **THEN** consulta los permisos efectivos recibidos del backend y conmuta por permiso
  (`team.read`, `team.update`, `team.delete`, `ownership.transfer`)
- **AND** el test de frontend verifica que no existe ninguna comparación de `roles` con valores
  `owner`, `clinical_admin`, `professional` o `front_desk` para decidir visibilidad

### Requirement: Fronteras duras clínicas (RN-CMP-04) codificadas como permisos

Salvo los clínicos —`professional` y `assistant`—, `owner` y `clinical_admin`, ningún rol interno
MUST tener permiso de lectura de historia clínica, y `front_desk`, `billing`, `accountant` y
`external_lab` MUST carecer de `clinical_record.read`, `chart.read` y `chart.finalize`. La recepcionista MUST NOT poder leer historia clínica ni odontograma por ninguna
vía HTTP (frontera dura, no preferencia de UI). El único rol con `chart.finalize` MUST ser
`professional`: `assistant` puede crear y leer odontograma pero no cerrarlo como autor. Mientras el
dominio clínico no exista (C-06), la frontera MUST probarse sobre un endpoint sonda reservado que no
crea tablas ni datos clínicos.

#### Scenario: S3.1 — La recepcionista recibe 403 en el endpoint clínico reservado

- **WHEN** una sesión con membership activa `front_desk` invoca `GET /api/v1/clinical/patients`
- **THEN** responde `403 forbidden` antes de ejecutar cualquier lógica del endpoint
- **AND** la respuesta no contiene pacientes, conteos, identificadores ni pistas de si el recurso
  existe, y no crea filas en ninguna tabla

#### Scenario: S3.2 — Un rol clínico pasa la guarda y la capacidad sigue pendiente

- **WHEN** una sesión con membership activa `professional` invoca `GET /api/v1/clinical/patients`
- **THEN** la guarda de permiso se satisface y responde `501` con `code = "capability_pending"`
- **AND** la respuesta no devuelve datos clínicos ni crea tablas: la capacidad se completa en C-06
  y queda registrada como deuda

#### Scenario: S3.3 — Solo el profesional finaliza odontograma y facturación no escribe clínica

- **WHEN** se comparan los permisos de `professional`, `assistant` y `billing` sobre el dominio
  clínico
- **THEN** `professional` tiene `chart.create`, `chart.read`, `chart.update` y `chart.finalize`;
  `assistant` tiene `chart.create` y `chart.read` pero no `chart.finalize`; `billing` no tiene ni
  `clinical_record.read` ni `clinical_record.create` ni `clinical_record.update`
- **AND** el test del guard confirma `403 forbidden` para `assistant` en una operación que exige
  `chart.finalize` y para `billing` en una que exige `clinical_record.update`

#### Scenario: S3.4 — Ningún rol interno gana lectura clínica por la unión de memberships

- **WHEN** un usuario acumula memberships activas `front_desk`, `billing`, `accountant` o
  `external_lab` en el mismo tenant, en cualquier combinación
- **THEN** la unión de permisos sigue sin incluir `clinical_record.read`, `chart.read` ni
  `chart.finalize`
- **AND** si además tiene `professional`, la lectura clínica proviene únicamente de esa membership
  y la frontera se evalúa por permiso, no por rol

#### Scenario: S3.5 — El guard rechaza por HTTP cada operación clínica reservada

- **WHEN** una sesión `billing` invoca un endpoint de prueba que exige `clinical_record.update` y una
  sesión `assistant` invoca otro que exige `chart.finalize`
- **THEN** ambas reciben `403 forbidden` con `code = "forbidden"`, sin ejecutar la operación
- **AND** el permiso faltante solo aparece en el log de aplicación (nunca en la respuesta y nunca como
  `membership_event`: un rechazo no se audita como evento de negocio)
- **AND** el mismo par (rol, permiso) evaluado por el guard parametrizado da el mismo resultado, de
  modo que la matriz y el guard no pueden divergir

### Requirement: Permisos efectivos del tenant activo en el contrato de sesión

`SessionOut` —respuesta de `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`,
`POST /api/v1/auth/switch-tenant`, los endpoints de MFA y `GET /api/v1/auth/me`— MUST incluir un
campo `permissions` con los permisos efectivos del usuario **en el tenant activo** (RN-TEN-05),
calculados en el servidor a partir de las memberships activas y la matriz. Los permisos MUST
recalcularse en cada respuesta de sesión (nunca se cachean en el token ni se aceptan del cliente),
MUST NOT incluir permisos de otro tenant y MUST NOT incluir secretos. El campo MUST ser una lista de
strings sin duplicados y con orden estable.

#### Scenario: S4.1 — /auth/me devuelve los permisos del rol activo

- **WHEN** se consulta `GET /api/v1/auth/me` con la sesión de una membership activa `owner`
- **THEN** responde `200` con `user`, `tenant`, `roles: ["owner"]`, `mfa_enrolled` y `permissions`
  que contiene `team.update`, `team.delete` y `ownership.transfer`
- **AND** el JSON no contiene `password_hash`, `mfa_secret`, tokens ni permisos de recursos
  inexistentes

#### Scenario: S4.2 — Con memberships en A y B, los permisos son los de A

- **WHEN** el usuario tiene `owner` en A y `front_desk` en B, y la sesión activa es la de A
- **THEN** `GET /api/v1/auth/me` devuelve únicamente los permisos derivados de `owner` en A e
  incluye `team.read`
- **AND** tras `switch-tenant` a B, el mismo endpoint devuelve los permisos de `front_desk` sin
  `team.read` ni `clinical_record.read`

#### Scenario: S4.3 — Un cambio de rol se refleja sin volver a loguearse

- **WHEN** el owner cambia el rol de un miembro de `professional` a `clinical_admin` y ese miembro
  consulta `GET /api/v1/auth/me` con su sesión vigente
- **THEN** la respuesta devuelve `roles: ["clinical_admin"]` y los permisos de esa fila
  (`chair.create` incluido), sin los permisos exclusivos de `professional` como `chart.finalize`
- **AND** la siguiente llamada a un endpoint de `chart.finalize` responde `403 forbidden` sin
  necesidad de revocar la sesión

#### Scenario: S4.4 — Permisos sin duplicados y sin permisos propios ajenos

- **WHEN** dos memberships activas del mismo tenant conceden el mismo permiso (`appointment.read`)
- **THEN** `permissions` aparece una sola vez y con orden estable entre llamadas
- **AND** los nueve permisos `_own` siguen la procedencia de la matriz: los del paciente
  (`clinical_record.read_own`, `chart.read_own`, `consent.read_own`, `appointment.create_own`,
  `appointment.read_own`, `cash.read_own`, `invoice.read_own`, `aaip_request.create_own`) solo
  aparecen con el rol `patient` —que no opera por HTTP interno en este change— y
  `settlement.read_own` solo con `professional`; ningún rol interno hereda los del paciente

#### Scenario: S4.5 — Sin memberships activas no hay sesión ni permisos residuales

- **WHEN** un usuario cuya única membership fue dada de baja consulta `GET /api/v1/auth/me` con su
  sesión todavía vigente
- **THEN** responde `401` con `code = "not_authenticated"` y no devuelve `permissions`
- **AND** ninguna respuesta posterior reutiliza el conjunto de permisos anterior
