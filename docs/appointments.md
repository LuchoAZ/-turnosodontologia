# Agenda — alta de turno sin solapamiento (`agendar-turno-sin-solapamiento`)

> Change: `agendar-turno-sin-solapamiento` (archivado el 2026-11-12). Migración: `007_agenda`.
> Pantalla: `/turnos/nuevo`.
> Ruta: `POST /api/v1/appointments` (1 endpoint). Este change entrega **solo el alta**:
> disponibilidad, reserva y cancelación quedan fuera (§8).

---

## 1. Qué se entrega

| Capa | Archivo |
|---|---|
| Modelo | `backend/app/models/agenda.py` (`Appointment`, `AppointmentEstado`, `AppointmentOrigen`) |
| Migración | `backend/alembic/versions/007_agenda.py` |
| Dominio | `backend/app/domain/agenda/appointments/{range,service,errors}.py` |
| Esquemas | `backend/app/schemas/appointments.py` (`CreateAppointment`, `AppointmentOut`, `TipoPractica`) |
| API | `backend/app/api/v1/agenda/router.py`, handler de `AgendaError` en `backend/app/main.py` |
| Frontend | `frontend/src/api/appointments.ts`, `frontend/src/features/agenda/*` |
| Pantalla | ruta `/turnos/nuevo` en `frontend/src/App.tsx`, enlace en `frontend/src/routes/Home.tsx` |
| Tests | `backend/tests/unit/agenda/test_appointments.py`, `backend/tests/integration/test_appointments_*.py` (6 suites) + `test_agenda_migration.py`, `frontend/src/features/agenda/*.test.ts(x)`, `frontend/tests/e2e/appointments.spec.ts` |
| Gate RN-TEN-02 | `backend/tests/integration/test_appointments_rls.py` + `docs/skills-mcp/evidencias/gate-rls-agenda.md` |

La pantalla exige `appointment.create` (guarda en el router + `RequirePermission` en el SPA). El
`tenant_id` **no** se declara en el request: sale de la sesión (RN-TEN-03).

Lo que este change **no** hace: listar turnos, reprogramar, cancelar, registrar llegada/atención,
recordatorios, portal del paciente, y el motor completo de disponibilidad (ventana horaria ya está en
`resolve_turno_range`, pero no se expone como consulta de slots). Todo eso está en CHANGES.md
(`C-07` y posteriores).

---

## 2. Modelo

### 2.1 `appointment`

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK `gen_random_uuid()` |
| `tenant_id` | uuid | FK `tenant` `ON DELETE CASCADE`, `NOT NULL` |
| `patient_id` | uuid | FK `patient` `ON DELETE SET NULL`; **nullable** = turno sin paciente identificado |
| `professional_id` | uuid | FK `professional` `ON DELETE CASCADE`, `NOT NULL` |
| `chair_id` | uuid | FK `chair` `ON DELETE CASCADE`, `NOT NULL` |
| `inicio`, `fin` | timestamptz | `NOT NULL`; `inicio` en UTC; `fin > inicio` por `ck_appointment_fin_posterior_a_inicio` |
| `duracion_min` | integer | `NOT NULL`; derivada en el servidor (RN-AG-03) |
| `buffer_previo_min`, `buffer_posterior_min` | smallint | `NOT NULL DEFAULT 0`; snapshot de la regla aplicable |
| `estado` | enum `appointment_estado` | `pendiente` al crear (también `confirmado`, `en_curso`, `atendido`, `cancelado`, `no_asistio`, `reprogramado`) |
| `tipo_practica` | varchar(40) | nullable; catálogo code-owned `TipoPractica` (10 valores) |
| `origen` | enum `appointment_origen` | fijo `recepcion` en este change |
| `creado_por` | uuid | FK `user` `ON DELETE SET NULL`; lo pasa el router desde la sesión, nunca el body |
| `motivo`, `cancelado_motivo`, `recordatorio_*`, `version`, `created_at`, `updated_at` | — | existen para los changes siguientes; este no los expone |

### 2.2 La garantía dura: `EXCLUDE USING gist` por recurso

```sql
ALTER TABLE appointment
ADD CONSTRAINT ex_appointment_professional_no_overlap
EXCLUDE USING gist (
    tenant_id WITH =,
    professional_id WITH =,
    tsrange(
        (inicio AT TIME ZONE 'UTC') - make_interval(mins => buffer_previo_min),
        (fin    AT TIME ZONE 'UTC') + make_interval(mins => buffer_posterior_min)
    ) WITH &&
)
WHERE (estado NOT IN ('cancelado', 'no_asistio'));
```

