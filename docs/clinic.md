# Configuración clínica (C-05) — sillones, profesionales y disponibilidad

> Change: `c-05-clinic-setup`. Migración: `005_clinic_setup`. Pantalla: `/clinica`.
> Rutas: `/api/v1/clinic/**` (11 endpoints). Prefijo elegido en el design (D1) para no
> colisionar con `tenant_settings` ni con el futuro `/agenda` de C-07.

---

## 1. Qué se entrega

| Capa | Archivo |
|---|---|
| Modelos | `backend/app/models/clinic.py` (`Chair`, `Professional`, `AvailabilityRule`, `ChairTipo`) |
| Migración | `backend/alembic/versions/005_clinic_setup.py` |
| Dominio | `backend/app/domain/clinic/{errors,validation,service}.py` |
| Esquemas | `backend/app/schemas/clinic.py` |
| API | `backend/app/api/v1/clinic/router.py` |
| Frontend | `frontend/src/api/clinic.ts`, `frontend/src/features/clinic/*` |
| Pantalla | ruta `/clinica` en `frontend/src/App.tsx`, enlace en `frontend/src/routes/Home.tsx` |

Las tres tablas nuevas tienen `tenant_id NOT NULL`, `ENABLE` + `FORCE ROW LEVEL SECURITY` y
política `USING/WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)`, igual que
`membership` (DD-07). El rol de aplicación (`odontologia_app`) recibe `SELECT/INSERT/UPDATE/DELETE`
sobre `chair`, `professional` y `availability_rule`.

`specialty` es la **excepción**: la sembró C-02 como catálogo global (`tenant_id IS NULL`) y no tiene
RLS. Su visibilidad se resuelve explícitamente en la consulta
(`tenant_id IS NULL OR tenant_id = :tid`), nunca con una política.

---

## 2. Modelo

### 2.1 `chair`

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK `gen_random_uuid()` |
| `tenant_id` | uuid | FK `tenant` `ON DELETE CASCADE`, `NOT NULL` |
| `nombre` | varchar(60) | único por tenant (`uq_chair_tenant_nombre`) |
| `tipo` | enum `chair_tipo` | `consultorio`, `rx`, `cirugia`, `higiene`, `otro` |
| `ubicacion` | varchar(120) | opcional |
| `equipamiento` | jsonb | `NOT NULL DEFAULT '{}'` |
| `activo` | boolean | nace en `true`; la baja es lógica |

### 2.2 `professional`

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK `tenant` `ON DELETE CASCADE` |
| `user_id` | uuid | FK `user` `ON DELETE SET NULL`; si viene, exige membership activa |
| `nombre`, `apellido` | varchar(80) | `NOT NULL` |
| `matricula` | varchar(32) | única por tenant (`uq_professional_tenant_matricula`) |
| `especialidad_id` | uuid | FK `specialty`, `NOT NULL`; debe ser global o del tenant |
| `porcentaje_liquidacion` | numeric(5,2) | `CHECK` 0–100, default `0` |
| `duracion_default_min` | integer | `CHECK` 5–480, default `30` |
| `color_agenda` | varchar(7) | hex `#RRGGBB`, default `#2563EB` |
| `activo` | boolean | la baja es `PATCH activo = false` (no existe `professional.delete`) |

`membership.professional_id` gana su FK `ON DELETE SET NULL` en esta migración: el vínculo
rol ↔ profesional ya existía como columna y ahora apunta a la tabla real.

### 2.3 `availability_rule`

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK `tenant` `ON DELETE CASCADE` |
| `professional_id` | uuid | `NULL` = toda la clínica; FK `ON DELETE CASCADE` |
| `chair_id` | uuid | `NULL` = cualquier sillón; FK `ON DELETE CASCADE` |
| `dia_semana` | smallint | `CHECK` 0–6 |
| `hora_inicio`, `hora_fin` | time | `CHECK hora_fin > hora_inicio` |
| `slot_min` | integer | `CHECK > 0`, default `30` |
| `buffer_previo_min`, `buffer_posterior_min` | integer | `CHECK >= 0`, default `0` |
| `fecha_desde` | date | vigencia desde |
| `fecha_hasta` | date | `NULL` = abierta; `CHECK NULL OR >= fecha_desde` |
| `tipo_practica` | varchar(40) | opcional (ver §11) |

