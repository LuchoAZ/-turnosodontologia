# Ficha demográfica del paciente (C-06) — alta, búsqueda e historia clínica numerada

> Change: `c-06-patients` (archivado el 2026-11-12). Migración: `006_patients`. Pantalla: `/pacientes`.
> Rutas: `/api/v1/patients` (4 endpoints). La historia clínica **clínica** (evoluciones,
> alergias, alertas) **no** se entrega acá: es C-09 (PQ-17).

---

## 1. Qué se entrega

| Capa | Archivo |
|---|---|
| Modelos | `backend/app/models/patients.py` (`Patient`, `PatientCounter`, `SexoPaciente`) |
| Migración | `backend/alembic/versions/006_patients.py` |
| Dominio | `backend/app/domain/patients/{normalize,hce,search,errors,service}.py` |
| Esquemas | `backend/app/schemas/patients.py` |
| API | `backend/app/api/v1/patients/router.py` |
| Frontend | `frontend/src/api/patients.ts`, `frontend/src/features/patients/*` |
| Pantalla | ruta `/pacientes` en `frontend/src/App.tsx`, enlace en `frontend/src/routes/Home.tsx` |

`patient` y `patient_counter` tienen `tenant_id NOT NULL`, `ENABLE` + `FORCE ROW LEVEL SECURITY` y
política `USING/WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)`, igual que
`membership` (DD-07). El rol de aplicación (`odontologia_app`) recibe `SELECT/INSERT/UPDATE/DELETE`
sobre `patient` y `SELECT/INSERT/UPDATE` sobre `patient_counter`: el contador **no** acepta `DELETE`
porque solo avanza (RN-CLI-01). La extensión `pg_trgm` se crea en esta migración porque solo estos
índices la consumen.

Lo que el change **no** hace (y está declarado): borrar pacientes (`DELETE`), línea de tiempo, portal
del paciente, captura de `alergias`/`alerta_clinica`, y auditoría de lecturas. Todas están en §12.

---

## 2. Modelo

### 2.1 `patient`

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK `gen_random_uuid()` |
| `tenant_id` | uuid | FK `tenant` `ON DELETE CASCADE`, `NOT NULL` |
| `user_id` | uuid | FK **simple** `user` `ON DELETE SET NULL`; se llena cuando exista portal (§12) |
| `dni` | varchar(11) | opcional; único por tenant con índice **parcial** (`WHERE dni IS NOT NULL`) |
| `nombre`, `apellido` | varchar(80) | `NOT NULL`; se recortan y no admiten vacío |
| `nombre_norm`, `apellido_norm` | varchar(80) | denormalización de búsqueda (D5); **no** se expone |
| `fecha_nacimiento` | date | opcional |
| `sexo` | enum `sexo_paciente` | `femenino`, `masculino`, `otro`, `no_declara`; nullable |
| `telefono` | varchar(32) | `NOT NULL` |
| `telefono_norm` | varchar(32) | solo dígitos; **no** se expone |
| `email` | citext | opcional |
| `domicilio` | jsonb | `{calle, numero, localidad, provincia, codigo_postal}`, todo opcional |
| `obra_social_id` | uuid | nullable, **sin** FK ni catálogo todavía (§12) |
| `numero_historia_clinica` | varchar(20) | único por tenant (`uq_patient_tenant_numero_historia_clinica`) |
| `alergias` | text | existe, **no** se expone en C-06 (PQ-17) |
| `alerta_clinica` | boolean | existe, `DEFAULT false`, **no** se expone (PQ-17) |
| `activo` | boolean | `DEFAULT true` |
| `deleted_at` | timestamptz | baja lógica; `NULL` = vigente |
| `created_at`, `updated_at` | timestamptz | `now()`; `updated_at` con `onupdate` en el modelo |

`varchar(20)` para la HCE es deliberado: el número crece de 6 a 7 dígitos sin migración (S4.6).

### 2.2 `patient_counter`

| Columna | Tipo | Regla |
|---|---|---|
| `tenant_id` | uuid | **PK** y FK `tenant` `ON DELETE CASCADE`: una fila por tenant |
| `ultimo_numero` | integer | `DEFAULT 0`; solo avanza |
| `updated_at` | timestamptz | `now()` en cada reserva |