Ídem `ex_appointment_chair_no_overlap` sobre `chair_id`. Es la garantía **de la base**: ni el
pre-chequeo de la aplicación ni una carrera entre dos requests pueden crear el doble booking
(RN-AG-02). El `tenant_id WITH =` dentro del `EXCLUDE` hace que los turnos de dos tenants **nunca**
se comparen entre sí.

**Desviación técnica declarada (verificada con Postgres 16).** El design D2 pedía
`tstzrange(inicio - make_interval(...), ...)`. Es imposible en un índice:
`timestamptz - interval` es `STABLE` (depende del `TimeZone` de la sesión) y Postgres responde
*«functions in index expression must be marked IMMUTABLE»*. Se usa `tsrange` sobre marcas UTC
(`AT TIME ZONE 'UTC'` es inmutable): compara exactamente los mismos instantes y conserva el rango
semiabierto, así que `nuevo.inicio == existente.fin` **no** es solape.

`btree_gist` se crea en esta migración y **no** se dropea en el `downgrade` (extensión compartida,
igual que `pg_trgm` en `006_patients`).

### 2.3 RLS

`ENABLE` + `FORCE ROW LEVEL SECURITY`, política
`USING/WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)` y
grants `SELECT/INSERT/UPDATE/DELETE` a `odontologia_app`. El servicio **además** filtra `tenant_id` en
todas sus consultas: con RLS activa es redundante, pero el `404` no depende del error de la base y la
mutación del gate lo demuestra (ver §7).

### 2.4 Índices

| Índice | Para qué |
|---|---|
| `ix_appointment_tenant_inicio` | agenda diaria por tenant |
| `ix_appointment_patient_inicio` | RN-AG-10 y futura historia del paciente |
| `ix_appointment_estado_activos` (parcial, `WHERE estado NOT IN ('cancelado','no_asistio')`) | pre-chequeo de solape sobre turnos que bloquean |
| `ex_appointment_{professional,chair}_no_overlap` | la garantía dura |

---

## 3. Contrato del endpoint

### 3.1 Request

```http
POST /api/v1/appointments
Content-Type: application/json
Cookie: access_token=…; refresh_token=…
```

```json
{
  "professional_id": "0a0d1f2e-…",
  "chair_id": "1b2c3d4e-…",
  "patient_id": "2c3d4e5f-…",
  "inicio": "2026-11-16T09:00:00-03:00",
  "tipo_practica": "limpieza"
}
```

| Campo | Tipo | Regla |
|---|---|---|
| `professional_id` | uuid | obligatorio |
| `chair_id` | uuid | obligatorio |
| `patient_id` | uuid \| null | opcional; `null` = sin paciente identificado (RN-AG-10 no aplica) |
| `inicio` | RFC 3339 **con offset** | obligatorio; `AwareDatetime`: sin offset es `422` (RN-AG-09) |
| `tipo_practica` | enum `TipoPractica` | opcional; fuera del catálogo es `422` |

`extra = "forbid"`: `fin`, `duracion_min`, `estado`, `origen` o cualquier campo desconocido → `422
invalid_request`. `tenant_id` en el body **se descarta antes de validar** (no es `422`), y el `query`
ni el header se leen: el tenant sale del token (RN-TEN-03).

### 3.2 Response `201`

```json
{
  "id": "9f8e7d6c-…",
  "professional_id": "0a0d1f2e-…",
  "chair_id": "1b2c3d4e-…",
  "patient_id": "2c3d4e5f-…",
  "inicio": "2026-11-16T12:00:00Z",
  "fin": "2026-11-16T12:30:00Z",
  "duracion_min": 30,
  "buffer_previo_min": 0,
  "buffer_posterior_min": 0,
  "estado": "pendiente",
  "origen": "recepcion",
  "tipo_practica": "limpieza"
}
```

`inicio`/`fin` se devuelven en UTC. La respuesta **nunca** incluye `tenant_id` ni `creado_por`.

### 3.3 Errores

