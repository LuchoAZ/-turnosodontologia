# Tasks — c-05-clinic-setup

> **Prerrequisitos (no son tasks de este change)**: C-01…C-04 archivados — `tenant`/`user`/`membership`
> con RLS `FORCE`, `specialty` sembrada, `set_tenant_context`, `require_auth`/`require_tenant`,
> `require_permission` y la matriz con `chair.*` / `professional.*`. Este change **no** toca la matriz
> de permisos, **no** crea `appointment` y **no** implementa `GET /chairs/{id}/utilization`.
>
> **Regla de trabajo**: Strict TDD. Cada tarea `RED` escribe el test que falla y lo confirma en rojo
> antes de la `GREEN`. Todo test que toque las tablas nuevas corre con Postgres real (Testcontainers)
> y `SET ROLE odontologia_app`: el superusuario ignora RLS y un test con el superusuario no prueba nada.
>
> **Recordatorio de plataforma**: después de `db.commit()` el GUC `app.current_tenant` se limpia; no
> consultar bajo RLS después del commit. `SET LOCAL` no acepta binds → `SELECT set_config(...)`.

## 1. Modelos y migración `005_clinic_setup`

- [x] 1.1 RED: escribir en `backend/tests/integration/test_clinic_migration.py` el test de esquema
  que falla si no existen las tablas `chair`, `professional`, `availability_rule`, el enum
  `chair_tipo` con sus 5 valores, los índices únicos `uq_chair_tenant_nombre` y
  `uq_professional_tenant_matricula`, y `pg_constraint` con los `CHECK` de rangos. Verificación:
  `uv run pytest tests/integration/test_clinic_migration.py -q` en rojo por `UndefinedTable`.
- [x] 1.2 GREEN: crear `backend/app/models/clinic.py` con `ChairTipo(StrEnum)`, `Chair`,
  `Professional` y `AvailabilityRule` (UUID PK, `TimestampMixin` solo si la tabla lo justifica,
  `tenant_id` NOT NULL con FK `ondelete="CASCADE"`). Registrarlos en `backend/app/models/__init__.py`.
  Verificación: `uv run python -c "import app.models.clinic"` y `uv run mypy app` limpio.
- [x] 1.3 RED→GREEN: escribir en el mismo test la verificación de que `alembic upgrade head` crea las
  tres tablas y que `downgrade` de `005` las elimina sin tocar `specialty`. Implementar
  `backend/alembic/versions/005_clinic_setup.py` con `down_revision = "004_rbac"` (o el head real),
  el `CREATE TYPE chair_tipo`, las tres tablas, los índices, los `CHECK` y las FK. Verificación:
  el test de reversibilidad pasa y `uv run alembic upgrade head` + `downgrade -1` + `upgrade head`
  corren limpios.
- [x] 1.4 RED→GREEN: en `test_clinic_migration.py` verificar RLS: `relrowsecurity` y
  `relforcerowsecurity` en `true` para las tres tablas y una política por tabla con predicado
  `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid` en `USING` **y**
  `WITH CHECK`. Agregar al `005` las políticas y los grants a `odontologia_app` (patrón de
  `002_core_tenancy`). Verificación: el test lee `pg_policies` y falla si falta `FORCE` o el
  `WITH CHECK`.

## 2. Catálogo de errores y validación pura (sin base de datos)

- [x] 2.1 RED: escribir `backend/tests/unit/clinic/test_errors.py` con los 9 `code` de
  `ClinicErrorCode` y su status (`chair_not_found` 404, `chair_name_taken` 409,
  `professional_not_found` 404, `professional_matricula_taken` 409, `specialty_not_found` 404,
  `user_not_member` 422, `availability_not_found` 404, `availability_overlap` 409,
  `invalid_request` 422) y el payload `{code, message}` sin datos del recurso. Verificar que falla
  (no existe el módulo).
- [x] 2.2 GREEN: crear `backend/app/domain/clinic/errors.py` con `ClinicErrorCode`, `CLINIC_ERROR_STATUS`,
  mensajes en español rioplatense y la excepción `ClinicError`. Registrar el `exception_handler` en
  `app/main.py`. Verificación: `uv run pytest tests/unit/clinic/test_errors.py -q` en verde.
- [x] 2.3 RED: escribir `backend/tests/unit/clinic/test_validation.py` con los casos de
  `validate_window`: ventana de 09:00–12:00 con `slot_min = 30` válida; `12:00→12:00` y `13:00→12:00`
  inválidas; `09:00–10:10` con `slot_min = 30` inválida por no ser múltiplo; `slot_min = 0` inválida;
  buffers negativos inválidos; `buffer_previo + buffer_posterior >= slot_min` inválido; `fecha_hasta`
  anterior a `fecha_desde` inválida. Verificar rojo.
