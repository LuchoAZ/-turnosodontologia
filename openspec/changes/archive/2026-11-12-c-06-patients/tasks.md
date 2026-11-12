# Tasks — c-06-patients

> Estrategia: Strict TDD en cada bloque (RED → GREEN → TRIANGULATE → REFACTOR). Cada task cita los
> escenarios de `specs/clinic/patients/spec.md` (S1.1…S11.5) y `specs/platform-rbac/spec.md`
> (S1.1, S1.3, S1.4, S3.2) que verifica. Antes de tocar archivos existentes se corre su test (safety net) y
> se anota la línea base.

## 1. Matriz RBAC y knowledge base

- [x] 1.1 RED: extender `backend/tests/unit/rbac/test_matrix.py` con la fila `patient` en `KB_TABLE`,
  los escenarios S10.1/S10.2 (owner con las 4 acciones, `front_desk` sin `delete`, `external_lab` sin
  ninguna), S10.3 (rol/permiso fuera del catálogo y lista vacía → conjunto vacío, sin `patient.read`
  por defecto) y los conteos 19 recursos / 61 permisos. Verificación: el test falla por la fila y el
  enum ausentes (safety net de la matriz: 1 test parametrizado + 6 unitarios en verde antes).
- [x] 1.2 GREEN: en `backend/app/domain/rbac/matrix.py` agregar `patient_create/read/update/delete` al
  enum `Permission`, la fila `patient` a `_KB_MATRIX` con `("patient", "CRUD", "CRU", "R", "R", "CRU",
  "R", "—", "—", "—")` y actualizar el docstring a 61 permisos. Verificación: los tests de 1.1 pasan y
  `_NO_PHYSICAL_DELETE` sigue sin incluir `patient`.
- [x] 1.3 Actualizar `knowledge-base/03_actores_y_roles.md` § Recursos estructurales con la fila
  `Pacientes` (misma matriz que `_KB_MATRIX`) y registrar en `knowledge-base/10_preguntas_abiertas.md`
  la **PQ-17** (US-030 pide a recepción capturar alergias/alertas; RN-CMP-04 se lo prohíbe; se difiere
  a C-09). Verificación: la fila de la KB y la de `KB_TABLE` coinciden celda por celda (el test de 1.1
  es la prueba) y la PQ-17 no reutiliza un ID existente.
- [x] 1.4 Verificar que el delta `specs/platform-rbac/spec.md` (MODIFIED) describe el estado final:
  19 recursos, 61 permisos, S1.1 con `patient.*` y S1.3 sin `patient.delete`; y que el segundo
  `MODIFIED` (Fronteras duras clínicas) conserva los 5 escenarios y corrige "se completa en C-06" por
  **C-09**. Verificación: `openspec validate c-06-patients --strict` no reporta errores de delta y el
  diff contra `openspec/specs/platform-rbac/spec.md` solo cambia lo declarado. S3.1/S3.2 se
  re-verifican en 4.6; S3.3–S3.5 no cambian de comportamiento y siguen cubiertos por los tests de
  C-04 (`test_matrix.py`, `test_guard.py`), que deben seguir en verde.

## 2. Modelo y migración `006_patients`

- [x] 2.1 RED: crear `backend/tests/integration/test_patients_migration.py` que sube `006_patients` y
  verifica tablas `patient`/`patient_counter`, enum `sexo_paciente` (4 valores), `UNIQUE (tenant_id,
  numero_historia_clinica)`, índice parcial de DNI, índices de nombre/teléfono/trigram, RLS `ENABLE` +
  `FORCE` y la política en ambas tablas. Verificación: falla porque la migración no existe (safety net:
  `test_migration_reversibility.py` y `test_clinic_migration.py` en verde).
