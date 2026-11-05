# platform-tenancy Specification

## Purpose
Define el modelo base multi-tenant del sistema odontológico, el aislamiento por fila en
PostgreSQL y el contrato de resolución del tenant activo, de modo que cualquier capacidad
posterior (auth, agenda, clínica, facturación) herede `tenant_id` obligatorio, RLS fail-closed y
un único punto de resolución del tenant desde la sesión.

## Requirements

### Requirement: Modelo base multi-tenant con migración versionada

El sistema MUST definir las tablas `tenant`, `user`, `membership`, `specialty`, `price_concept` y
`currency` con SQLAlchemy 2.0 tipado (`Mapped`/`mapped_column`, sin `Any`) y una migración Alembic
`002_core_tenancy` que las cree desde la baseline de C-01. `membership` MUST tener `tenant_id NOT
NULL` con FK a `tenant`; `user` MUST ser global (sin `tenant_id`); `price_concept.tenant_id` MUST
ser nullable **solo** para representar el catálogo global de referencia (KB `04`, § Catálogos).
`membership` MUST tener `unique(tenant_id, user_id, rol)` y `price_concept` MUST tener
`unique(tenant_id, codigo)` con semántica `NULLS NOT DISTINCT` para que el catálogo global no
admita códigos duplicados.

#### Scenario: Migración aplicada sobre la baseline

- **WHEN** se ejecuta `alembic upgrade head` sobre una base con la baseline de C-01
- **THEN** existen las 6 tablas con sus índices y constraints, y el tipo enum `role` tiene
  exactamente los 9 valores de `03_actores_y_roles.md`

#### Scenario: Membership sin tenant rechazada

- **WHEN** se intenta insertar una `membership` sin `tenant_id`
- **THEN** PostgreSQL rechaza la operación con violación de `NOT NULL` (SQLSTATE `23502`) y no
  queda ninguna fila

#### Scenario: Membership con usuario inexistente rechazada

- **WHEN** se inserta una `membership` con un `user_id` que no existe
- **THEN** PostgreSQL rechaza la operación con violación de FK (SQLSTATE `23503`)

#### Scenario: Código global duplicado rechazado, global + tenant permitido

- **WHEN** existen dos `price_concept` globales (`tenant_id IS NULL`) con el mismo `codigo`
- **THEN** la segunda inserción falla por unicidad; en cambio, un `codigo` global y el mismo
  `codigo` en un tenant sí coexisten (el tenant puede sobreescribir el nomenclador base)

### Requirement: Unicidad del owner activo por tenant (RN-TEN-04)

El esquema MUST impedir que un tenant tenga **más de un** `membership` con `rol = 'owner'` y
`activo = true`, mediante un índice único parcial. Un `owner` inactivo MUST NOT contar para esa
restricción. La invariante complementaria —que no exista un estado con **cero** owners— es
responsabilidad de la transacción atómica de transferencia de ownership, que se implementa en
C-04; este change no la modela.

#### Scenario: Primer owner activo aceptado

- **WHEN** se inserta una `membership` con `rol = 'owner'` y `activo = true` en un tenant que no
  tiene otro owner activo
- **THEN** la inserción se acepta

#### Scenario: Segundo owner activo rechazado

- **WHEN** un tenant ya tiene un `owner` activo e intenta insertar otro `membership` con
  `rol = 'owner'` y `activo = true`
- **THEN** PostgreSQL rechaza la operación por el índice único parcial (SQLSTATE `23505`)

#### Scenario: Owner inactivo no bloquea al owner activo

- **WHEN** un tenant tiene un `owner` con `activo = false` e inserta un `owner` con
  `activo = true`
- **THEN** la inserción se acepta: el índice parcial solo cubre las filas activas

### Requirement: Row Level Security fail-closed en tablas tenant-scoped

Las tablas con datos de tenant (`membership`, `price_concept`) MUST tener Row Level Security
habilitada y **forzada** (`FORCE ROW LEVEL SECURITY`), con políticas que comparen `tenant_id`
contra `NULLIF(current_setting('app.current_tenant', true), '')::uuid`. La tabla `tenant` y los
catálogos globales (`user`, `specialty`, `currency`) MUST NOT tener RLS: `tenant` se resuelve por
`slug` antes de que exista contexto de tenant (login de C-03) y los catálogos son de lectura
pública interna. Sin contexto de tenant seteado, una consulta a una tabla con RLS MUST devolver
cero filas y MUST NOT fallar.

#### Scenario: Un tenant solo ve sus propias filas

- **WHEN** la sesión tiene `app.current_tenant = A` y consulta `membership`
- **THEN** devuelve únicamente las filas del tenant A

#### Scenario: Escritura cross-tenant rechazada por la política

- **WHEN** la sesión tiene `app.current_tenant = A` e intenta insertar o actualizar una
  `membership` con `tenant_id = B`
- **THEN** PostgreSQL rechaza la operación por `WITH CHECK` (SQLSTATE `42501`) y la fila de B no
  cambia

#### Scenario: Sin contexto de tenant la consulta es fail-closed

- **WHEN** no se ejecutó `set_config('app.current_tenant', …)` en la transacción y se consulta una
  tabla con RLS
- **THEN** la consulta devuelve 0 filas (no lanza error y no filtra datos)

#### Scenario: Update y delete cross-tenant no afectan filas