| Status | `code` | Cuándo | Campos extra |
|---|---|---|---|
| `401` | `not_authenticated` | sin sesión o sin membership activa (lo emite C-03) | — |
| `403` | `forbidden` | sesión sin `appointment.create` (guarda de RBAC, C-04) | — |
| `404` | `recurso_no_encontrado` | profesional, sillón o paciente inexistente **o de otro tenant** (RN-EX-06: indistinguible) | `recurso` |
| `409` | `recurso_inactivo` | `professional.activo = false` o `chair.activo = false` | `recurso`, `motivo` |
| `409` | `duracion_invalida` | duración derivada `<= 0` (regla o `duracion_default_min` inválidos) | `recurso`, `motivo` |
| `409` | `paciente_solapado` | RN-AG-10: mismo paciente + mismo profesional, turno activo solapado | `recurso: "patient"`, `motivo`, `rangoEnConflicto` |
| `409` | `turno_solapado` | RN-AG-02: solape de profesional o de sillón (pre-chequeo **o** `EXCLUDE`) | `recurso` (`professional`\|`chair`), `motivo`, `rangoEnConflicto` |
| `422` | `invalid_request` | body inválido: campo faltante, uuid mal formado, `inicio` sin offset, campo desconocido | `errors` (detalle de Pydantic) |

Shape del `409`:

```json
{
  "code": "turno_solapado",
  "message": "El horario se solapa con otro turno del mismo recurso.",
  "recurso": "professional",
  "motivo": "turno_solapado",
  "rangoEnConflicto": { "inicio": "2026-11-16T12:00:00Z", "fin": "2026-11-16T12:30:00Z" }
}
```

`rangoEnConflicto` trae los extremos del turno **que ganó**, no los del intento: es el dato que la UI
necesita para decir «se solapa con el turno de 09:00 a 09:30».

### 3.4 Orden de las validaciones (contrato de precedencia)

1. **Scoping de recursos** → `404 recurso_no_encontrado` (profesional, sillón, paciente).
2. **Recurso activo** → `409 recurso_inactivo`.
3. **Rango del turno** (`resolve_turno_range`) → `409 duracion_invalida`.
4. **RN-AG-10** (`paciente_solapado`) — **antes** que el solape de recursos.
5. **Solape de recursos**: primero `professional`, después `chair` → `409 turno_solapado`.
6. `INSERT` dentro de un `SAVEPOINT`; una *exclusion violation* (`SQLSTATE 23P01`) se traduce al
   **mismo** `409 turno_solapado` del paso 5, con el `recurso` que nombra el constraint.

El paso 4 antes del 5 es deliberado: si el mismo paciente choca contra el mismo profesional, el
mensaje accionable es «el paciente ya tiene un turno», no «el sillón está ocupado».

### 3.5 Cálculo del rango (`backend/app/domain/agenda/appointments/range.py`)

* **Duración base**: `slot_min` de la `availability_rule` aplicable **que declara el `tipo_practica`**;
  si ninguna lo declara (o no hay regla), `professional.duracion_default_min`.
* **Buffers**: snapshot de la regla aplicable **aunque no declare el tipo** (son tiempo real de
  higiene/esterilización, RN-AG-03). Sin regla: `0/0`.
* **Regla aplicable**: la que matchea profesional (o `NULL` = cualquiera), sillón (o `NULL`),
  `dia_semana` de la fecha **en la zona del tenant** y rango `fecha_desde`/`fecha_hasta`.
* **Rango clínico**: `[inicio, fin)` con `fin = inicio + duracion_min`.
* **Rango bloqueado**: `[inicio - buffer_previo, fin + buffer_posterior)`, el que usan el pre-chequeo
  y el `EXCLUDE`.

Es una función **pura** (sin ORM, sin base, sin reloj): es el seam de TDD del change.

---

## 4. Reglas de negocio citadas

| Regla | Cómo se aplica acá |
|---|---|
| **RN-AG-02** | Un profesional y un sillón no pueden tener dos turnos solapados: `EXCLUDE USING gist` + pre-chequeo. Turnos `cancelado`/`no_asistio` no bloquean. |
| **RN-AG-03** | `fin`, `duracion_min` y los buffers los deriva el servidor de la disponibilidad; el cliente no los manda. |
| **RN-AG-09** | `inicio` viaja como instante RFC 3339 **con offset**; el servidor normaliza a UTC y nunca asume su zona. |
| **RN-AG-10** | El mismo paciente no puede tener dos turnos solapados con el mismo profesional (estados `pendiente`/`confirmado`/`en_curso`). |
| **RN-EX-06** | Un recurso inexistente o de otro tenant responde `404`, nunca `403`: no se filtra la existencia de recursos ajenos. |
| **RN-TEN-02** | `tenant_id` en todas las consultas + RLS `FORCE` + `tenant_id` dentro del `EXCLUDE`. Sin filtro de tenant no hay verde: gate de merge. |
| **RN-TEN-03** | El tenant sale del token/sesión; `tenant_id` en body/query/header se ignora. |

