# Spec Delta — platform-rbac

## MODIFIED Requirements

### Requirement: Catálogo de permisos atómicos y matriz rol→permiso completa

El sistema MUST declarar la matriz RBAC como constantes de aplicación: **19 recursos** × **9 roles**
con permisos atómicos nombrados `recurso.accion`. Los **17 recursos** se toman 1:1 de la tabla de
`knowledge-base/03_actores_y_roles.md` (§ Recursos estructurales); la fila "Usuarios y roles" se
desdobla en dos recursos —`team` (CRUD de memberships) y `ownership` (`ownership.transfer`)—, lo que da
18, y se agrega `membership_event` para la auditoría de RBAC (19), que no tiene lectores en la
aplicación. Cada celda de la matriz de la KB MUST traducirse a la misma cantidad de acciones
(`C`→`create`, `R`→`read`, `U`→`update`, `D`→`delete`), y los accesos "propios" del paciente MUST
declararse con el sufijo `_own` (nunca como `read` pleno). Los permisos efectivos de un usuario en un
tenant MUST ser la **unión** de los permisos de sus memberships activas, y un rol o permiso desconocido
MUST resolver a conjunto vacío (fail-closed), nunca a "permitir todo". Ningún endpoint ni componente de
UI MUST comparar el nombre del rol para decidir un acceso: la decisión MUST salir del conjunto de
permisos.

#### Scenario: S1.1 — El owner obtiene exactamente el conjunto de su fila de la matriz

- **WHEN** se resuelven los permisos efectivos de un usuario con una única membership activa
  `owner` en el tenant
- **THEN** el conjunto incluye `tenant_settings.create`, `tenant_settings.read`,
  `tenant_settings.update`, `chair.create`, `chair.read`, `chair.update`, `chair.delete`,
  `professional.create`, `professional.read`, `professional.update`, `patient.create`, `patient.read`,
  `patient.update`, `patient.delete`, `team.create`, `team.read`, `team.update`, `team.delete`,
  `appointment.create`, `appointment.read`, `appointment.update`, `appointment.delete`, `cash.create`,
  `cash.read`, `cash.update`, `invoice.create`, `invoice.read`, `invoice.update`,
  `settlement.create`, `settlement.read`, `settlement.update`, `report_financial.read`,
  `report_usage.read`, `migration.create`, `migration.read`, `migration.update`, `aaip_request.create`,
  `aaip_request.read`, `whatsapp_config.create`, `whatsapp_config.read`, `whatsapp_config.update`,
  `clinical_record.read`, `chart.read`, `consent.read` y `ownership.transfer`
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
- **THEN** el conjunto no incluye `clinical_record.read`, `chart.read`, `team.read`, `cash.delete`,
  `patient.delete` ni `ownership.transfer`
- **AND** sí incluye `appointment.create`, `appointment.read`, `appointment.update`,
  `appointment.delete`, `patient.create`, `patient.read`, `patient.update`, `cash.create`,
  `cash.read`, `cash.update` e `invoice.create`/`invoice.read`

#### Scenario: S1.4 — Un rol o permiso fuera del catálogo falla cerrado

- **WHEN** la resolución de permisos recibe un valor que no pertenece al enum `Role` o un permiso
  que no está en el catálogo
- **THEN** devuelve conjunto vacío o lanza un error de dominio, pero nunca concede un permiso no
  declarado
- **AND** el test parametrizado de la matriz recorre las 9 roles × 19 recursos y falla si una celda
  de la KB no coincide con el catálogo declarado

### Requirement: Fronteras duras clínicas (RN-CMP-04) codificadas como permisos

Salvo los clínicos —`professional` y `assistant`—, `owner` y `clinical_admin`, ningún rol interno
MUST tener permiso de lectura de historia clínica, y `front_desk`, `billing`, `accountant` y
`external_lab` MUST carecer de `clinical_record.read`, `chart.read` y `chart.finalize`. La recepcionista MUST NOT poder leer historia clínica ni odontograma por ninguna
vía HTTP (frontera dura, no preferencia de UI). El único rol con `chart.finalize` MUST ser
`professional`: `assistant` puede crear y leer odontograma pero no cerrarlo como autor. Mientras el
dominio clínico no exista (llega con **C-09**; la ficha demográfica de C-06 **no** lo reemplaza), la
frontera MUST probarse sobre un endpoint sonda reservado que no crea tablas ni datos clínicos.

#### Scenario: S3.1 — La recepcionista recibe 403 en el endpoint clínico reservado

- **WHEN** una sesión con membership activa `front_desk` invoca `GET /api/v1/clinical/patients`
- **THEN** responde `403 forbidden` antes de ejecutar cualquier lógica del endpoint
- **AND** la respuesta no contiene pacientes, conteos, identificadores ni pistas de si el recurso
  existe, y no crea filas en ninguna tabla

#### Scenario: S3.2 — Un rol clínico pasa la guarda y la capacidad sigue pendiente

- **WHEN** una sesión con membership activa `professional` invoca `GET /api/v1/clinical/patients`
- **THEN** la guarda de permiso se satisface y responde `501` con `code = "capability_pending"`
- **AND** la respuesta no devuelve datos clínicos ni crea tablas: la capacidad se completa en **C-09**
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