- [x] 2.4 GREEN: crear `backend/app/domain/clinic/validation.py` con `validate_window(...) -> list[str]`
  (pura, sin imports de DB) y `ranges_overlap(a, b) -> bool` para el solape de reglas. Verificación:
  2.3 en verde y `uv run mypy app` limpio.
- [x] 2.5 RED→GREEN: agregar a `test_validation.py` los bordes de `ranges_overlap`: mismo día con
  `fecha_hasta` `None` (infinito) contra un rango cerrado, rangos disjuntos, rangos que se tocan en el
  extremo (`fin == inicio` no es solape) y ventanas horarias idénticas. Verificación: los 4 casos
  pasan y la función no muta sus argumentos.

## 3. API de sillones

- [x] 3.1 RED: escribir `backend/tests/integration/test_clinic_chairs.py` con lectura
  (`S1.1` lista ordenada sin `tenant_id` e incluye inactivos; `S1.2` `403 forbidden` sin
  `chair.read`; `S1.3` lista vacía con `200`), usando sesiones emitidas con `create_access_token`
  (patrón de `test_auth_me`). Verificar rojo por `404` en la ruta.
- [x] 3.2 GREEN: crear `app/schemas/clinic.py` (`ChairIn`, `ChairPatch`, `ChairOut` con
  `extra="forbid"`), `app/domain/clinic/service.py::list_chairs` y
  `app/api/v1/clinic/router.py::GET /chairs` con `require_permission(Permission.CHAIR_READ)`.
  Registrar el router en `app/main.py`. Verificación: 3.1 en verde.
- [x] 3.3 RED→GREEN: alta de sillón (`S2.1` `201` con `equipamiento` intacto, `S2.2` duplicado
  `409 chair_name_taken` y la cantidad no cambia, `S2.3` tipo inválido `422 invalid_request` sin ecoar
  el valor, `S2.4` dos `rx` conviven con `201`, `S2.5` mismo nombre en otro tenant `201`). Implementar
  `POST /chairs` con `chair.create`, `activo` forzado en `true` y `tenant_id` de la sesión.
  Verificación: los 5 escenarios en verde.
- [x] 3.4 RED→GREEN: `PATCH /chairs/{id}` (`S3.1` actualiza `ubicacion`/`equipamiento`; `S3.5`
  `404 chair_not_found` indistinguible para un id de otro tenant y para un UUID aleatorio).
  Implementar con `chair.update` y `UPDATE ... WHERE id = :id` bajo RLS.
  Verificación: ambos escenarios en verde y el sillón ajeno sin cambios.
- [x] 3.5 RED→GREEN: baja lógica (`S3.2` `DELETE` `204` con `activo = false` y fila viva, `S3.3`
  repetir es idempotente `204`, `S3.4` `clinical_admin` recibe `403 forbidden` y el sillón sigue
  activo). Implementar `DELETE /chairs/{id}` con `chair.delete` como `UPDATE activo = false`.
  Verificación: los 3 escenarios en verde.

## 4. API de profesionales

- [x] 4.1 RED: escribir `backend/tests/integration/test_clinic_professionals.py` con lectura
  (`S4.1` matrícula + `especialidad.nombre` + `duracion_default_min`, sin `tenant_id`; `S4.2` `403`
  sin `professional.read`; `S4.3` externo con `user_id: null`). Verificar rojo.
- [x] 4.2 GREEN: implementar `GET /professionals` (join a `specialty`, orden por `apellido`, `nombre`)
  con `professional.read`. Verificación: 4.1 en verde.
- [x] 4.3 RED→GREEN: alta (`S5.1` `201` con especialidad resuelta, `S5.2` matrícula repetida
  `409 professional_matricula_taken`, `S5.3` `duracion_default_min = 0` y
  `porcentaje_liquidacion = 120` → `422 invalid_request` sin fila escrita, `S5.6` misma matrícula en
  otro tenant `201`). Implementar `POST /professionals` con `professional.create` y los rangos en
  Pydantic **y** en el DDL.
- [x] 4.4 RED→GREEN: validación de `especialidad_id` (`S5.4` inexistente y de otro tenant →
  `404 specialty_not_found`, indistinguibles) con consulta explícita
  `tenant_id IS NULL OR tenant_id = :tid` (la tabla no tiene RLS). Verificación: el test cubre los dos
  casos con el mismo status y código.
- [x] 4.5 RED→GREEN: validación de `user_id` (`S5.5` sin membership activa → `422 user_not_member`,
  sin fila creada; membership inactiva también se rechaza). Implementar la consulta a `membership`
  bajo RLS del tenant.
- [x] 4.6 RED→GREEN: desactivación (`S6.1` `PATCH activo = false` conserva matrícula y especialidad,
  `S6.2` `front_desk` `403` sin cambios, `S6.3` las reglas de disponibilidad siguen visibles,
  `S6.4` id de otro tenant → `404 professional_not_found`). Implementar `PATCH /professionals/{id}` con
  `professional.update`; **no** crear `professional.delete`.