Índice único: `unique nulls not distinct (tenant_id, professional_id, chair_id, dia_semana,
fecha_desde)` (`uq_availability_rule_scope`). `nulls not distinct` es necesario: dos reglas "toda la
clínica para el lunes" con ambos FKs en `NULL` deben chocar; con el `UNIQUE` clásico no chocarían.

### 2.4 Convención de `dia_semana`

`dia_semana` sigue **`EXTRACT(DOW)` de Postgres: `0 = domingo` … `6 = sábado`**. Se documenta acá
porque C-07 (agenda) va a generar los slots con esa misma extracción y un mapeo distinto en la UI
produciría turnos en el día equivocado. `frontend/src/features/clinic/catalog.ts` (`DAY_OPTIONS`)
es la única traducción a etiquetas.

---

## 3. Permisos usados (subconjunto de la matriz de C-04)

| Endpoint | Permiso |
|---|---|
| `GET /clinic/chairs` | `chair.read` |
| `POST /clinic/chairs` | `chair.create` |
| `PATCH /clinic/chairs/{id}` | `chair.update` |
| `DELETE /clinic/chairs/{id}` | `chair.delete` |
| `GET /clinic/professionals` | `professional.read` |
| `POST /clinic/professionals` | `professional.create` |
| `PATCH /clinic/professionals/{id}` | `professional.update` |
| `GET /clinic/specialties` | `professional.read` |
| `GET /clinic/availability` | `professional.read` |
| `POST /clinic/availability` | `professional.update` |
| `PATCH /clinic/availability/{id}` | `professional.update` |

Consecuencias de la matriz (no se agregaron permisos nuevos):

- `professional` y `front_desk` **leen** sillones pero no los crean ni los dan de baja.
- `clinical_admin` crea y actualiza sillones, pero **no** los da de baja (la matriz le da `CRU`, no `CRUD`).
- No existe `professional.delete`: la baja de un profesional es `PATCH` con `activo = false`.
- `availability_rule` **no tiene recurso propio** en la matriz; se reutilizan los permisos de
  `professional` en lectura/escritura. Es una deuda registrada (§11).
- La guarda corre **antes** del body y antes de tocar la base: un `403` no filtra si el id existía.

---

## 4. Catálogo `ClinicErrorCode`

`backend/app/domain/clinic/errors.py`. El payload es siempre `{"code", "message"}` y el `code` es el
contrato estable que consume la UI (`frontend/src/features/clinic/errors.ts`).

| `code` | Status | Cuándo |
|---|---:|---|
| `chair_not_found` | 404 | id ajeno, inexistente o de otro tenant |
| `chair_name_taken` | 409 | nombre repetido en el tenant (también si está inactivo) |
| `professional_not_found` | 404 | id ajeno, inexistente o de otro tenant |
| `professional_matricula_taken` | 409 | matrícula repetida en el tenant |
| `specialty_not_found` | 404 | la especialidad no es global ni del tenant |
| `user_not_member` | 422 | `user_id` sin membership activa en el tenant |
| `availability_not_found` | 404 | regla ajena, inexistente o de otro tenant |
| `availability_overlap` | 409 | solape parcial con otra regla del mismo alcance y día |
| `invalid_request` | 422 | ventana inválida, `tenant_id` en el body, campo desconocido |

`forbidden` (403) se reutiliza de `RbacErrorCode`: la matriz es la misma fuente para todo el
producto y duplicar el código rompería el contrato del front.

El mensaje **no** ecoa el valor recibido ni el `tenant_id`: nunca se devuelve el dato de otro tenant.

---

## 5. Contrato HTTP

Base: `/api/v1`. Todas las rutas exigen sesión (`require_auth` + `require_tenant`). El `tenant_id`
sale **del token**, nunca del body ni de la query: si aparece en el body, `422 invalid_request`
(lo cubre `S8.4`); `?tenant_id=` y los headers se ignoran.

### 5.1 Sillones

| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| `GET` | `/clinic/chairs` | — | `200 {"chairs": [ChairOut]}` |
| `POST` | `/clinic/chairs` | `ChairIn` | `201 ChairOut` |
| `PATCH` | `/clinic/chairs/{id}` | `ChairPatch` | `200 ChairOut` |
| `DELETE` | `/clinic/chairs/{id}` | — | `204` (baja lógica: `activo = false`) |

`ChairIn` = `{nombre, tipo, ubicacion?, equipamiento?}`. `activo` **no** se acepta en el alta (nace
`true`). `ChairPatch` acepta los mismos campos más `activo`. `ChairOut` agrega `id` y `activo`.

