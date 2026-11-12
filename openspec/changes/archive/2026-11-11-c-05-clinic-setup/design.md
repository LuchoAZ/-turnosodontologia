# Design — c-05-clinic-setup

## Contexto

C-02 dejó `tenant`, `user`, `membership`, `specialty`, `price_concept` y `currency` con RLS fail-closed
y el rol `odontologia_app`. C-03 agregó sesión y resolución de tenant desde el token. C-04 agregó la
matriz de permisos y la guarda `require_permission`. Este change agrega los tres recursos que la agenda
necesita reservar y **reutiliza** esos tres cimientos sin reabrirlos.

## D1 — Rutas, DTOs y cadena de guardas

Prefijo único `/api/v1/clinic` con tres sub-recursos: `chairs`, `professionals`, `availability`.

```
GET    /api/v1/clinic/chairs                 chair.read
POST   /api/v1/clinic/chairs                 chair.create
PATCH  /api/v1/clinic/chairs/{id}            chair.update
DELETE /api/v1/clinic/chairs/{id}            chair.delete     → baja lógica (204)

GET    /api/v1/clinic/professionals          professional.read
POST   /api/v1/clinic/professionals          professional.create
PATCH  /api/v1/clinic/professionals/{id}     professional.update   (incluye activo=false)

GET    /api/v1/clinic/specialties            professional.read

GET    /api/v1/clinic/availability           professional.read
POST   /api/v1/clinic/availability           professional.update
PATCH  /api/v1/clinic/availability/{id}      professional.update
```

Todos los DTOs de entrada usan `model_config = ConfigDict(extra="forbid")`. El `tenant_id` nunca se lee
del cliente: sale de `require_auth` + `require_tenant` (mismo mecanismo que C-04) y el `422` de body
invalido ya lo traduce el handler global de `RequestValidationError` a `invalid_request`.

`DELETE` de sillón **no** borra: es el nombre HTTP de la baja lógica. La decisión evita inventar un
verbo (`POST /chairs/{id}/deactivate`) y mantiene el contrato REST del roadmap.

## D2 — Permisos: se usan los de la matriz, no se inventa un recurso

`knowledge-base/03_actores_y_roles.md` no declara un recurso `availability`. En vez de expandir la
matriz (que es un artefacto de C-04 y ya está sincronizada en `platform-rbac`), las reglas de
disponibilidad se **administran como configuración del profesional**: leerlas exige
`professional.read` y escribirlas `professional.update`. Queda registrado en `docs/clinic.md` como
deuda: si la KB incorpora el recurso, la migración de permisos es un agregado a `ROLE_PERMISSIONS`.

Consecuencia práctica: `front_desk`, `assistant` y `professional` **leen** la configuración; solo
`owner` y `clinical_admin` escriben sillones/profesionales/reglas; solo `owner` da de baja un sillón
(`chair.delete`).

## D3 — Modelo de datos y migración `005_clinic_setup`

```sql
CREATE TYPE chair_tipo AS ENUM ('consultorio','rx','cirugia','higiene','otro');

chair(
  id uuid pk default gen_random_uuid(),
  tenant_id uuid not null references tenant(id) on delete cascade,
  nombre varchar(60) not null,
  tipo chair_tipo not null,
  activo boolean not null default true,
  ubicacion varchar(120) null,
  equipamiento jsonb not null default '{}'::jsonb,
  unique (tenant_id, nombre)
);

professional(
  id uuid pk default gen_random_uuid(),
  tenant_id uuid not null references tenant(id) on delete cascade,
  user_id uuid null references "user"(id) on delete set null,
  nombre varchar(80) not null,
  apellido varchar(80) not null,
  matricula varchar(32) not null,
  especialidad_id uuid not null references specialty(id),
  porcentaje_liquidacion numeric(5,2) not null default 0 check (between 0 and 100),
  duracion_default_min integer not null default 30 check (between 5 and 480),
  color_agenda varchar(7) not null default '#2563EB',
  activo boolean not null default true,
  unique (tenant_id, matricula)
);

availability_rule(
  id uuid pk default gen_random_uuid(),
  tenant_id uuid not null references tenant(id) on delete cascade,
  professional_id uuid null references professional(id) on delete cascade,
  chair_id uuid null references chair(id) on delete cascade,
  dia_semana smallint not null check (between 0 and 6),
  hora_inicio time not null,
  hora_fin time not null check (hora_fin > hora_inicio),
  slot_min integer not null default 30 check (> 0),
  buffer_previo_min integer not null default 0 check (>= 0),
  buffer_posterior_min integer not null default 0 check (>= 0),
  fecha_desde date not null,
  fecha_hasta date null check (fecha_hasta >= fecha_desde),
  tipo_practica varchar(40) null,
  unique nulls not distinct (tenant_id, professional_id, chair_id, dia_semana, fecha_desde)
);
```