---

## 5. Ejemplos ejecutables (curl)

Con el backend arriba en `http://127.0.0.1:8000` y una cuenta de recepción
(`front_desk`, que tiene `appointment.create`) sembrada por el seed de dev:

```bash
# 1) Login: deja las cookies de sesión en cookies.txt
curl -s -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"tenant_slug":"clinica-demo","email":"desk@example.test","password":"demo-password-123"}' \
  http://127.0.0.1:8000/api/v1/auth/login

# 2) Alta de un turno (201). El servidor deriva fin = inicio + 30 min
curl -s -b cookies.txt -H 'Content-Type: application/json' \
  -d '{"professional_id":"<uuid>","chair_id":"<uuid>","patient_id":"<uuid>","inicio":"2026-11-16T09:00:00-03:00"}' \
  http://127.0.0.1:8000/api/v1/appointments

# 3) Mismo horario otra vez (409 turno_solapado con recurso y rangoEnConflicto)
curl -s -o - -w '\n%{http_code}\n' -b cookies.txt -H 'Content-Type: application/json' \
  -d '{"professional_id":"<uuid>","chair_id":"<uuid>","patient_id":null,"inicio":"2026-11-16T09:15:00-03:00"}' \
  http://127.0.0.1:8000/api/v1/appointments

# 4) Campo que no existe (422 invalid_request)
curl -s -b cookies.txt -H 'Content-Type: application/json' \
  -d '{"professional_id":"<uuid>","chair_id":"<uuid>","inicio":"2026-11-16T09:00:00-03:00","duracion_min":15}' \
  http://127.0.0.1:8000/api/v1/appointments
```

Los `<uuid>` salen de `GET /api/v1/clinic/professionals`, `GET /api/v1/clinic/chairs` y
`GET /api/v1/patients` con la misma cookie.

---

## 6. Frontend

Ruta `/turnos/nuevo` (`frontend/src/features/agenda/NewAppointmentPage.tsx`), protegida con
`RequirePermission permission="appointment.create"` y enlazada desde la home con la misma condición.

* **Carga en paralelo**: `Promise.all([listPatients, listProfessionals, listChairs])`. Sin waterfalls.
* **Solo activos**: los recursos dados de baja no se ofrecen; si llegaran igual, el `409
  recurso_inactivo` se muestra tal cual.
* **RN-AG-09**: `localDateTimeToInstant(fecha, hora)` (`datetime.ts`) convierte la hora de pared del
  `<input>` al instante UTC con la zona **del navegador** y devuelve `null` para una fecha imposible
  (`2026-02-31`). Función pura, con 13 tests TZ-agnósticos: no depende de la zona del runner.
* **Contrato**: no se envían `fin`, `duracion_min`, `estado` ni `origen`.
* **Errores por `code`** (`errors.ts`): el `409` muestra recurso («profesional», «sillón», «paciente»)
  y el rango del turno que ganó; el `404` «no existe en esta clínica o no tenés acceso»; el `422`
  «revisá los datos» conservando lo cargado; el `403` remite a la pantalla de acceso denegado.
* **Duplicados de red**: `asApiError` vive en `src/api/http.ts` (lo comparten pacientes y agenda).

Supuesto declarado: la sesión (`SessionOut`) **no** expone `tenant.timezone`, así que el formulario
interpreta la hora de pared en la zona del navegador (la del equipo que agenda). Si el navegador está
en otra zona que la clínica, el instante se corre; queda anotado como límite para el change que
exponga la zona del tenant en la sesión.

---

## 7. Verificación

### 7.1 Pipeline completo (PowerShell, desde la raíz del repo)

```powershell
# Backend
cd backend
uv run ruff check app tests
uv run mypy app
uv run pytest -q

# Frontend
cd ..\frontend
npm run lint
npx tsc -b
npx vitest run

# e2e (backend real: Testcontainers + Alembic + seed + Vite)
$env:E2E_WEB_PORT = '5180'
npx playwright test
```

Requiere Docker corriendo (Postgres 16 y Redis 7 por Testcontainers).

### 7.2 Qué cubre cada suite