```json
{
  "id": "0f0f…",
  "nombre": "Sillón 1",
  "tipo": "consultorio",
  "ubicacion": "Planta baja",
  "equipamiento": {},
  "activo": true
}
```

### 5.2 Profesionales

| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| `GET` | `/clinic/professionals` | — | `200 {"professionals": [ProfessionalOut]}` |
| `POST` | `/clinic/professionals` | `ProfessionalIn` | `201 ProfessionalOut` |
| `PATCH` | `/clinic/professionals/{id}` | `ProfessionalPatch` | `200 ProfessionalOut` |

`ProfessionalIn` = `{nombre, apellido, matricula, especialidad_id, user_id?, duracion_default_min?,
porcentaje_liquidacion?, color_agenda?}`. `ProfessionalOut` anida la especialidad:

```json
{
  "id": "9b1e…",
  "user_id": null,
  "nombre": "Paula",
  "apellido": "Pérez",
  "matricula": "MP-1234",
  "especialidad": { "id": "8a2c…", "nombre": "Ortodoncia" },
  "duracion_default_min": 30,
  "porcentaje_liquidacion": "40.00",
  "color_agenda": "#2563EB",
  "activo": true
}
```

`porcentaje_liquidacion` es `numeric` y FastAPI lo serializa como **string** (`"40.00"`): la UI lo
normaliza con `Number(...)`.

### 5.3 Catálogo de especialidades

`GET /clinic/specialties` → `200 {"specialties": [{id, nombre}]}`

Devuelve las globales del seed (`tenant_id IS NULL`) **más** las propias del tenant, ordenadas por
`nombre` (y `id` para desempatar). Existe porque el alta de profesional exige `especialidad_id` y el
front no puede hardcodear los UUID5 deterministas del seed: un tenant puede tener sus propias
especialidades. Es la única fuente válida para el `<select>`.

No expone `tenant_id` ni las especialidades de otro tenant.

### 5.4 Disponibilidad

| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| `GET` | `/clinic/availability` | — | `200 {"availability": [AvailabilityOut]}` |
| `POST` | `/clinic/availability` | `AvailabilityIn` | `201 AvailabilityOut` |
| `PATCH` | `/clinic/availability/{id}` | `AvailabilityPatch` | `200 AvailabilityOut` |

`AvailabilityIn`:

```json
{
  "professional_id": null,
  "chair_id": null,
  "dia_semana": 1,
  "hora_inicio": "09:00",
  "hora_fin": "12:00",
  "slot_min": 30,
  "buffer_previo_min": 0,
  "buffer_posterior_min": 0,
  "fecha_desde": "2026-11-16",
  "fecha_hasta": null,
  "tipo_practica": null
}
```

El `PATCH` es parcial y revalida **el estado final**: se mergea el payload sobre la fila, se
reconstruye un `AvailabilityIn` y recién entonces se validan ventana y solape. Un `PATCH` de un solo
campo puede volver inválida la regla, y eso es un `422`.

---

## 6. Validaciones (servicio, antes de escribir)

`backend/app/domain/clinic/validation.py` → `validate_window` devuelve la lista de motivos; el
servicio los convierte en un solo `422 invalid_request` con el primer motivo:

| Regla | Ejemplo que falla |
|---|---|
| `hora_fin > hora_inicio` | `12:00 → 12:00` |
| `hora_fin − hora_inicio` múltiplo exacto de `slot_min` | `09:00–10:10` con `slot_min = 30` |
| `slot_min > 0` | `slot_min = 0` |
| `buffer_previo_min >= 0`, `buffer_posterior_min >= 0` | `-5` |
| `buffer_previo + buffer_posterior < slot_min` | `20 + 20` con `slot_min = 30` |
| `fecha_hasta is null or fecha_hasta >= fecha_desde` | `2026-11-20 → 2026-11-01` |

Solape: antes de insertar, el servicio lee con `FOR UPDATE` las reglas del mismo alcance
(`professional_id`, `chair_id`, `dia_semana`) con fechas que se intersectan y compara las ventanas
con `time_ranges_overlap`. Si hay solape parcial → `409 availability_overlap` y **cero filas nuevas**.
El índice único cubre el caso exacto; el solape parcial no lo puede cubrir un índice.

Referencias cruzadas: `professional_id`, `chair_id` y `especialidad_id` se resuelven **antes** de
escribir. Un id de otro tenant no existe bajo RLS → `404` con el `code` del recurso (nunca `403`,
que confirmaría que existe).