- [x] 2.2 Crear `backend/app/models/patients.py` con `SexoPaciente(StrEnum)`, `Patient` y
  `PatientCounter`, usando `UUIDPrimaryKeyMixin`, `TimestampMixin`, `Base`, `citext` para `email` y
  `JSONB` para `domicilio`; exportarlo donde el `env.py` de Alembic recolecta los modelos. Verificación:
  `uv run mypy app` acepta los modelos y `alembic revision --autogenerate` no detecta diferencias
  (solo se usa como chequeo, la migración se escribe a mano).
- [x] 2.3 Escribir `backend/alembic/versions/006_patients.py` con `CREATE EXTENSION IF NOT EXISTS
  pg_trgm`, el enum, las dos tablas, los índices (incluida la GIN trigram), `GRANT` y RLS con el mismo
  molde de `005_clinic_setup` (`TENANT_PREDICATE`). Verificación: `test_patients_migration.py` en
  verde y `uv run alembic upgrade head` idempotente sobre la base de test.
- [x] 2.4 RED→GREEN del `downgrade()`: baja `patient_counter`, `patient`, `sexo_paciente` y deja
  `pg_trgm` instalada (extensión compartida, igual que `citext`). Verificación: el test de
  reversibilidad vuelve a `005_clinic_setup` y sube otra vez sin error.
- [x] 2.5 Gate RLS (parte 1): `backend/tests/integration/test_patients_rls.py` crea dos tenants y
  verifica que cada uno ve solo sus `patient` y su `patient_counter`. Verificación: el test pasa con
  RLS activa y falla si se desactiva (se completa en 4.9 con la mutación).

## 3. Dominio

- [x] 3.1 RED→GREEN de `backend/app/domain/patients/normalize.py`: `normalizar_texto` (NFKD, sin
  diacríticos, `casefold`, espacios colapsados) y `normalizar_telefono` (solo dígitos). Casos: `Pérez`
  → `perez`, `  ANA   MARÍA ` → `ana maria`, `+54 11 5555-1234` → `541155551234`, cadena vacía → `""`.
  Verificación: unit test con al menos 4 casos por función (triangulación).
- [x] 3.2 RED→GREEN de `backend/app/domain/patients/hce.py`: `formatear_numero(secuencia)` →
  `f"{n:06d}"` y `siguiente_numero_historia_clinica(session, tenant_id)` con el upsert atómico de
  `patient_counter`. Verificación: unit test de formato (`1`→`000001`, `999999`→`999999`,
  `1000000`→`1000000`) e integración de secuencia (S4.1–S4.6). `S4.3` (baja lógica que no recicla)
  setea `deleted_at` por fixture/SQL directo, **no** por HTTP (no hay `DELETE`); `S4.5` monta la
  carrera del mismo DNI con dos sesiones y verifica que la fallida no deja hueco.
- [x] 3.3 RED→GREEN de `backend/app/domain/patients/errors.py`: `PatientErrorCode` con
  `patient_not_found` (404), `patient_dni_duplicado` (409), `patient_posible_duplicado` (409) e
  `invalid_request` (422); `to_payload()` incluye `candidatos` cuando existen. Verificación: unit test
  del catálogo completo y del payload con y sin candidatos.
- [x] 3.4 Implementar el servicio de alta en `backend/app/domain/patients/service.py`: normalizar,
  chequear DNI (duro, **sin** filtrar `deleted_at`) y nombre/teléfono (blando, solo activos, tope de 5
  candidatos, salvo `confirmar_duplicado`), pedir la HCE e insertar en una sola transacción; traducir
  `IntegrityError` de DNI a `patient_dni_duplicado` sin consumir número. Verificación: los escenarios
  S3.*, S5.* y S6.* pasan por HTTP en 4.4.