- [x] 4.7 RED→GREEN: catálogo visible de especialidades (`S10.1` el `GET` devuelve las globales del seed
  y las propias del tenant, ordenadas por `nombre`, sin `tenant_id`; `S10.2` sin `professional.read` →
  `403 forbidden`; `S10.3` la especialidad propia de otro tenant no se lista y usarla en
  `POST /professionals` → `404 specialty_not_found` sin fila). Implementar
  `service.list_specialties` con `tenant_id IS NULL OR tenant_id = :tid` (la tabla **no** tiene RLS),
  `SpecialtyListOut` y `GET /specialties` con `professional.read`. Es lo que consume el alta de
  profesional: el front no hardcodea los UUID5 del seed. Verificación: los 3 escenarios en verde.

## 5. API de disponibilidad

- [x] 5.1 RED: escribir `backend/tests/integration/test_clinic_availability.py` con el alta feliz
  (`S7.1` buffers y `slot_min` persistidos sin cambios) y la lectura con `professional.read`.
  Verificar rojo.
- [x] 5.2 GREEN: implementar `GET /availability` y `POST /availability` usando
  `validate_window` **antes** de tocar la base (no se escribe fila inválida). Verificación: 5.1 en verde.
- [x] 5.3 RED→GREEN: ventanas inválidas (`S7.2` `12:00→12:00` y fin anterior, `S7.3` 09:00–10:10 con
  `slot_min = 30` con mensaje que explique el múltiplo, `S7.4` buffers negativos y `slot_min = 0`,
  `S7.8` `fecha_hasta < fecha_desde`) → `422 invalid_request` y cero filas nuevas.
- [x] 5.4 RED→GREEN: solape (`S7.5` profesional P lunes 09:00–12:00 y otra 11:00–14:00 con fechas que
  se intersectan → `409 availability_overlap` y la primera intacta). Implementar en el servicio la
  consulta `FOR UPDATE` de las reglas del mismo alcance y día + `ranges_overlap`. Documentar la
  limitación de concurrencia en `docs/clinic.md`.
- [x] 5.5 RED→GREEN: alcance `null` (`S7.6` regla con `professional_id: null` → `201` y se lista sin
  profesional) y duplicado exacto rechazado por el índice único
  `unique nulls not distinct (tenant_id, professional_id, chair_id, dia_semana, fecha_desde)`.
- [x] 5.6 RED→GREEN: referencias ajenas (`S7.7` `professional_id` o `chair_id` de otro tenant →
  `404 professional_not_found` / `chair_not_found` y sin fila). Implementar la resolución previa de
  ambas referencias bajo RLS.
- [x] 5.7 RED→GREEN: `PATCH /availability/{id}` con `professional.update` (`200` al mover la ventana a
  un horario libre, `409 availability_overlap` cuando choca con otra regla, `404 availability_not_found`
  para id ajeno o inexistente). Verificación: los 3 casos en verde.

## 6. Gate de aislamiento cross-tenant (RN-TEN-02, bloqueante de merge)

- [x] 6.1 RED: escribir `backend/tests/integration/test_clinic_rls.py` con el patrón de
  `test_team_rls.py`: con `SET ROLE odontologia_app` y contexto del tenant A, `SELECT` de las filas de
  B en las tres tablas devuelve `0`; `UPDATE`/`DELETE` del id de B afecta `0` filas
  (`S8.1`, `S8.2`). Verificar rojo si falta alguna política.
- [x] 6.2 GREEN: completar lo que falte en `005` y en el servicio hasta que 6.1 pase. Verificación:
  los conteos son `0` y los endpoints responden `404` con el `code` del recurso.
- [x] 6.3 RED→GREEN: fail-closed (`S8.3` sin `app.current_tenant` fijado las tres tablas devuelven `0`
  filas y un `INSERT` sin `tenant_id` válido es rechazado) y `S8.4` `tenant_id` en el body →
  `422 invalid_request` sin fila, mientras que `?tenant_id=` o un header con otro tenant se ignoran y
  la operación sigue con el de la sesión.
- [x] 6.4 Prueba de mutación del gate: quitar temporalmente la política de `chair`, correr 6.1 y
  confirmar que **falla**; restaurarla y confirmar verde. Anotar el resultado en
  `docs/skills-mcp/evidencias/`. Verificación: el gate no puede pasar sin la política.

## 7. Frontend `/clinica`

- [x] 7.1 RED: escribir `frontend/src/features/clinic/ChairsSection.test.tsx` con render por permiso
  (`chair.read` lista, `chair.create` muestra "Nuevo sillón", `chair.delete` muestra la baja) y el
  error de negocio mostrado por `code` (`chair_name_taken`). Verificar rojo.
