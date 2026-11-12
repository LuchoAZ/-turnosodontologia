# Design — c-06-patients

## Contexto

C-02 dejó `tenant`, `user`, `membership`, `specialty`, `price_concept` y `currency` con RLS fail-closed
y el rol `odontologia_app`. C-03 agregó la sesión y la resolución del tenant desde el token. C-04
agregó la matriz de permisos, la guarda `require_permission` y las sondas de frontera clínica. C-05
agregó sillones, profesionales y disponibilidad. Este change agrega la **ficha del paciente** y la
**secuencia de historia clínica**, y reutiliza esos cimientos sin reabrirlos.

## D1 — Rutas, DTOs y cadena de guardas

```
GET    /api/v1/patients                 patient.read
GET    /api/v1/patients/{id}            patient.read
POST   /api/v1/patients                 patient.create
PATCH  /api/v1/patients/{id}            patient.update
```

- **No hay `DELETE`.** La baja lógica con justificación (Ley 25.326, RN-EX-03) es de C-13; exponerla
  ahora obligaría a inventar el motivo, la auditoría y el derecho de supresión en el mismo change. El
  permiso `patient.delete` sí se declara (D2) para que la matriz no cambie dos veces.
- Todos los DTO usan `model_config = ConfigDict(extra="forbid")`. El `tenant_id` sale de
  `require_auth` → `require_tenant` (C-03/C-04); nunca del cuerpo ni del query.
- El `422` de body inválido lo traduce el handler global de `RequestValidationError` a
  `invalid_request`, igual que en C-05.
- La sonda `GET /api/v1/clinical/patients` **se queda como está**: exige `clinical_record.read`
  (historia clínica) y pertenece a C-09. La ficha de C-06 es un recurso **administrativo** distinto.
  Esta separación es la que permite que recepción administre pacientes sin ver la HC (RN-CMP-04).

## D2 — Matriz RBAC: fila `patient`

`knowledge-base/03_actores_y_roles.md` no tiene fila de pacientes. US-030 pone el alta en recepción y
RN-CMP-04 le prohíbe la HC, así que la ficha demográfica es un recurso propio y no una celda de
`clinical_record`. Se agrega la fila:

| Recurso | Owner | Dir. clínica | Odontólogo | Higienista | Recepción | Administración | Paciente | Lab. | Contador |
|---|---|---|---|---|---|---|---|---|---|
| Pacientes | C R U D | C R U | R | R | C R U | R | — | — | — |

Consecuencias:

- `patient.create/read/update` habilitan el flujo de US-030 en recepción y dirección clínica.
- `patient.delete` queda declarado pero **sin endpoint** hasta C-13. Es baja lógica, así que `patient`
  **no** entra en `_NO_PHYSICAL_DELETE` (esa tupla es para historia clínica y odontograma, RN-CMP-02).
- El rol `patient` (portal) **no** recibe nada de esta fila: no existe `patient.read_own` todavía; el
  portal del paciente es post-deadline y se anota como deuda.
- El catálogo pasa de **18 a 19 recursos** y de **57 a 61 permisos**. Se actualizan
  `_KB_MATRIX`, `KB_TABLE`, `test_catalogo_de_recursos_y_enum_coherentes`, el requisito S1.1/S1.3 de
  `platform-rbac` (delta `MODIFIED`) y los conteos de `docs/rbac.md`, `README.md` y `AGENTS.md`.
- `_NOT_CLINICAL` no toca `patient.*`: recepción conserva su acceso demográfico y sigue sin
  `clinical_record.read`/`chart.read`.

## D3 — Modelo y migración `006_patients`

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TYPE sexo_paciente AS ENUM ('femenino','masculino','otro','no_declara');