| Suite | Casos | Qué fija |
|---|---|---|
| `tests/unit/agenda/test_appointments.py` | 18 | schema (offset obligatorio, `extra=forbid`, `tenant_id` descartado), `resolve_turno_range` (regla vs default, buffers, contiguo, `<= 0`) |
| `tests/integration/test_agenda_migration.py` | 12 | la migración `007_agenda`: columnas y enums, RLS `FORCE` + política, `EXCLUDE` por profesional y sillón, `CHECK (fin > inicio)`, índices, grants, fail-closed sin contexto de tenant e inserts de solape/contiguo/cancelado/buffer |
| `tests/integration/test_appointments_service.py` | 1 | concurrencia real (dos `create` simultáneos): el `EXCLUDE` rechaza el segundo con `SQLSTATE 23P01` y se mapea al `409 turno_solapado` |
| `tests/integration/test_appointments_http.py` | 14 | `201` (contrato completo, UTC, sin `tenant_id`), `401`, `403`, `422`, cruce de medianoche |
| `tests/integration/test_appointments_overlap.py` | 7 | solape por profesional y por sillón, estados que no bloquean, contiguo, buffer posterior |
| `tests/integration/test_appointments_resources.py` | 4 | `404` por recurso inexistente, `409 recurso_inactivo` |
| `tests/integration/test_appointments_patient_rule.py` | 8 | RN-AG-10 (estados, otro profesional, otro rango, `patient_id = NULL`) y su precedencia |
| `tests/integration/test_appointments_rls.py` | 8 | gate RN-TEN-02: scoping de recursos, `tenant_id` ajeno en body/query/header, turnos homólogos, rol de app |
| `frontend/src/features/agenda/datetime.test.ts` | 13 | ida y vuelta hora de pared ↔ UTC, fechas imposibles, formato del rango |
| `frontend/src/features/agenda/NewAppointmentPage.test.tsx` | 14 | opciones activas, alta sin `fin`/`duracion_min`, `409`/`404`/`422`/`403`, permisos |
| `frontend/tests/e2e/appointments.spec.ts` | 5 | alta real con duración derivada, solape visible, RN-AG-10 primero, `403`, `404` |

### 7.3 Gate de aislamiento cross-tenant (bloqueante)

`tests/integration/test_appointments_rls.py` corre con `SET ROLE odontologia_app`. La evidencia
incluye la **prueba de mutación**: con RLS apagada y los 5 filtros `tenant_id` del servicio quitados,
la suite se pone roja (5 failed) y el caso `[professional_id]` **crea** el turno con el UUID ajeno
(`assert 201 == 404`); restaurado, vuelve a `8 passed`. Detalle en
`docs/skills-mcp/evidencias/gate-rls-agenda.md`. Sin este gate verde el change no se archiva.

---

## 8. Límites, desviaciones y supuestos

1. **`EXCLUDE` sobre `tsrange`** en vez de `tstzrange` (§2.2): imposible de otra forma en un índice.
   Mismos instantes, rango semiabierto. Verificado con Postgres 16.
2. **Precedencia declarada en la spec (RN-AG-10 vs RN-AG-02).** Con `patient_id = NULL` y otro turno
   solapado del mismo `professional`, RN-AG-10 no se evalúa (`paciente_solapado` nunca aparece), pero
   RN-AG-02 sigue siendo regla dura: responde `409 turno_solapado`. La delta de la spec se corrigió en
   el gate pre-archive (`docs/skills-mcp/evidencias/revision-agendar-turno-pre-archive.md`): ya no pide
   el `201` imposible.
3. **`duracion_invalida` es defensiva.** Los `CHECK` vigentes
   (`duracion_default_min BETWEEN 5 AND 480`, `slot_min > 0`) la hacen inalcanzable por API; el test
   HTTP muta el esquema (drop/re-add del `CHECK`) y lo restaura en `finally`. Se conserva como guarda
   por si un change futuro relaja los `CHECK`.
4. **Zona horaria del form.** Ver §6: el navegador aporta la zona. `SessionOut` no expone
   `tenant.timezone` todavía.
5. **`tipo_practica` es catálogo code-owned** (`TipoPractica`, `StrEnum`) y la columna es
   `varchar(40)`: un valor nuevo no requiere migración, pero tampoco hay tabla de tipos (llega con el
   catálogo clínico).
6. **Un endpoint, un slice.** Listar, reprogramar y cancelar no están en este change (§1).