---

## 7. Aislamiento (RN-TEN-02, gate de merge)

`backend/tests/integration/test_clinic_rls.py` (13 tests) corre con `SET ROLE odontologia_app` y el
GUC `app.current_tenant` fijado, porque el superusuario **ignora** RLS y un test con el
superusuario no prueba nada:

1. `SELECT` de las filas de B en las tres tablas devuelve `0`.
2. `UPDATE`/`DELETE` del id de B afecta `0` filas.
3. Fail-closed: sin `app.current_tenant`, las tres tablas devuelven `0` filas y el `INSERT` sin
   `tenant_id` válido es rechazado.
4. `tenant_id` en el body → `422 invalid_request`; `?tenant_id=` y headers con otro tenant se
   ignoran y la operación sigue con el de la sesión.
5. La especialidad de B no se lista y usarla en `POST /professionals` da `404 specialty_not_found`.

**Prueba de mutación** (evidencia en `docs/skills-mcp/evidencias/gate-rls-c-05.md`): con
`ALTER TABLE chair DISABLE ROW LEVEL SECURITY` el mismo test ve `2` filas de otro tenant y falla;
al restaurar `ENABLE ROW LEVEL SECURITY` vuelve a verde. El gate no puede pasar sin la política.

Recordatorio de plataforma: después de `db.commit()` el GUC se limpia, así que no se consulta bajo
RLS después del commit; el contexto se abre en cada transacción con
`SELECT set_config('app.current_tenant', :tenant_id, true)` (`SET LOCAL` no acepta binds).

---

## 8. Pantalla `/clinica`

- Ruta protegida con `<RequirePermission permission="chair.read">`; el enlace "Clínica" de la Home
  aparece solo con ese permiso.
- Cada sección decide qué mostrar con `hasPermission(...)` — nunca comparando `session.roles`
  (lo barre `frontend/src/features/auth/rolesSweep.test.ts`).
- `ChairsSection`: tabla (nombre, tipo, ubicación, estado) y alta si `chair.create`. Con
  `chair.update` el nombre/ubicación se editan inline y aparece "Guardar"; "Dar de baja" solo con
  `chair.delete`.
- `ProfessionalsSection`: alta con el `<select>` lleno por `GET /clinic/specialties`; la baja es
  `PATCH activo = false` con `professional.update`.
- `AvailabilitySection`: alta de reglas con día (`DAY_OPTIONS`, 0 = domingo), horario, slot,
  vigencia y alcance opcional; el solape se muestra como `availability_overlap`.
- Un `403` de la API se muestra como "No tenés permiso para ver esta sección." junto al `code`; un
  error de negocio muestra el mensaje del catálogo y el `code` en monoespaciado.

---

## 9. Demo (guion de 3 minutos para el video)

1. Login `admin@example.test` (clínica `clinica-demo`) → Home → click **Clínica**.
2. **Sillón**: nombre `Sillón 2`, tipo `Rayos X` → "Nuevo sillón" → aparece en la tabla como
   *Activo*. Editar la ubicación → "Guardar" → "Sillón actualizado.".
3. **Profesional**: nombre/apellido/matrícula `MP-2026`, especialidad elegida del catálogo
   (p. ej. `Ortodoncia`) → "Nuevo profesional" → aparece con su matrícula.
4. Repetir la misma matrícula → error **"Ya hay un profesional con esa matrícula."** con
   `professional_matricula_taken`. Es el error de negocio que pide la rúbrica.
5. **Disponibilidad**: día `Lunes`, `09:00–12:00`, `slot_min 30`, vigente desde hoy → "Nueva regla"
   → aparece en la tabla. Repetir la misma ventana → `availability_overlap`.
6. Cerrar sesión y entrar con `demo@example.test` (`professional`): ve "Clínica" y la tabla, pero
   **no** los botones de alta ni de baja. Forzar
   `POST /api/v1/clinic/chairs` desde la consola del navegador devuelve `403 forbidden`.

---

## 10. Orquestación del e2e

`backend/scripts/e2e_server.py` levanta Postgres/Redis (Testcontainers), corre `alembic upgrade head`
y ejecuta `backend/tests/fixtures/seed_auth_e2e.py`. El seed ahora siembra también la configuración
clínica del tenant A:

| Fila | Valor |
|---|---|
| sillón | `Sillón demo` (`consultorio`) |
| profesional | `MP-DEMO-1`, especialidad global `Odontología general`, ligado a `profe@example.test` |

Las filas que crea el spec llevan el prefijo reservado **`E2E-`**; el seed las borra (junto con
`availability_rule` del tenant) antes de sembrar. Sin ese reset, el segundo run chocaría con
`409 chair_name_taken` / `409 professional_matricula_taken`. El tenant B (`clinica-demo-b`) no
tiene configuración clínica: es lo que prueba que la UI no filtra filas de A.

---

## 11. Verificación (salida real, 2026-11-11)

### 11.1 Backend

```text
$ uv run ruff check .
All checks passed!

$ uv run mypy app
Success: no issues found in 60 source files

$ uv run pytest -q
444 passed, 1 warning in 77.14s (0:01:17)
```

Línea base previa a C-05: 334 tests. Este change agrega **110** (los 110 son de C-05; no se borró
ni se salteó ninguno).

### 11.2 Frontend

```text
$ npx tsc -b          # sin salida = limpio
$ npx eslint .        # ✖ 1 problem (0 errors, 1 warning)
$ npx vitest run      # Test Files 12 passed (12) / Tests 67 passed (67)
```

El único warning es el **preexistente** de `components/ui/button.tsx` (`react-refresh` por exportar
`buttonVariants` junto al componente); C-05 no agrega warnings.

### 11.3 e2e (backend + Postgres reales)

```text
$ E2E_WEB_PORT=5180 npx playwright test
15 passed (17.8s)
```

Los 4 nuevos son `frontend/tests/e2e/clinic.spec.ts`; los 11 previos siguen verdes.

### 11.4 Detalle por capa

| Capa | Archivo | Tests |
|---|---|---:|
| Catálogo de errores | `backend/tests/unit/clinic/test_clinic_errors.py` | 12 |
| Validación de ventanas | `backend/tests/unit/clinic/test_validation.py` | 22 |
| Migración `005` | `backend/tests/integration/test_clinic_migration.py` | 11 |
| Sillones | `backend/tests/integration/test_clinic_chairs.py` | 14 |
| Profesionales | `backend/tests/integration/test_clinic_professionals.py` | 15 |
| Catálogo de especialidades | `backend/tests/integration/test_clinic_specialties.py` | 4 |
| Disponibilidad | `backend/tests/integration/test_clinic_availability.py` | 17 |
| Aislamiento cross-tenant (gate) | `backend/tests/integration/test_clinic_rls.py` | 13 |
| Seed e2e (idempotencia + reset) | `backend/tests/integration/test_seed_e2e.py` | 2 |
| UI de las tres secciones | `frontend/src/features/clinic/*.test.tsx` | 20 |
| Rutas | `frontend/src/App.test.tsx`, `./routes/Home.test.tsx` | 6 + 4 |
| e2e | `frontend/tests/e2e/clinic.spec.ts` | 4 |

> Nota de plataforma: `pytest` no acepta dos archivos con el mismo basename sin `__init__.py`. El
> test del catálogo de errores se llama `test_clinic_errors.py` para no colisionar con
> `tests/unit/rbac/test_errors.py`.

---

## 12. Deudas y desviaciones registradas

| Deuda | Motivo |
|---|---|
| `availability_rule` sin recurso propio en la matriz RBAC | Se reutilizan `professional.read`/`professional.update`; agregar `availability.*` es un cambio de matriz (C-04) que no estaba en el alcance |
| `tipo_practica` es `varchar(40)` libre | El catálogo de prácticas llega con facturación; hoy es una etiqueta opcional |
| Solape parcial: concurrencia | La lectura `FOR UPDATE` serializa contra las filas existentes, pero dos `INSERT` simultáneos con alcances distintos que se solapan pueden pasar; el índice único solo frena el duplicado exacto. Aceptado para 1 dev / 1 tenant |
| `GET /chairs/{id}/utilization` no existe | Salió del alcance de C-05; pertenece a la agenda (C-07) |
| RN-AG-06 (capacidad del sillón) sin implementar | Depende de `appointment`; se resuelve en C-07 |
| `specialty` sin RLS | Es catálogo global por diseño (C-02); la visibilidad se valida explícitamente y tiene sus propios escenarios (`S5.4`, `S10.1`–`S10.3`) |
| `mypy app tests` falla por módulos duplicados | Preexistente; el gate real es `mypy app` |