- [x] 3.5 RED→GREEN del constructor de búsqueda: `escape_like` para `%`, `_` y `\` y el armado del
  `WHERE` con `LIKE ... ESCAPE '\'`. Verificación: unit test con `%`, `_`, `' OR 1=1 --` y `\`.

## 4. API `/api/v1/patients` y tests de integración

- [x] 4.1 RED→GREEN de `app/schemas/patients.py`: `Sexo`, `Domicilio`, `PatientCreate`,
  `PatientUpdate`, `PatientOut`, `PatientListOut`, `PatientCandidate`, todos con `extra="forbid"` y
  `PatientCreate.confirmar_duplicado` fuera de la persistencia. Verificación: unit test de validación
  (S3.4, S3.6, S8.2) y de que `PatientOut` no tiene `tenant_id`, `deleted_at`, `alergias` ni
  `alerta_clinica` (S9.1).
- [x] 4.2 RED→GREEN de `GET /api/v1/patients` con `q`, `limit`, `offset` e `incluir_inactivos`
  (`patient.read`). Verificación: S1.1–S1.6, S2.1–S2.6 y S9.1 (listado sin campos clínicos).
- [x] 4.3 RED→GREEN de `GET /api/v1/patients/{id}` (`patient.read`). Verificación: S7.1–S7.3 y la
  indistinguibilidad 404 de un id ajeno vs. inexistente.
- [x] 4.4 RED→GREEN de `POST /api/v1/patients` (`patient.create`): HCE, dedupe, `201`, `403` y `422`.
  Verificación: S3.1–S3.6, S5.1–S5.6 y S6.1–S6.7.
- [x] 4.5 RED→GREEN de `PATCH /api/v1/patients/{id}` (`patient.update`): actualización parcial,
  recálculo de `*_norm`, DNI duplicado y campos reservados. Verificación: S8.1–S8.6.
- [x] 4.6 Registrar el router en `backend/app/main.py` y el handler de `PatientError`; no tocar el
  router `clinical`. Verificación: `GET /api/v1/clinical/patients` sigue respondiendo `403` a
  recepción y `501` a los roles clínicos (S3.5, S9.2).
- [x] 4.7 Frontera clínica (S9.1–S9.3): test dedicado que recorre las cuatro respuestas y un `POST`
  con `alergias`/`alerta_clinica` → `422`, y que confirma que la columna queda en su default.
- [x] 4.8 Gate de tenancy (S1.5, S2.4, S5.3, S6.5, S7.2, S8.4): un test por cruce de tenant, con
  mutaciones (crear en B, leer desde A).
- [x] 4.9 Gate RLS (parte 2): prueba de mutación en `test_patients_rls.py` — con
  `ALTER TABLE patient DISABLE ROW LEVEL SECURITY` el test cross-tenant debe fallar; se restaura y se
  documenta la salida en `docs/skills-mcp/evidencias/gate-rls-c-06.md`. Verificación: la mutación
  detecta la fuga en `patient` y en `patient_counter`.

## 5. Frontend

- [x] 5.1 RED→GREEN de `src/api/patients.ts` (listar, leer, crear, actualizar) con el cliente httpOnly
  de `clinic.ts` y tipos de los DTO. Verificación: unit test del cliente con `fetch` mockeado
  (query string, `confirmar_duplicado`, propagación de `code`/`candidatos`).
- [x] 5.2 RED→GREEN de `PatientsPage` (buscador, tabla, total) con visibilidad por `patient.read`.
  Verificación: S11.1 y S11.5 (sin permiso no llama al backend ni renderiza datos; `forbidden` se
  informa como falta de permisos).
- [x] 5.3 RED→GREEN de `PatientFormDialog` (alta y edición): validación de campos, `input type="date"`
  con `fireEvent.change`, alta que aparece en la tabla con su HCE. Verificación: S11.2.
- [x] 5.4 RED→GREEN de `DuplicateDialog`: candidatos y "Confirmar alta" que reintenta con
  `confirmar_duplicado=true`; `patient_dni_duplicado` sin diálogo. Verificación: S11.3 y S11.4.
- [x] 5.5 Registrar `/pacientes` en `App.tsx` con la guarda de `patient.read` y el enlace en
  `Home.tsx`. Verificación: test de rutas (con y sin permiso, incluida la acción de edición oculta sin
  `patient.update` según S11.5) y `npx tsc -b` limpio.
- [x] 5.6 e2e `frontend/tests/e2e/patients.spec.ts` (la carpeta real del config es `tests/e2e`):
  login `clinical_admin` → `/pacientes` → búsqueda → alta → el paciente aparece con su HCE; el DNI
  duplicado muestra el error y el POST forzado por `professional` da `403`. Verificación: el spec
  pasa con `E2E_WEB_PORT=5180` (4/4) y el `owner` del seed conserva su flujo en `team.spec.ts`.

## 6. Seed y datos de demo

- [x] 6.1 Extender `backend/tests/fixtures/seed_auth_e2e.py`: borrar los pacientes del tenant e2e con
  `apellido LIKE 'E2E-%'` (prefijo reservado) antes de sembrar, sin resetear `patient_counter`.
  Verificación: `test_seed_e2e.py` sigue en verde (2/2) y dos corridas seguidas del e2e no colisionan.
- [x] 6.2 Sembrar un paciente de demo (`E2E-Paciente, Demo`, DNI reservado `99000111`) para la lista
  y la búsqueda del video. Verificación: el e2e lo encuentra por `?q=demo` y el número de HCE tiene 6
  dígitos; el canónico conserva id y HCE entre corridas (el reset no lo borra).

## 7. Documentación

- [x] 7.1 Escribir `docs/patients.md` con: modelo y migración, contrato de los 4 endpoints, regla de
  HCE (por qué no `MAX+1`, sin huecos y desborde a 7 dígitos), dedupe duro/blando (incluido el DNI de
  un paciente dado de baja), búsqueda normalizada, RLS + prueba de mutación, pantalla `/pacientes`,
  demo paso a paso, verificación y deudas (PQ-17, `patient.delete`, portal, FK simple de `user_id`).
  Verificación: cada escenario de la spec aparece al menos una vez.
- [x] 7.2 Actualizar `README.md` (C-06 archivado, números reales, `docs/patients.md`),
  `CHANGES.md` (C-06 `[x]`, próximo `agendar-turno-sin-solapamiento`, **quitar**
  `GET /patients/:id/timeline` de la línea ~267 y el "Alergias y `alerta_clinica` destacadas" de la
  línea ~270, que son C-09), `AGENTS.md`/`CLAUDE.md` (ruta `C-01…C-06`, 61 permisos) y
  `docs/entrega/resumen-entrega.txt` (6 changes). Verificación: no quedan menciones a C-06 como
  pendiente ni a funcionalidad que el change declara fuera de alcance.

## 8. Gates y cierre

- [x] 8.1 Ejecutar la skill `spec-scenario-review` sobre `proposal.md`, `design.md`, `specs/**` y
  `tasks.md`, y guardar el veredicto con la tabla de cobertura por requisito y el check de tenancy en
  `docs/skills-mcp/evidencias/revision-c-06-pre-apply.md`. Verificación: cada requisito con ≥3
  escenarios (esperado, error de negocio, borde) y cada escenario con una task; sin bloqueantes.
- [x] 8.2 Pipeline completo: `uv run ruff check .`, `uv run mypy app`, `uv run pytest -q`,
  `npx eslint .`, `npx tsc -b`, `npx vitest run` y el e2e. Anotar los números en `docs/patients.md` y
  en el README. Verificación: cero fallos nuevos respecto de la línea base (444 back / 67 front / 15
  e2e) y ningún test borrado o salteado.
- [x] 8.3 Gate pre-archive: volver a correr `spec-scenario-review` contra lo implementado y guardar
  `docs/skills-mcp/evidencias/revision-c-06-pre-archive.md` con la correspondencia escenario → test
  ejecutado. Verificación: ningún escenario sin prueba.
- [x] 8.4 Cerrar el change: `openspec validate c-06-patients --strict`, marcar todas las tasks,
  `openspec archive c-06-patients --yes` y verificar que `openspec/specs/clinic/patients/spec.md`
  existe y que `platform-rbac` quedó con 19 recursos/61 permisos. Verificación:
  `openspec validate --specs --strict` y `--archived --strict` en verde.