Es una tabla de **negocio** (tiene `tenant_id`), así que lleva la misma RLS `FORCE` que `patient`. No
tiene `DELETE` para `odontologia_app`: un número emitido no se libera ni por error de permisos.

### 2.3 Índices (y por qué cada uno)

| Índice | Definición | Para qué |
|---|---|---|
| `uq_patient_dni` | `UNIQUE (tenant_id, dni) WHERE dni IS NOT NULL` | dedupe duro por DNI (S5.1) sin impedir varios pacientes sin DNI (S5.4) ni castigar otros tenants (S5.3) |
| `ix_patient_tenant_id` | `(tenant_id)` | listado por tenant |
| `ix_patient_nombre` | `(tenant_id, apellido_norm, nombre_norm)` | orden estable del listado (S1.1) |
| `ix_patient_nombre_trgm` | GIN `apellido_norm gin_trgm_ops, nombre_norm gin_trgm_ops` | búsqueda por fragmento (`LIKE '%…%'`) sin scan completo (S2.1) |
| `ix_patient_telefono` | `(tenant_id, telefono_norm)` | búsqueda y dedupe blando por teléfono (S2.2, S6.2) |
| `ix_patient_activos` | `(tenant_id) WHERE deleted_at IS NULL` | listado y dedupe blando solo sobre vigentes (S6.6) |

El índice único **no** filtra por `deleted_at` a propósito: el DNI de un paciente dado de baja sigue
bloqueando el alta de otro con el mismo documento (S5.6). Un DNI nunca se recicla.

La migración es reversible: `test_patients_migration.py` sube, baja y verifica que `patient`,
`patient_counter` y el tipo `sexo_paciente` desaparezcan; `pg_trgm` **no** se dropea (extensión
compartida, mismo criterio que `citext` en `002_core_tenancy`).

---

## 3. Permisos usados (fila `patient` de la matriz de C-04)

| Endpoint | Permiso |
|---|---|
| `GET /patients` | `patient.read` |
| `GET /patients/{id}` | `patient.read` |
| `POST /patients` | `patient.create` |
| `PATCH /patients/{id}` | `patient.update` |

La fila `patient` de `backend/app/domain/rbac/matrix.py` queda así (S10.1):

| Rol | `patient.*` |
|---|---|
| `owner` | `create`, `read`, `update`, `delete` |
| `clinical_admin` | `create`, `read`, `update` |
| `front_desk` | `create`, `read`, `update` |
| `professional` | `read` |
| `assistant` | `read` |
| `billing` | `read` |
| `patient`, `external_lab`, `accountant` | — |

El catálogo pasa a **19 recursos / 61 permisos** (S10.2) y `RESOURCE_ACTIONS["patient"]` declara las
cuatro acciones, incluida `delete`, que todavía **no tiene endpoint** (§12). La resolución sigue
fallando cerrado: rol desconocido o lista vacía → conjunto vacío, nunca `patient.read` por defecto
(S10.3).

Consecuencias que se ven en el producto:

- Recepción administra la ficha completa (US-030) **sin** obtener `clinical_record.read`: la sonda
  `GET /api/v1/clinical/patients` le sigue respondiendo `403` (S3.5, S9.2, RN-CMP-04).
- Un profesional ve la lista pero no da de alta ni edita (S3.2, S8.6, S11.2, S11.5).
- `accountant` y `external_lab` no ven nada (S1.2, S7.3).

La guarda corre **antes** del body y antes de tocar la base: un `403` no filtra si el `id` existía.

---

## 4. Catálogo `PatientErrorCode`

`backend/app/domain/patients/errors.py`. Payload `{"code", "message"}` y, cuando corresponde,
`candidatos`. El frontend conmuta por `code` (`frontend/src/features/patients/errors.ts`).