- Los `CHECK` de rango viven en la base **además** de Pydantic: la API es la primera barrera, el DDL la
  última (mismo criterio que RN-AG-02).
- `unique ... nulls not distinct` (Postgres 16) evita duplicar exactamente la misma regla cuando
  `professional_id` o `chair_id` son `NULL`; el solape **parcial** de horarios lo valida el servicio
  (D6).
- `tipo_practica` queda como `varchar(40)` y no como FK: la KB no cierra el enum ni lo liga a
  `price_concept` (que no tiene duración). Deuda anotada; la agenda lo resolverá.
- Política RLS idéntica a `membership` en las tres tablas:

```sql
ALTER TABLE chair ENABLE ROW LEVEL SECURITY;
ALTER TABLE chair FORCE ROW LEVEL SECURITY;
CREATE POLICY chair_tenant_isolation ON chair
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
```

`specialty` **no** tiene RLS (es catálogo con filas globales `tenant_id NULL`): por eso el servicio
valida visibilidad con una consulta explícita `tenant_id IS NULL OR tenant_id = :tid` antes de escribir.

## D4 — Bajas lógicas y permisos asimétricos

| Recurso | Permiso de baja | Verbo | Efecto |
|---|---|---|---|
| `chair` | `chair.delete` | `DELETE /chairs/{id}` | `activo = false`, fila intacta, idempotente |
| `professional` | `professional.update` | `PATCH /professionals/{id}` con `activo: false` | fila intacta, reglas intactas |

No hay `DELETE` físico en ninguna de las tres tablas. `availability_rule` no tiene baja propia: se
"retira" con `PATCH` (`fecha_hasta`) porque no tiene columna `activo` en la KB.

## D5 — Validación de ventana (función pura)

`app/domain/clinic/validation.py` recibe `hora_inicio`, `hora_fin`, `slot_min`, buffers y
`fecha_desde/fecha_hasta`, y devuelve `list[str]` de motivos (vacía = válido):

1. `hora_fin > hora_inicio` (estricto; 12:00→12:00 inválido).
2. `slot_min > 0` y múltiplo exacto: `(hora_fin - hora_inicio) % slot_min == 0`.
3. `buffer_previo_min >= 0` y `buffer_posterior_min >= 0`.
4. `buffer_previo_min + buffer_posterior_min < slot_min`: un turno con buffers debe caber en su slot.
5. `fecha_hasta is None or fecha_hasta >= fecha_desde`.

Es pura y testeable sin base: es la unidad del ciclo RED→GREEN de las tasks 2.x, y el servicio la usa
como precondición antes de tocar la base.

## D6 — Solape de reglas del mismo alcance

"Alcance" = `(professional_id, chair_id)`, con `NULL` significando "todos". Dos reglas se solapan si
coinciden en `dia_semana`, sus rangos `[fecha_desde, fecha_hasta]` se intersectan (con `NULL` =
infinito) y sus ventanas horarias se tocan (`inicio < otra.fin AND fin > otra.inicio`).

El servicio consulta las reglas del tenant con `FOR UPDATE` sobre las filas del mismo alcance y día,
calcula el solape en Python y responde `409 availability_overlap`. La garantía dura contra duplicados
exactos la da el índice único; el solape parcial es una regla de negocio (no una restricción de rango
continua, porque `dia_semana` + `time` + `daterange` no se expresan con un `EXCLUDE` simple sin
`btree_gist` sobre columnas nullable).

**Limitación registrada**: dos creaciones concurrentes de reglas parcialmente solapadas podrían pasar
ambas si no existe aún ninguna fila que bloqueen; la ventana es de milisegundos y la corrección es
idempotente (PATCH), no destructiva. Se documenta en `docs/clinic.md`; el gate de concurrencia real
llega con la agenda, que es quien reserva.

## D7 — Catálogo de errores `ClinicErrorCode`

Mismo shape que `RbacErrorCode` (`{code, message}`) y mismo handler global para `422`:

| `code` | HTTP | Cuándo |
|---|---|---|
| `forbidden` | 403 | Reutilizado de `RbacErrorCode`: falta el permiso |
| `chair_not_found` | 404 | Sillón inexistente **en este tenant** |
| `chair_name_taken` | 409 | `(tenant_id, nombre)` ya existe |
| `professional_not_found` | 404 | Profesional inexistente en este tenant |
| `professional_matricula_taken` | 409 | `(tenant_id, matricula)` ya existe |
| `specialty_not_found` | 404 | Especialidad inexistente o de otro tenant (indistinguible) |
| `user_not_member` | 422 | `user_id` sin membership activa en el tenant |
| `availability_not_found` | 404 | Regla inexistente en este tenant |
| `availability_overlap` | 409 | Regla solapada con otra del mismo alcance y día |
| `invalid_request` | 422 | Body inválido o campo no declarado |

El `403` sale de la guarda de C-04 (no se duplica el catálogo); el resto vive en
`app/domain/clinic/errors.py`. Un único `exception_handler` para `ClinicError` en `app/main.py`.

## D8 — Frontend: pantalla única, tres secciones

- `src/api/clinic.ts`: `listChairs`, `createChair`, `updateChair`, `deactivateChair`, `listProfessionals`,
  `createProfessional`, `updateProfessional`, `listSpecialties`, `listAvailability`, `createAvailability`,
  `updateAvailability`. Tipos derivados a mano del contrato (el OpenAPI es la fuente). El alta de
  profesional toma `especialidad_id` del catálogo (`GET /specialties`), nunca de un valor hardcodeado:
  los ids del seed son UUID5 deterministas pero los tenants pueden tener especialidades propias.
- `src/features/clinic/ClinicPage.tsx` + secciones `ChairsSection`, `ProfessionalsSection`,
  `AvailabilitySection`. Cada botón se muestra con `hasPermission(...)`; **prohibido** comparar
  `session.roles` (lo vigila `rolesSweep.test.ts`).
- Ruta `/clinica` envuelta en `<RequirePermission permission="chair.read">`; enlace en la Home con el
  mismo permiso.
- `src/features/clinic/errors.ts`: mapa `code → mensaje` (mismo patrón que `Login.tsx`), de modo que un
  `409 availability_overlap` explique el solape sin mostrar el `message` del backend si cambia.
- `ASSIGNABLE`-style constants (tipos de sillón, etiquetas) viven en
  `src/features/clinic/catalog.ts`, fuera del módulo mockeado por los tests. Las especialidades **no**
  son constantes: se leen de `GET /specialties` porque un tenant puede tener las suyas.

## D9 — Estrategia de tests (Strict TDD, Postgres real)

| Capa | Archivo | Qué congela |
|---|---|---|
| Unidad | `tests/unit/clinic/test_validation.py` | Ventana, buffers, múltiplo del slot, fechas |
| Unidad | `tests/unit/clinic/test_errors.py` | Los 9 `code` y su status |
| Integración | `tests/integration/test_clinic_chairs.py` | Alta, duplicado, PATCH, baja idempotente, 403 |
| Integración | `tests/integration/test_clinic_professionals.py` | Matrícula única, especialidad, `user_not_member`, baja |
| Integración | `tests/integration/test_clinic_availability.py` | Ventanas inválidas, solape, alcance `null`, 404 ajeno |
| Integración (gate) | `tests/integration/test_clinic_rls.py` | Cross-tenant SQL y HTTP + mutación de RLS |
| Frontend | `src/features/clinic/*.test.tsx` | Render por permiso, errores por `code`, enlace en Home |
| e2e | `frontend/tests/e2e/clinic.spec.ts` | Alta real de sillón y profesional contra el backend |

Sin mocks de base: el engine de los tests es el mismo `odontologia_app` bajo RLS. Las sesiones se
emiten con `create_access_token` (patrón de `test_auth_me`), porque las pruebas son de autorización y
no del flujo de MFA.

## D10 — Riesgos y deudas

| Riesgo / deuda | Mitigación |
|---|---|
| Solape concurrente de reglas (D6) | Ventana mínima, PATCH idempotente, documentado |
| `tipo_practica` sin catálogo cerrado | `varchar(40)` + deuda en `docs/clinic.md`; agenda decide |
| `specialty` sin RLS | Validación explícita `tenant_id IS NULL OR = :tid` en el servicio |
| RN-AG-06 no se puede validar sin turnos | Se documenta que se activa en C-07; el modelo no la contradice |
| `membership.professional_id` sigue `NULL` | Fuera de alcance; se completa en el flujo "mi agenda" |
| `GET /chairs/{id}/utilization` | Necesita `appointment`; se implementa con la agenda |