patient(
  id uuid pk default gen_random_uuid(),
  tenant_id uuid not null references tenant(id) on delete cascade,
  user_id uuid null references "user"(id) on delete set null,  -- portal (post-deadline); ningún DTO lo escribe
  dni varchar(11) null,
  nombre varchar(80) not null,
  apellido varchar(80) not null,
  apellido_norm varchar(80) not null,
  nombre_norm varchar(80) not null,
  fecha_nacimiento date null,
  sexo sexo_paciente null,
  telefono varchar(32) not null,
  telefono_norm varchar(32) not null,
  email citext null,
  domicilio jsonb null,
  obra_social_id uuid null,                    -- catálogo fuera de v0.1: sin FK
  numero_historia_clinica varchar(20) not null,
  alergias text null,                          -- existe, NO se expone en C-06
  alerta_clinica boolean not null default false, -- existe, NO se expone en C-06
  activo boolean not null default true,
  deleted_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, numero_historia_clinica)
);

CREATE UNIQUE INDEX uq_patient_dni ON patient (tenant_id, dni) WHERE dni IS NOT NULL;
CREATE INDEX ix_patient_nombre ON patient (tenant_id, apellido_norm, nombre_norm);
CREATE INDEX ix_patient_telefono ON patient (tenant_id, telefono_norm);
CREATE INDEX ix_patient_nombre_trgm ON patient
  USING gin (apellido_norm gin_trgm_ops, nombre_norm gin_trgm_ops);
CREATE INDEX ix_patient_activos ON patient (tenant_id) WHERE deleted_at IS NULL;

patient_counter(
  tenant_id uuid primary key references tenant(id) on delete cascade,
  ultimo_numero integer not null default 0,
  updated_at timestamptz not null default now()
);
```

- **Columnas `*_norm`**: son una denormalización de búsqueda y dedupe, no campos de dominio; no se
  exponen en `PatientOut`. Se calculan en la aplicación (D5) porque `unaccent` es `STABLE` y no se
  puede indexar, y porque normalizar en Python es determinístico y testeable sin extensiones extra.
- **`pg_trgm`**: acelera `ILIKE '%q%'` sobre las columnas normalizadas. Se crea igual que `citext` en
  `002_core_tenancy` y **no se elimina en el downgrade** (extensión compartida; dropearla podría romper
  otros objetos). El test de reversibilidad solo exige que las tablas y el enum desaparezcan.
- **`patient_counter` es una tabla de negocio**: tiene `tenant_id`, así que lleva RLS `FORCE`, política
  y grants como `patient`.
- RLS y grants, con el mismo molde de `005_clinic_setup`:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON patient TO odontologia_app;
GRANT SELECT, INSERT, UPDATE ON patient_counter TO odontologia_app;
ALTER TABLE patient ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient FORCE ROW LEVEL SECURITY;
CREATE POLICY patient_tenant_isolation ON patient FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
-- idem patient_counter
```

- `obra_social_id` se persiste **sin FK** porque el catálogo de obras sociales no existe en v0.1 (misma
  deuda explícita que tuvo `membership.professional_id` hasta C-05).
- `user_id` enlaza con el portal del paciente y queda **nullable y sin escritores**: ningún DTO de C-06
  lo acepta (los DTO son `extra="forbid"`), así que no puede usarse para apuntar a un usuario de otro
  tenant. La FK es simple porque `user` es global (`uq_user_email`), no tenant-scoped; si el portal se
  implementa, se evalúa una FK compuesta `(tenant_id, user_id)` o validación de dominio. Deuda
  registrada en `docs/patients.md`.

## D4 — Número de historia clínica secuencial y no reciclable

El número se toma de `patient_counter` con un upsert atómico:

```sql
INSERT INTO patient_counter (tenant_id, ultimo_numero) VALUES (:tid, 1)
ON CONFLICT (tenant_id) DO UPDATE
  SET ultimo_numero = patient_counter.ultimo_numero + 1,
      updated_at = now()
RETURNING ultimo_numero;
```

- **Por qué no `MAX(numero) + 1`**: si el paciente con el número más alto se da de baja lógica, `MAX`
  lo sigue viendo (la fila queda), pero cualquier borrado físico o una migración de datos podría
  liberarlo. El contador es independiente de las filas y **solo avanza** (RN-CLI-01).
- **Formato**: `f"{secuencia:06d}"` → `000001`; si supera `999999`, crece a 7 dígitos sin romper la
  columna `varchar(20)`.