- [x] 7.2 GREEN: crear `frontend/src/api/clinic.ts` (las 11 funciones del contrato, `listSpecialties`
  incluida) y `frontend/src/features/clinic/catalog.ts` (tipos de sillón fuera del módulo mockeado),
  más `errors.ts` con el mapa `code → mensaje`. Implementar `ChairsSection` con `hasPermission`, nunca
  comparando `session.roles`. Verificación: 7.1 en verde y `npx tsc -b` limpio.
- [x] 7.3 RED→GREEN: `ProfessionalsSection.test.tsx` y `AvailabilitySection.test.tsx` (alta, matrícula
  repetida, ventana inválida y solape) con el mismo patrón. El `<select>` de especialidad se llena con
  `listSpecialties` (nunca con ids fijos) y sin el permiso de lectura del catálogo la sección no
  ofrece el alta. Verificación: ambas suites en verde.
- [x] 7.4 RED→GREEN: `ClinicPage.test.tsx` con `S9.1` (con `chair.read` se ven las tres secciones),
  `S9.2` (sin `chair.read`: "No tenés permiso para ver esta sección."), `S9.3` (`clinical_admin` ve
  "Nuevo sillón" y "Guardar" pero no la baja) y el `403` de la API mostrado como acceso denegado.
- [x] 7.5 RED→GREEN: ruta `/clinica` envuelta en `<RequirePermission permission="chair.read">` y enlace
  en la Home condicionado al mismo permiso; extender `Home.test.tsx` con el enlace presente/ausente.
  Verificación: `npx vitest run` en verde y sin claves `roles` comparadas
  (`rolesSweep.test.ts` sigue pasando).

## 8. Seed y e2e del flujo

- [x] 8.1 RED: escribir `frontend/tests/e2e/clinic.spec.ts` con el flujo real contra el backend: login
  → `/clinica` → alta de sillón → aparece en la tabla → alta de profesional con la especialidad
  sembrada → aparece con su matrícula → el intento de repetir la matrícula muestra el error. Verificar
  rojo (la ruta no existe).
- [x] 8.2 GREEN: extender `backend/tests/fixtures/seed_auth_e2e.py` con un sillón y un profesional del
  tenant de prueba (idempotente, limpieza en `finally` como el resto del seed) y hacer pasar el spec.
  Verificación: `npx playwright test tests/e2e/clinic.spec.ts` en verde con
  `E2E_WEB_PORT=5180` si 5173 está ocupado.
- [x] 8.3 RED→GREEN: `backend/tests/integration/test_seed_e2e.py` verifica el seed nuevo sin dejar
  usuarios ni filas sueltas (limpieza en `finally`); correrlo dos veces seguidas para confirmar
  idempotencia. Verificación: segunda corrida en verde.

## 9. Documentación, pipeline y cierre

- [x] 9.1 Escribir `docs/clinic.md` con el contrato de los 11 endpoints, la tabla de permisos usados,
  el catálogo `ClinicErrorCode`, la demo del flujo (sillón → profesional → disponibilidad) y la
  sección de verificación con los números reales de la corrida. Incluir las deudas: `availability` sin
  recurso propio en la matriz, `tipo_practica` sin catálogo, solape concurrente de reglas y
  RN-AG-06 pendiente de `appointment`.
- [x] 9.2 Ejecutar el gate `spec-scenario-review` sobre `proposal.md`, `design.md`, `specs/**` y
  `tasks.md` y guardar el veredicto en `docs/skills-mcp/evidencias/revision-c-05-pre-apply.md` con la
  tabla de cobertura por requisito y el check de tenancy. Verificación: cada requisito con ≥3
  escenarios y cada escenario con una tarea ejecutada; sin bloqueantes.
- [x] 9.3 Pipeline completo: `uv run ruff check .`, `uv run mypy app`, `uv run pytest -q`,
  `npx eslint .`, `npx tsc -b`, `npx vitest run` y los e2e. Anotar los números en `docs/clinic.md` §
  verificación y en el README. Verificación: cero fallos nuevos respecto de la línea base (334
  back / 43 front / 11 e2e) y ningún test borrado o salteado.
- [x] 9.4 Actualizar `README.md` (C-05 verificado, ruta del Sprint, `docs/clinic.md`, evidencias) y
  `CHANGES.md` (C-05 `[x]` con gate cumplido). Verificación: no quedan menciones a `utilization` como
  parte de C-05.
- [x] 9.5 Cerrar el change: `openspec validate c-05-clinic-setup --strict`, marcar todas las tasks,
  `openspec archive c-05-clinic-setup --yes` y verificar que `openspec/specs/clinic-setup/spec.md`
  quede sincronizada. Verificación: `openspec validate --specs --strict` sin errores.