| `code` | Status | Cuándo |
|---|---:|---|
| `patient_not_found` | 404 | id inexistente, de otro tenant o ya invisible por RLS |
| `patient_dni_duplicado` | 409 | DNI ya registrado en el tenant (incluido un paciente con `deleted_at`) |
| `patient_posible_duplicado` | 409 | coincidencia blanda por nombre completo o teléfono, sin confirmar |
| `invalid_request` | 422 | body inválido, campo reservado/desconocido, `q` de 61+ caracteres, paginación fuera de rango |

`forbidden` (403) **no** se duplica: lo emite la guarda de RBAC (C-04) con el mismo shape. El mensaje
no ecoa el valor recibido ni el `tenant_id`, y un `404` por id ajeno es **byte a byte** igual al de un
id inexistente (S7.2, S8.4): no se puede distinguir si la fila existe en otro tenant.

Los `422` de FastAPI también salen como `invalid_request`: `app/main.py` registra
`RequestValidationError` y reemplaza el `detail` de FastAPI (que ecoa el valor) por el contrato único.

---

## 5. Contrato HTTP

Base: `/api/v1`. Todas las rutas exigen sesión (`require_auth` + `require_tenant`) y el `tenant_id`
sale **del token**: nunca del body, la query o los headers. Si aparece en el body, `422`
(`extra="forbid"`), incluso `tenant_id`, `numero_historia_clinica`, `deleted_at`, `alergias` o
`alerta_clinica` (S3.3, S8.2, S11.5).

### 5.1 Listado

`GET /patients?q=&incluir_inactivos=&limit=&offset=` → `200 {"patients": [PatientOut], "total": int}`

- `q` opcional, máximo **60** caracteres; se recorta y, si queda vacío, equivale a listar sin filtro
  (S2.6). Con 61 caracteres responde `422 invalid_request` **sin ejecutar la consulta** (S2.5).
- `incluir_inactivos` (`false` por defecto) trae también las filas con `deleted_at`; la respuesta
  nunca expone `deleted_at` (S1.6).
- `limit` 1–100 (default 20), `offset` ≥ 0. Fuera de rango → `422` (S1.4).
- Orden fijo: `apellido_norm`, `nombre_norm`, `id` (S1.1, S4.1). La colación del contenedor ordena por
  bytes, así que los tests de orden usan apellidos ASCII.
- Un tenant sin pacientes devuelve `{"patients": [], "total": 0}` (S1.3). RLS garantiza que el listado
  de A nunca incluye filas de B, aunque compartan DNI y nombre (S1.5, S2.4).

### 5.2 Lectura

`GET /patients/{id}` → `200 PatientOut` / `404 patient_not_found`

Devuelve los mismos campos que el listado (S7.1). Sin `tenant_id`, `deleted_at`, `*_norm`, `alergias`
ni `alerta_clinica` (S9.1). Un id de otro tenant y un id aleatorio dan el mismo `404` (S7.2).

### 5.3 Alta

`POST /patients` → `201 PatientOut`

`PatientCreate` = `{nombre, apellido, telefono, dni?, fecha_nacimiento?, sexo?, email?, domicilio?,
confirmar_duplicado?}`. `nombre`/`apellido` 1–80 (se recortan; vacío → `422`, S3.6), `telefono` 1–32
obligatorio, `dni` `^\d{7,11}$` opcional, `email` validado con `EmailStr`. `confirmar_duplicado` es
**control**, no se persiste ni se devuelve (S6.3).

```json
{
  "id": "0f0f8c1e-…",
  "numero_historia_clinica": "000001",
  "nombre": "Ana",
  "apellido": "Pérez",
  "dni": "30111222",
  "fecha_nacimiento": "1985-07-12",
  "sexo": "femenino",
  "telefono": "11 5555-1234",
  "email": "ana.perez@example.com",
  "domicilio": { "calle": "Av. Demo", "numero": "123", "localidad": "CABA" },
  "activo": true,
  "created_at": "2026-11-12T10:00:00Z",
  "updated_at": "2026-11-12T10:00:00Z"
}
```

La HCE se reserva y el `INSERT` se confirman **juntos** (§6.1). Un body inválido no avanza el
contador (S3.4).

### 5.4 Actualización

`PATCH /patients/{id}` → `200 PatientOut`