- **WHEN** la sesión tiene `app.current_tenant = A` y ejecuta `UPDATE` o `DELETE` filtrando por el
  `id` de una fila del tenant B
- **THEN** la operación afecta 0 filas y la fila de B permanece intacta

#### Scenario: Catálogo global visible para todos, override del tenant solo para su tenant

- **WHEN** la sesión tiene `app.current_tenant = A` y consulta `price_concept`
- **THEN** ve los conceptos globales (`tenant_id IS NULL`) y los de A, pero no los de B; una sesión
  con contexto B ve los globales y los de B

### Requirement: Contexto de tenant por transacción, parameterizado

El sistema MUST exponer un helper que fije el tenant activo con
`SELECT set_config('app.current_tenant', :tenant_id, true)` dentro de la transacción. El valor
MUST pasarse como parámetro bindeado (nunca interpolado en el SQL) y MUST ser transaction-local,
de modo que al hacer commit o rollback la conexión vuelva al pool sin contexto. Un identificador
inválido MUST rechazarse antes de ejecutar el SQL.

#### Scenario: Contexto aplicado dentro de la transacción

- **WHEN** se abre una transacción, se ejecuta el helper con el tenant A y se consulta `membership`
- **THEN** la consulta ve las filas de A

#### Scenario: Identificador inválido rechazado sin dejar contexto

- **WHEN** se ejecuta el helper con un valor que no es un UUID
- **THEN** lanza un error de validación antes de tocar la base y la transacción no queda con un
  contexto parcial

#### Scenario: El contexto no se filtra entre transacciones del pool

- **WHEN** una transacción fija el tenant A, hace commit y otra transacción reutiliza la misma
  conexión del pool sin fijar tenant
- **THEN** la segunda transacción no ve filas de A (el GUC quedó vacío), demostrando que no hay
  leak por reutilización de conexión

### Requirement: TenantGuard resuelve el tenant del token, nunca del body

El sistema MUST exponer una función pura que resuelva el `tenant_id` **exclusivamente** desde los
claims de la sesión (RN-TEN-03). Cualquier `tenant_id` presente en body, query o header MUST ser
ignorado. Si el claim falta, no es un UUID o la sesión no tiene membership activa, el resultado
MUST ser un error de autenticación (`401`), nunca un tenant por defecto.

#### Scenario: Tenant resuelto desde los claims

- **WHEN** los claims de la sesión contienen `tenant_id = A`
- **THEN** el guard resuelve A

#### Scenario: Sin claim de tenant no hay acceso

- **WHEN** los claims no incluyen `tenant_id`
- **THEN** el guard lanza el error de autenticación que el borde HTTP traduce a `401`

#### Scenario: Claim con formato inválido rechazado

- **WHEN** el claim `tenant_id` no es un UUID válido
- **THEN** el guard lanza el error de autenticación y no resuelve ningún tenant

#### Scenario: tenant_id en el body es ignorado

- **WHEN** los claims contienen el tenant A y el body de la petición contiene `tenant_id = B`
- **THEN** el guard resuelve A; el valor del body no influye en la resolución

### Requirement: Validación del CUIT del tenant (RN-TEN-01)

El sistema MUST validar el CUIT de un tenant con el algoritmo módulo 11 antes de persistirlo y
MUST normalizarlo a 11 dígitos sin guiones. Un CUIT con longitud distinta de 11, con caracteres no
numéricos o con dígito verificador incorrecto MUST rechazarse con un error de dominio.

#### Scenario: CUIT válido normalizado

- **WHEN** se valida `20-12345678-6`
- **THEN** el resultado es el CUIT válido normalizado `20123456786`

#### Scenario: Dígito verificador incorrecto rechazado

- **WHEN** se valida `20-12345678-0`
- **THEN** se lanza un error de dominio que indica dígito verificador inválido

#### Scenario: Formato inválido rechazado

- **WHEN** se valida un valor con 10 u 12 dígitos, o con letras
- **THEN** se lanza un error de dominio de formato y no se persiste nada

### Requirement: Seed de catálogos base

La migración MUST sembrar los catálogos mínimos para operar: las 2 monedas (`ARS` con 2 decimales
y símbolo `$`, `USD` con 2 decimales), las 9 especialidades de la KB, 80 `price_concept` globales
de referencia (`tenant_id IS NULL`) y el enum de 9 roles. Los conceptos globales MUST ser de solo
lectura para los tenants (RN-EX-05: son precios de referencia, no un precio cobrable sin override
del tenant) y la migración MUST ser reversible (`alembic downgrade base` elimina tablas, políticas
y rol de aplicación).

#### Scenario: Catálogos sembrados

- **WHEN** la migración termina
- **THEN** existen 2 monedas, 9 especialidades, 80 conceptos globales y el enum `role` con 9 valores

#### Scenario: Un tenant no puede escribir en el catálogo global

- **WHEN** la sesión tiene `app.current_tenant = A` e intenta insertar un `price_concept` con
  `tenant_id IS NULL`
- **THEN** la política RLS lo rechaza (`42501`): el catálogo global solo lo modifica la migración

#### Scenario: Downgrade reversible

- **WHEN** se ejecuta `alembic downgrade base` sobre una base migrada
- **THEN** las tablas, las políticas y el rol de aplicación se eliminan sin errores y la base queda
  como estaba después de la baseline de C-01