- **Concurrencia**: el `ON CONFLICT DO UPDATE` toma un lock de fila sobre el contador. Dos
  transacciones del mismo tenant se serializan y obtienen números distintos; `UNIQUE (tenant_id,
  numero_historia_clinica)` es la red de seguridad.
- **Orden de la transacción**: validar → chequear duplicados → incrementar el contador → insertar el
  paciente → commit. Si un chequeo falla **antes** del upsert, el contador no avanza; si el `INSERT`
  choca con el índice único por una carrera, se captura `IntegrityError` y se traduce a
  `patient_dni_duplicado`, y la transacción revierte el incremento (sin huecos).

## D5 — Normalización, dedupe y búsqueda

`app/domain/patients/normalize.py`:

```python
def normalizar_texto(valor: str) -> str:
    # NFKD → quita diacríticos → casefold → colapsa espacios
def normalizar_telefono(valor: str) -> str:
    # solo dígitos
```

- **Dedupe duro por DNI**: consulta explícita `WHERE tenant_id = :tid AND dni = :dni` antes de crear
  (para devolver el candidato con un `409` legible) + índice único parcial como backstop.
  `confirmar_duplicado` **no** lo vence. La consulta **no** filtra por `deleted_at`: el DNI de un
  paciente dado de baja sigue bloqueando (el índice tampoco filtra), así que un DNI nunca se recicla
  (S5.6). Si dos altas pasan el chequeo a la vez, el que pierde el `INSERT` captura `IntegrityError` y
  responde `409 patient_dni_duplicado`, no `500` (S5.5).
- **Dedupe blando**: `WHERE deleted_at IS NULL AND (apellido_norm = :ap AND nombre_norm = :nom OR
  telefono_norm = :tel)`. Solo mira **pacientes activos**: un homónimo dado de baja no dispara la
  confirmación (S6.6). Si hay filas y `confirmar_duplicado = false` → `409
  patient_posible_duplicado` con **hasta 5** candidatos (`ORDER BY ... LIMIT 5`, S6.7). Con `true` →
  crea.