`PatientUpdate` acepta solo los campos demográficos, todos opcionales;
`model_dump(exclude_unset=True)` distingue "no enviado" de `null` (S8.1). Rechaza con `422` los campos
reservados (S8.2) y con `409 patient_dni_duplicado` un DNI ya usado por otro paciente del tenant, sin
modificar la fila (S8.3). Al cambiar `nombre`/`apellido` recalcula los `*_norm`: después del cambio,
`?q=gomez` lo encuentra y `?q=perez` ya no (S8.5).

> Detalle de implementación: el servicio hace `db.refresh(patient)` **antes** del `commit()`. El GUC
> `app.current_tenant` es transaction-local; después del commit se limpia y un `refresh` posterior
> chocaba con RLS (`ObjectDeletedError`) al recargar `updated_at` (`onupdate=now()`).

---

## 6. Reglas de dominio

### 6.1 Número de historia clínica (D4)

El número sale de `patient_counter` con un **upsert atómico** dentro de la misma transacción del alta:

```sql
INSERT INTO patient_counter (tenant_id, ultimo_numero) VALUES (:tenant_id, 1)
ON CONFLICT (tenant_id) DO UPDATE
  SET ultimo_numero = patient_counter.ultimo_numero + 1, updated_at = now()
RETURNING ultimo_numero
```

Por qué **no** `MAX(numero) + 1`:

- Dar de baja al paciente con el número más alto lo **reciclaría** (S4.3, RN-CLI-01).
- Dos altas concurrentes leerían el mismo `MAX` y chocarían contra la unicidad.
- El `MAX` escanea la tabla en cada alta.

Propiedades que se verifican:

| Propiedad | Escenario |
|---|---|
| Tres altas seguidas dan `000001`, `000002`, `000003` | S4.1 |
| Cada tenant arranca su propia secuencia (unicidad por `(tenant_id, numero)` | S4.2 |
| Dar de baja al último no libera su número | S4.3 |
| Dos altas concurrentes obtienen números distintos | S4.4 |
| Un alta fallida (p. ej. DNI duplicado) **no deja hueco**: contador e `INSERT` revierten juntos | S4.5 |
| Formato `f"{secuencia:06d}"`; en `999999` el siguiente es `1000000` | S4.6 |

`formatear_numero` (`backend/app/domain/patients/hce.py`) es puro y testeable sin base; `siguiente_numero_historia_clinica`
es el único que toca la tabla.

### 6.2 Dedupe duro por DNI (S5)

Antes de insertar, el servicio busca el DNI en el tenant **sin filtrar `deleted_at`**:

| Caso | Resultado |
|---|---|
| DNI de un paciente vigente | `409 patient_dni_duplicado` con `id` y HCE del existente (S5.1) |
| Mismo alta con `confirmar_duplicado=true` | `409` igual: esa regla no se vence (S5.2) |
| Mismo DNI en **otro** tenant | `201` (S5.3) |
| Varios pacientes con `dni = null` | conviven: el índice es parcial (S5.4) |
| Dos altas simultáneas con el mismo DNI | la que pierde la carrera recibe `409`, nunca `500`, y no consume número (S5.5) |
| DNI de un paciente con `deleted_at` | sigue bloqueando (S5.6) |

El chequeo explícito da el mensaje legible; el índice único parcial es el **backstop**: su
`IntegrityError` se traduce al mismo `409` (nunca a `500`).

### 6.3 Dedupe blando por nombre o teléfono (S6)

Solo entre pacientes **activos** (`deleted_at IS NULL`), comparando `apellido + nombre` normalizados
o `telefono_norm`. Con coincidencias y `confirmar_duplicado = false` → `409 patient_posible_duplicado`
con **hasta 5** candidatos `{id, numero_historia_clinica, nombre, apellido, dni, telefono}` y sin crear
fila.

| Caso | Resultado |
|---|---|
| `PEREZ, ANA` cuando existe `Pérez, Ana` | `409` con el candidato (S6.1) |
| Teléfono normalizado repetido, otro nombre | `409` con el candidato por teléfono (S6.2) |
| Reintento con `confirmar_duplicado=true` | `201`, dos HCE distintas (S6.3) |
| Sin coincidencias | `201` directo (S6.4) |
| Homónimo en otro tenant | `201` (S6.5) |
| Único homónimo dado de baja | `201`, porque solo miran los activos (S6.6) |
| Siete coincidencias por teléfono | `409` con exactamente 5 candidatos (S6.7) |

El tope de 5 es de producto: el diálogo debe ser accionable, no un volcado de la tabla. El `code` es el
mismo con una o con cinco coincidencias, así la UI no ramifica por cantidad.

### 6.4 Normalización y búsqueda (D5)

`normalizar_texto` = `NFKD` → sin diacríticos → `casefold` → espacios colapsados. Por eso `"  ANA
MARÍA "` → `"ana maria"` y `"Núñez"` → `"nunez"`: se busca sin acentos y el dedupe no se rompe por
tipeo. `normalizar_telefono` deja **solo dígitos**: `+54 11 5555-1234` y `11 5555-1234` son números
distintos, y los tests que comparan por teléfono usan los mismos dígitos.

La búsqueda corre sobre `apellido_norm`, `nombre_norm`, `telefono_norm` y el **DNI exacto**. El texto
del usuario se escapa (`%`, `_`, `\`) y el `LIKE` se ejecuta siempre con `ESCAPE '\'` (S2.3): un `%`
buscado es un porcentaje literal, nunca "todos". `q` se recorta antes de armar el patrón, y un `q`
vacío no envía `%%` (S2.6). Se prefiere normalizar en la aplicación antes que `unaccent`: es
determinístico, testeable sin extensiones y el GIN trigram acelera el `LIKE` sobre columnas ya
normalizadas.

### 6.5 Frontera clínica (S9, PQ-17)

Ninguna respuesta de `/api/v1/patients` incluye `alergias`, `alerta_clinica`, `clinical_record` ni
`historia_clinica` (S9.1). Mandarlos en el body es `422 invalid_request` y la columna queda en su
valor por defecto (S9.3). Recepción administra la ficha y sigue fuera de la HC (S9.2). La captura
clínica —incluida la alerta que US-030 le atribuía a recepción— llega con C-09 y el permiso
`clinical_record.*`; el conflicto entre US-030 y RN-CMP-04 quedó registrado como **PQ-17**.

---

## 7. Aislamiento (RN-TEN-02, gate de merge)

`backend/tests/integration/test_patients_rls.py` (9 tests) corre con `SET ROLE odontologia_app` y el
GUC `app.current_tenant` fijado, porque el superusuario **ignora** RLS y un test con el superusuario no
prueba nada:

1. `SELECT` de las filas de B en `patient` y `patient_counter` devuelve `0`.
2. `UPDATE`/`DELETE` del id de B afecta `0` filas.
3. Fail-closed: sin `app.current_tenant`, ambas tablas devuelven `0` filas y el `INSERT` sin contexto
   lo frena el `WITH CHECK`.
4. Con contexto de A no se puede insertar una fila con `tenant_id` de B.
5. `tenant_id` en el body → `422`; `?tenant_id=` y headers con otro tenant se ignoran y la operación
   sigue con el de la sesión.
6. Los pacientes y la HCE de B no aparecen en el listado, la búsqueda ni la lectura de A.

**Prueba de mutación** (evidencia en `docs/skills-mcp/evidencias/gate-rls-c-06.md`): con
`ALTER TABLE patient DISABLE ROW LEVEL SECURITY` el test cross-tenant ve filas de B y falla; al
restaurarla vuelve a verde. Lo mismo con `patient_counter`. El gate no puede pasar sin la política.

Recordatorio de plataforma: después de `db.commit()` el GUC se limpia, así que no se consulta bajo RLS
después del commit; el contexto se abre en cada transacción con
`SELECT set_config('app.current_tenant', :tenant_id, true)` (`SET LOCAL` no acepta binds).

---

## 8. Pantalla `/pacientes`

- Ruta protegida con `<RequirePermission permission="patient.read">`; el enlace "Pacientes" de la Home
  aparece solo con ese permiso. Mientras la sesión carga, la pantalla muestra "Cargando…" y **no**
  `Forbidden`: con el estado todavía desconocido, "sin permisos" sería una mentira.
- Buscador por apellido, nombre, DNI o teléfono con el `q` recortado; se dispara con "Buscar" o Enter
  (sin debounce, para que el e2e sea determinista). Checkbox "Incluir dados de baja", total y tabla
  (HCE, paciente, DNI, teléfono, estado).
- `Nuevo paciente` solo con `patient.create`; la columna "Acciones" con "Editar" solo con
  `patient.update`. Nunca se compara el rol: `hasPermission(...)` (lo barre
  `frontend/src/features/auth/rolesSweep.test.ts`).
- `PatientFormDialog` hace alta y edición: `nombre`, `apellido`, `teléfono`, `DNI`, fecha de
  nacimiento, sexo, email y domicilio simple; valida en el cliente y muestra el error del backend sin
  cerrar el diálogo.
- Errores por `code`: `patient_dni_duplicado` informa "Ya hay un paciente con ese DNI" y conserva los
  valores cargados, **sin** ofrecer confirmación (S11.3); `patient_posible_duplicado` abre
  `DuplicateDialog` con los candidatos y "Confirmar alta", que reintenta con
  `confirmar_duplicado=true` (S11.4); `forbidden` se informa como falta de permisos (S11.5).
- El alta aparece en la tabla con su `numero_historia_clinica` y aviso
  `Paciente creado con HCE 000007.` (S11.2). La pantalla habla siempre con el backend real: no hay
  datos mock ni *fallback* local (S11.1).
- `ApiError` transporta `payload: unknown` (5º parámetro) para que `candidatesOf(error)` lea
  `candidatos` con validación de runtime (`isCandidate`). Un `409` sin `candidatos` no rompe la
  pantalla.

### 8.1 Estados de la UI

| Estado | Qué se ve |
|---|---|
| sesión cargando | "Cargando…" (sin `Forbidden`) |
| sin `patient.read` | `Forbidden`, y **no** se ejecuta el `GET` del listado |
| `403` del backend con `patient.read` | `Forbidden` con el `code` |
| lista vacía | "No hay pacientes para mostrar." |
| error de negocio del listado | mensaje del catálogo + `code` en monoespaciado |

---

## 9. Demo (guion de 4 minutos para el video)

1. Login `admin@example.test` (clínica `clinica-demo`, rol `clinical_admin`) → Home → click
   **Pacientes**.
2. La tabla muestra el paciente sembrado **`E2E-Paciente, Demo`**, DNI `99000111`, con una HCE de seis
   dígitos (`000001`).
3. Buscar `demo` → la tabla se reduce a esa ficha y el total dice `1 paciente`. La petición real es
   `GET /api/v1/patients?q=demo` (visible en la pestaña Network).
4. **Nuevo paciente**: nombre `Ana`, apellido `Demo-Alta`, teléfono `11 4444-8271`, DNI `30111222` →
   "Guardar paciente" → aparece con su nueva HCE y el aviso `Paciente creado con HCE …`.
5. Repetir el **mismo DNI** con otro nombre → "Ya hay un paciente con ese DNI" +
   `patient_dni_duplicado`, el diálogo sigue abierto y los datos cargados se conservan. No hay opción
   de confirmar: la regla no se vence.
6. Repetir el **mismo nombre y apellido** con otro teléfono y sin DNI → aparece **"Posible
   duplicado"** con el candidato `E2E-Paciente, Demo`; "Confirmar alta" crea la ficha con una HCE
   distinta.
7. Cerrar sesión y entrar con `demo@example.test` (`professional`): ve la lista y la búsqueda, pero
   **no** "Nuevo paciente" ni "Editar". Forzar
   `POST /api/v1/patients` desde la consola devuelve `403 forbidden`.
8. Entrar con `ajeno@example.test` (tenant `clinica-demo-b`): la lista está vacía y buscar `demo`
   devuelve `total = 0`, aunque la ficha exista en la misma base.

---

## 10. Orquestación del e2e y seed

`backend/scripts/e2e_server.py` levanta Postgres/Redis (Testcontainers), corre `alembic upgrade head`
y ejecuta `backend/tests/fixtures/seed_auth_e2e.py`. El seed siembra, además de usuarios y clínica:

| Fila | Valor |
|---|---|
| paciente canónico | `E2E-Paciente, Demo`, DNI `99000111`, teléfono `11 5555-0199`, HCE de 6 dígitos |

Reglas del reset (mismo criterio que `Sillón demo` de C-05):

- Borra los pacientes del tenant e2e con `apellido LIKE 'E2E-%'` **salvo** el canónico (DNI
  `99000111`). Si se borrara, el `id` y la HCE cambiarían en cada arranque y el spec no tendría una
  fila estable que buscar.
- **Nunca** toca `patient_counter`: el número de historia clínica no se recicla (RN-CLI-01), así que
  las altas del e2e siguen tomando números nuevos aunque sus filas se borren.
- `test_seed_e2e.py` (2 tests) verifica idempotencia: mismos usuarios, mismas memberships, mismo
  paciente con la misma HCE, contador estable y borrado de un paciente residual insertado a mano.

`frontend/tests/e2e/patients.spec.ts` (4 tests, serial) usa `clinical_admin` —no `owner`, que exige
TOTP— y comparte `frontend/tests/e2e/support.ts` con los demás specs (importar de un `.spec.ts`
registraría sus tests dos veces). El spec crea su propio DNI con `Date.now()`; el seed limpia en el
arranque siguiente.

`playwright.config.ts` fija `expect.timeout` en **10 s**: el backend real arranca en frío (uvicorn +
pool + argon2) y cuatro workers lo golpean a la vez; con 5 s el primer login de la corrida era flaky.

---

## 11. Verificación (salida real, 2026-11-12)

### 11.1 Backend

```text
$ uv run ruff check .
All checks passed!

$ uv run mypy app
Success: no issues found in 70 source files

$ uv run pytest -q
621 passed, 1 warning in 95.55s (0:01:35)
```

Línea base previa a C-06: 444 tests. Este change agrega **177**: 174 en sus módulos propios (§11.4) y
3 en tests existentes (matriz RBAC, reversibilidad de migraciones y seed e2e). No se borró ni se
salteó ninguno. El gate real de tipos es `mypy app`: `mypy app tests` falla por módulos duplicados
(preexistente).

### 11.2 Frontend

```text
$ npx tsc -b          # sin salida = limpio
$ npx eslint .        # ✖ 1 problem (0 errors, 1 warning)
$ npx vitest run      # Test Files 14 passed (14) / Tests 96 passed (96)
```

El único warning es el **preexistente** de `components/ui/button.tsx` (`react-refresh` por exportar
`buttonVariants` junto al componente); C-06 no agrega warnings.

### 11.3 e2e (backend + Postgres reales)

```text
$ E2E_WEB_PORT=5180 npx playwright test
19 passed (25.0s)
```

Dos corridas verdes consecutivas con 4 workers. Los 4 nuevos son
`frontend/tests/e2e/patients.spec.ts`; los 15 previos siguen verdes.

### 11.4 Detalle por capa

| Capa | Archivo | Tests |
|---|---|---:|
| Catálogo de errores | `backend/tests/unit/patients/test_patient_errors.py` | 8 |
| Normalización de texto y teléfono | `backend/tests/unit/patients/test_normalize.py` | 16 |
| Búsqueda (escape de `LIKE`) | `backend/tests/unit/patients/test_search.py` | 14 |
| Numeración de HCE | `backend/tests/unit/patients/test_hce.py` | 8 |
| Schemas y validación de entrada | `backend/tests/unit/patients/test_schemas.py` | 30 |
| Migración `006` y reversibilidad | `backend/tests/integration/test_patients_migration.py` | 13 |
| Contrato HTTP (listar, leer, alta, PATCH, dedupe, RBAC) | `backend/tests/integration/test_patients_http.py` | 72 |
| Servicio (concurrencia y rollback del contador) | `backend/tests/integration/test_patients_service.py` | 4 |
| Aislamiento cross-tenant (gate) | `backend/tests/integration/test_patients_rls.py` | 9 |
| Seed e2e (idempotencia + reset) | `backend/tests/integration/test_seed_e2e.py` | 2 |
| Cliente HTTP | `frontend/src/api/patients.test.ts` | 9 |
| Pantalla, diálogos y permisos | `frontend/src/features/patients/PatientsPage.test.tsx` | 17 |
| Rutas y enlace de la Home | `frontend/src/App.test.tsx` | 9 (4 nuevos) |
| e2e | `frontend/tests/e2e/patients.spec.ts` | 4 |

> Nota de plataforma: `pytest` no acepta dos archivos con el mismo basename sin `__init__.py`. El test
> del catálogo se llama `test_patient_errors.py` (singular) para no colisionar con
> `tests/unit/rbac/test_errors.py` ni con `tests/unit/clinic/test_clinic_errors.py`.

### 11.5 Cobertura de escenarios

| Requisito | Escenarios | Dónde se prueba |
|---|---|---|
| Listado | S1.1–S1.6 | `test_patients_http.py` (listado/orden/paginación/inactivos), `test_patients_rls.py` (S1.5) |
| Búsqueda | S2.1–S2.6 | `test_patients_http.py` (acentos, DNI, teléfono, escapes, `q` largo, `q` vacío) |
| Alta | S3.1–S3.6 | `test_patients_http.py` (201, 403, reservados, inválidos, recepción, recorte) |
| HCE | S4.1–S4.6 | `test_patients_http.py` (secuencia por tenant, baja, concurrencia, desborde) + `test_patients_service.py` (rollback) |
| Dedupe por DNI | S5.1–S5.6 | `test_patients_http.py` (409, `confirmar_duplicado`, otro tenant, `null`, carrera, baja) |
| Dedupe blando | S6.1–S6.7 | `test_patients_http.py` (nombre, teléfono, confirmar, sin match, otro tenant, baja, tope 5) |
| Lectura | S7.1–S7.3 | `test_patients_http.py` (campos, 404 indistinguible, 403) |
| Actualización | S8.1–S8.6 | `test_patients_http.py` (contacto, reservados, DNI, 404, `*_norm`, 403) |
| Frontera clínica | S9.1–S9.3 | `test_patients_http.py` (claves ausentes, recepción + sonda `clinical`, 422) |
| RBAC | S10.1–S10.3 | `backend/tests/unit/rbac/test_matrix.py` (fila `patient`, 19/61) y `test_guard.py` (falla cerrado) |
| Pantalla | S11.1–S11.5 | `PatientsPage.test.tsx`, `App.test.tsx`, `patients.spec.ts` |

---

## 12. Deudas y desviaciones registradas (D10 + PQ-17)

| Deuda | Motivo |
|---|---|
| **PQ-17**: US-030 pide a recepción capturar `alergias`/`alerta_clinica`; RN-CMP-04 se lo prohíbe | Las columnas existen pero no se exponen; la captura clínica va a C-09 con `clinical_record.*`. Registrado en `knowledge-base/10_preguntas_abiertas.md` |
| `patient.delete` sin endpoint | El permiso existe para C-13 (baja con justificación y auditoría), no para C-06 |
| `obra_social_id` sin catálogo ni FK | Se persiste nullable para la migración de datos; la obra social llega con facturación |
| Portal del paciente | `patient.read_own` + identidad OTP/DNI es post-deadline |
| Auditoría de lecturas | Leer una ficha demográfica no se audita en C-06; la auditoría de accesos sensibles es C-13 |
| Búsqueda por acentos en SQL crudo | Se resuelve con columnas normalizadas en la aplicación; `unaccent` + función `IMMUTABLE` queda como alternativa futura |
| `patient.user_id` con FK simple | No hay portal todavía; cuando exista se agregará el `UNIQUE` que impida dos fichas para el mismo usuario |
| Baja de paciente sin flujo | `deleted_at` y `activo` existen y el listado los respeta, pero darlos de baja es C-13 |
| Carrera del dedupe blando | Dos altas simultáneas con el mismo nombre pueden pasar las dos: es una advertencia, no una regla dura. El DNI sí es duro |
| `mypy app tests` falla por módulos duplicados | Preexistente; el gate real es `mypy app` |