- **Búsqueda**: `q` se normaliza; se arma `pat = "%" + escape_like(q_norm) + "%"` (se escapan `%`, `_`
  y `\`) y se consulta:

```sql
WHERE tenant_id = :tid AND deleted_at IS NULL
  AND (apellido_norm LIKE :pat ESCAPE '\'
       OR nombre_norm LIKE :pat ESCAPE '\'
       OR dni = :q_digitos
       OR telefono_norm LIKE :tel_pat ESCAPE '\')
```

- Los `ILIKE`-equivalentes se hacen sobre columnas ya normalizadas; la GIN trigram acelera el `LIKE`.
- `q` vacío → sin filtro; `q` de más de 60 caracteres → `422 invalid_request` (validación de Pydantic
  antes de tocar la base).

## D6 — Errores

`app/domain/patients/errors.py`, mismo shape que `ClinicError`:

| code | status | cuándo |
|---|---|---|
| `patient_not_found` | 404 | id propio inexistente **o** de otro tenant (indistinguibles) |
| `patient_dni_duplicado` | 409 | DNI ya usado en el tenant; incluye el candidato |
| `patient_posible_duplicado` | 409 | nombre/teléfono normalizado coincide; incluye `candidatos[]` |
| `invalid_request` | 422 | body inválido o campo reservado |

`PatientError.to_payload()` agrega `candidatos` cuando existe. `forbidden` **no** vive acá: lo emite la
guarda de RBAC. El handler se registra en `app/main.py` junto a los de `AuthError`/`RbacError`/
`ClinicError`.

## D7 — Schemas

- `Sexo(StrEnum)` espeja el enum de la base (`femenino`, `masculino`, `otro`, `no_declara`).
- `Domicilio(BaseModel)` con `calle`, `numero`, `localidad`, `provincia`, `codigo_postal` opcionales y
  `extra="forbid"`; se persiste como JSONB.
- `PatientCreate`: `nombre` y `apellido` (1–80, se recortan), `telefono` (1–32, obligatorio), `dni`
  (`^\d{7,11}$`, opcional), `fecha_nacimiento`, `sexo`, `email` (`EmailStr`), `domicilio`,
  `confirmar_duplicado: bool = False` (control, no se persiste).
- `PatientUpdate`: los mismos campos, todos opcionales; `model_dump(exclude_unset=True)` distingue
  "no enviado" de `null`.
- `PatientOut`: `id`, `numero_historia_clinica`, `nombre`, `apellido`, `dni`, `fecha_nacimiento`,
  `sexo`, `telefono`, `email`, `domicilio`, `activo`, `created_at`, `updated_at`. **Sin** `tenant_id`,
  `deleted_at`, `alergias`, `alerta_clinica`, `*_norm`.
- `PatientListOut`: `{"patients": [...], "total": int}`.
- `PatientCandidate`: `id`, `numero_historia_clinica`, `nombre`, `apellido`, `dni`, `telefono`.

## D8 — Frontend

- `src/api/patients.ts`: `listPatients`, `getPatient`, `createPatient`, `updatePatient` sobre el mismo
  cliente httpOnly de `src/api/clinic.ts`; tipados con los DTO del backend; los `409` se propagan con
  `code` y `candidatos`.
- `src/features/patients/`: `PatientsPage.tsx` (buscador + tabla + acciones), `PatientFormDialog.tsx`
  (alta/edición), `DuplicateDialog.tsx` (candidatos + "Confirmar alta" con
  `confirmar_duplicado=true`), `errors.ts` (mapa `code` → mensaje).
- La búsqueda se dispara con el botón "Buscar" o Enter (sin debounce) para que los tests sean
  deterministas; el `q` se recorta antes de enviarlo.
- Visibilidad por permiso: sin `patient.read` la ruta muestra "sin permisos"; sin `patient.create` no
  se renderiza el alta; sin `patient.update`, la acción de edición no aparece. **Nunca** se compara el
  rol.
- `App.tsx` registra `/pacientes` con la misma guarda de ruta de `/clinica`; `Home.tsx` muestra el
  enlace con `patient.read`.

## D9 — Seed y tests

- **Integración**: cada test crea su tenant con `seeder.tenant()`; el contador arranca en 1 y los tests
  de secuencia son deterministas. Los tests de concurrencia usan dos sesiones/transacciones reales.
- **Seed e2e**: borra los pacientes de los tenants e2e cuyo `apellido` empieza con `E2E-` (prefijo
  reservado, mismo criterio que `Sillón demo`/`MP-DEMO-1` de C-05) y **no** resetea el contador; el e2e
  asserta formato de 6 dígitos y unicidad, no el valor exacto.
- **Gate RLS**: `test_patients_rls.py` repite el molde de `test_clinic_rls.py`, con la prueba de
  mutación (`ALTER TABLE patient DISABLE ROW LEVEL SECURITY` → el test cross-tenant debe fallar). La
  evidencia se guarda en `docs/skills-mcp/evidencias/gate-rls-c-06.md`.
- **Reversibilidad**: `test_patients_migration.py` sube y baja `006_patients` contra Postgres real y
  verifica que `patient`, `patient_counter` y `sexo_paciente` desaparezcan.

## D10 — Deudas registradas

1. **US-030 vs RN-CMP-04**: US-030 pide a recepción capturar `alergias` y `alerta_clinica`, pero
   RN-CMP-04 le prohíbe la HC. C-06 guarda las columnas pero **no** las expone; la captura clínica
   pasa a C-09 con el permiso correcto. Se registra como PQ-17 en `10_preguntas_abiertas.md`.
2. **`patient.delete` sin endpoint**: el permiso existe para C-13 (baja con justificación y auditoría).
3. **`obra_social_id` sin catálogo ni FK**: se persiste nullable para la migración de datos.
4. **Portal del paciente**: `patient.read_own` y la identidad OTP+DNI son post-deadline.
5. **Auditoría de lecturas**: leer una ficha demográfica no se audita en C-06; la auditoría de accesos
   sensibles es de C-13.
6. **Búsqueda por acentos**: se resuelve con columnas normalizadas en la aplicación; si en el futuro
   se quiere consultar por SQL crudo con acentos, se evalúa `unaccent` con una función `IMMUTABLE`.
