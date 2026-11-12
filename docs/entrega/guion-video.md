# Guion del video — TPI Metodología I

**Duración objetivo**: 9–10 minutos · **Formato**: grabación de pantalla + voz · **Integrantes**: 1
**Proyecto**: Gestión Odontológica PyME (`odontologia-saas`) · **Entrega**: 2026-11-20

> Regla del video: mostrar **evidencia ejecutada**, no diapositivas. Cada bloque termina con un
> archivo, un comando o una salida de terminal que se pueda verificar en el repo.

---

## Antes de grabar (checklist)

- [ ] Docker Desktop corriendo (Testcontainers levanta Postgres 16 + Redis 7).
- [ ] Terminal en la raíz del repo: `C:\Users\L\Desktop\Tpi Metodologia`.
- [ ] `cd backend` y `uv sync` ya ejecutados; `cd ../frontend` y `npm install` ya ejecutados.
- [ ] **Demo ya ensayada**: backend y frontend levantados con los dos comandos del bloque 0.
- [ ] Zoom de terminal al 120 % y fuente legible; navegador sin pestañas personales.
- [ ] `.env` **no** se muestra: los comandos usan las variables del seed de e2e, sin secretos.
- [ ] Tener a mano: `README.md`, `docs/appointments.md`, `docs/skills-mcp/aplicacion.md`,
      `docs/skills-mcp/evidencias/revision-agendar-turno.md`,
      `docs/skills-mcp/evidencias/revision-agendar-turno-post-fix.md`,
      `docs/skills-mcp/evidencias/revision-agendar-turno-pre-archive.md`,
      `docs/skills-mcp/evidencias/gate-rls-agenda.md`,
      `openspec/specs/agenda/appointments/spec.md`.

### Bloque 0 — Preparar la demo (fuera del video)

Dos terminales, ambas con Docker arriba:

```powershell
# Terminal 1 — backend real: Postgres 16 + Redis 7 por Testcontainers, Alembic head, seed de demo
cd backend
uv run python scripts/e2e_server.py
# imprime: [e2e] cuenta lista: clinica-demo / demo@example.test
#          [e2e] uvicorn en http://127.0.0.1:8000

# Terminal 2 — SPA
cd frontend
npm run dev            # http://127.0.0.1:5173
```

Cuentas sembradas (contraseña `demo-password-123`):

| Cuenta | Rol | Para qué en el video |
|---|---|---|
| `desk@example.test` | `front_desk` | agenda el turno (tiene `appointment.create`) |
| `demo@example.test` | `owner` | opcional: mostrar la home completa |
| `ajeno@example.test` | `professional` (tenant B) | el `403` de RBAC |

---

## Bloque 1 — Presentación y problema (0:00–0:50)

**Decir**:

> "Este es el TPI de Metodología I: un SaaS multi-tenant de gestión para clínicas odontológicas PyME
> de Argentina. El riesgo dominante no es funcional, es de seguridad: un solo leak cross-tenant
> destruye la confianza de todas las clínicas. Por eso el proyecto usa Spec-Driven Development y el
> aislamiento por tenant es un gate de merge, no una tarea opcional. La entrega tiene siete changes
> archivados —los seis de la base más el entregable de agenda—, una skill propia y el MCP context7
> aplicados sobre trabajo real."

**Mostrar**: `README.md`, sección 1 y la tabla de estado.

---

## Bloque 2 — Estado del proyecto: los 4 gates (0:50–2:00)

**Ejecutar**:

```powershell
openspec list                              # sin changes activos: los 7 están archivados
Get-ChildItem openspec\changes\archive -Directory -Name
Get-ChildItem openspec\specs -Recurse -File -Name
openspec validate --archived --strict      # 7 passed, 0 failed
openspec validate --specs --strict         # 8 passed, 0 failed
```

**Decir**:

> "OpenSpec es la fuente de verdad del estado. No queda ningún change activo: los siete se
> archivaron con los cuatro gates que pide la cátedra —propuesto, aplicado, verificado y archivado—.
> C-01 dejó el monorepo, los tests con Postgres y Redis reales y el CI; C-02 las seis tablas base con
> RLS fail-closed y el gate RN-TEN-02; C-03 la sesión httpOnly con MFA; C-04 la matriz RBAC de 19
> recursos y 61 permisos; C-05 sillones, profesionales y disponibilidad; C-06 la ficha de pacientes
> con historia clínica numerada; y el séptimo es el entregable: alta de turno sin solapamientos.
> Cada uno dejó su spec principal, que es lo que se está validando acá."

**Mostrar**: `openspec/specs/agenda/appointments/spec.md` — 6 requisitos, 26 escenarios. Bajar hasta
el requisito de solapamiento y leer el escenario de concurrencia.

---

## Bloque 3 — La skill propia: qué es y qué encontró (2:00–4:00)

**Mostrar**: `.agents/skills/spec-scenario-review/SKILL.md` (frontmatter + procedimiento).

**Decir**:

> "La skill se llama `spec-scenario-review`. Revisa proposal, design, specs y tasks antes de escribir
> código, y exige al menos tres escenarios verificables por requisito: funcionamiento esperado, error
> de negocio y caso borde. Además cruza las reglas RN-XX contra la knowledge base y bloquea si falta
> el check de tenancy. El veredicto es uno de tres: listo para aplicar, faltan escenarios o bloqueado."

### 3.1 El ciclo completo sobre el entregable (2:30–3:30)

**Abrir**: `docs/skills-mcp/evidencias/revision-agendar-turno.md`.

**Decir**:

> "La corrí sobre el change de agenda antes de implementarlo. Veredicto: faltan escenarios. Detectó
> seis huecos, por ejemplo: qué pasa si el profesional está inactivo, si el turno nuevo empieza
> exactamente cuando termina otro, si la fecha llega sin offset de zona, o si el payload trae un
> `tenant_id` de otra clínica. Ninguno es teórico: cada uno define un contrato de error."

**Cambiar a**: `docs/skills-mcp/evidencias/revision-agendar-turno-post-fix.md`.

**Decir**:

> "Corregimos los seis huecos y volvimos a pasar la skill. La segunda pasada encontró dos defectos que
> la primera no vio: el payload aceptaba `fin` y además el servidor lo derivaba —dos fuentes de verdad
> para el mismo dato— y el `401` estaba en la spec pero no tenía tarea que lo verificara. La tercera
> pasada dio listo para aplicar con seis requisitos, veinticuatro escenarios y veinticuatro de
> veinticuatro con tarea."

**Cambiar a**: `docs/skills-mcp/evidencias/revision-agendar-turno-pre-archive.md`.

**Decir**:

> "Y acá está lo que más me sirvió: volví a correr la misma skill sobre el change ya implementado,
> como gate previo al archivado. Encontró cinco defectos de redacción que se habrían congelado en la
> spec principal: un escenario que pedía un `201` imposible porque la regla dura de la base lo
> rechaza, el tipo de rango que Postgres no acepta en un índice, un borde de buffers que estaba
> implementado pero no declarado, el `403` de permisos que faltaba y una guarda defensiva que había
> que anotar. Quedó listo para archivar con veintiséis escenarios, veintiséis con test. Y no cambió
> una línea de código: la implementación ya era correcta, lo que estaba mal era la spec."

### 3.2 El hueco de negocio que encontró en C-02 (3:30–4:00)

**Abrir**: `docs/skills-mcp/evidencias/revision-c-02.md`.

**Decir**:

> "En C-02 encontró un hueco que el proposal no cubría: RN-TEN-04 dice que un tenant tiene exactamente
> un owner activo, y `membership` es de ese change. Lo cerramos con un requisito, tres escenarios y un
> índice único parcial. Y verificamos el RED: sin el índice el test falla; con el índice, verde."

---

## Bloque 4 — El MCP context7 y la corrección concreta (4:00–5:00)

**Mostrar**: `README.md` sección 5.4 (configuración reproducible) y
`docs/skills-mcp/investigacion.md` (tabla de consultas).

**Decir**:

> "El MCP elegido es context7, un servidor remoto de documentación actualizada del stack. Se compara
> con Playwright MCP en la ficha: context7 aporta directo al SQL de PostgreSQL y al manejo de la
> sesión en SQLAlchemy; Playwright se usa como herramienta de test, no como MCP. Es remoto, no
> requiere instalación y es de solo lectura."

**Demo en vivo (si la sesión lo permite)**: pedir al agente:

1. `use context7` → `resolve-library-id` para SQLAlchemy.
2. `query-docs` con: *"SET LOCAL with bound parameters vs set_config per transaction"*.

**Mostrar mientras responde**: `backend/app/db/tenant_context.py`.

**Decir**:

> "La corrección concreta fue esta. El primer diseño usaba `SET LOCAL app.current_tenant = :tenant_id`.
> La documentación mostró que `SET` no acepta parámetros bindeados: o interpolás el UUID, con riesgo
> de inyección y quoting, o usás `set_config`, que sí acepta el parámetro. La versión final es
> `SELECT set_config('app.current_tenant', :tenant_id, true)`. El tercer argumento `true` es
> transaction-local: al commit o rollback la conexión vuelve al pool sin contexto. Sin ese `true`, el
> valor sobrevive y se filtra a la siguiente request."

---

## Bloque 5 — Los cinco criterios, en vivo (5:00–7:50)

### 5.1 Fundación ejecutable (5:00–5:20)

```powershell
curl.exe -s http://127.0.0.1:8000/health
curl.exe -s http://127.0.0.1:8000/ready
```

**Decir**:

> "Criterio uno: el sistema levanta. Liveness y readiness contra Postgres real. El CI corre lint,
> typecheck, unit, integration, e2e y build para las dos apps, y todos los jobs bloquean el merge."

### 5.2 Modelos y persistencia (5:20–5:50)

**En el navegador**: login `demo@example.test` → `/clinica` y `/pacientes`.

**Decir**:

> "Criterio dos: los modelos están persistidos y verificados. Acá se ven los sillones, profesionales y
> reglas de disponibilidad, y las fichas de pacientes con historia clínica numerada. Son tablas con
> `tenant_id`, RLS forzada y una migración reversible cada una; el gate de aislamiento se prueba con
> mutación, no con un `WHERE`."

### 5.3 Autenticación y permisos (5:50–6:20)

**En el navegador**: login `desk@example.test` (recepción) → la home muestra los enlaces según
permisos. Después, en una pestaña incógnita, `http://127.0.0.1:5173/turnos/nuevo` sin sesión →
redirige al login.

**Decir**:

> "Criterio tres: la sesión vive en cookies httpOnly con access y refresh rotativo, y los permisos
> salen de la sesión, no del cliente. Si el rol no tiene `appointment.create`, la ruta no se renderiza
> y la API responde `403`: eso lo verifica el e2e, no solo el unitario."

### 5.4 Agenda y turnos — el entregable (6:20–7:30)

**En el navegador**, como `desk@example.test`:

1. Home → **Agendar turno** → `/turnos/nuevo`.
2. Elegir profesional (`Profesional, Paula`, matrícula `MP-DEMO-1`), sillón (`Sillón demo`), paciente
   (`E2E-Paciente, Demo`), fecha y hora **09:00** → **Guardar turno**.
3. Mostrar la confirmación: **09:00 a 09:30 · 30 min · pendiente**. Sin regla de disponibilidad, la
   duración sale del profesional; el cliente no mandó `fin` ni `duracion_min`.
4. Cargar otro turno el mismo día a las **09:15** → **Guardar turno**.
5. Mostrar el `409`: `turno_solapado`, *recurso en conflicto: profesional*, rango `09:00–09:30`, con
   los datos cargados conservados.

**Decir**:

> "Criterio cuatro, y el entregable: crear un turno sin solapamientos. El formulario manda solo
> profesional, sillón, paciente e inicio con offset; el servidor deriva el fin, la duración y los
> buffers. El segundo intento a las nueve y cuarto devuelve `409` con el recurso y el rango del turno
> que ganó, no un error genérico. Esto no lo decide solo la aplicación: la base tiene un `EXCLUDE
> USING gist` por profesional y por sillón sobre el rango bloqueado, así que ni una carrera entre dos
> requests puede crear el doble booking. Además RN-AG-10 se evalúa antes: si el mismo paciente choca
> contra el mismo profesional, el mensaje es 'el paciente ya tiene un turno', que es lo accionable."

**Mostrar en el editor**: `backend/alembic/versions/007_agenda.py`, el bloque del `EXCLUDE`, y
`backend/app/domain/agenda/appointments/service.py`, el orden de validaciones.

### 5.5 Frontend integrado (7:30–7:50)

```powershell
cd frontend
$env:E2E_WEB_PORT='5180'; npx playwright test
```

**Decir**:

> "Criterio cinco: esto que acabamos de hacer a mano corre solo, cinco escenarios de punta a punta
> contra el backend real —alta con duración derivada, solape visible, precedencia de RN-AG-10, `403`
> sin permiso y `404` de recurso inexistente—, dentro de una suite de 24 e2e. El frontend no tiene
> mocks: pega contra FastAPI, Postgres con RLS y el `EXCLUDE`."

---

## Bloque 6 — El gate de tenancy y la suite (7:50–9:10)

**Abrir**: `docs/skills-mcp/evidencias/gate-rls-agenda.md`.

**Decir**:

> "El gate RN-TEN-02 no es un test más. Los tests de RLS hacen `SET ROLE odontologia_app` antes de
> consultar, porque el usuario del contenedor es superusuario y un superusuario ignora Row Level
> Security: sin ese `SET ROLE`, el verde sería falso. Y la evidencia incluye la prueba de mutación:
> apagué RLS y quité los cinco filtros de tenant del servicio, y la suite se puso roja —cinco fallos y
> el caso del profesional ajeno creando el turno, `assert 201 == 404`—; restaurado, vuelve a ocho en
> verde. Eso demuestra que el aislamiento no es accidental."

**Ejecutar**:

```powershell
cd backend
uv run ruff check app tests
uv run mypy app
uv run pytest -q
```

**Decir mientras corre**:

> "Ruff limpio, mypy limpio en setenta y nueve archivos y la suite completa: seiscientos noventa y
> cinco tests, con Postgres 16 y Redis reales, ninguno skippeado. Sumando el frontend, ciento
> veintiocho unitarios y veinticuatro e2e."

---

## Bloque 7 — Revisión crítica y cierre (9:10–10:00)

**Decir**:

> "Qué funcionó: la skill encontró un hueco de negocio que el autor del proposal no vio, frenó el
> change de agenda antes de codear seis contratos de error y, después del apply, volvió a corregir la
> spec antes de archivarla; el MCP evitó una API inventada. Qué queda como límite: la skill es manual,
> no hay gate de CI que la ejecute; context7 sin API key tiene rate limit; la prueba de mutación es una
> garantía de test, no de runtime —en producción la garantía es RLS más un rol sin `BYPASSRLS`—; y el
> formulario toma la zona horaria del navegador porque la sesión todavía no expone la zona del tenant,
> algo que está documentado como supuesto y cubierto por tests que no dependen de la zona del runner."

> "Estado de la entrega: siete changes archivados con los cuatro gates, seiscientos noventa y cinco
> tests de backend, ciento veintiocho unitarios y veinticuatro e2e de frontend en verde, y los cinco
> criterios cubiertos: fundación, modelos y persistencia, auth y permisos, agenda con turnos sin
> solapamiento, y frontend integrado contra el backend real. El resto del roadmap —cancelar,
> reprogramar, lista de espera, facturación— queda como backlog post-deadline y está en CHANGES.md.
> Gracias."

---

## Tomas de respaldo (si algo falla en vivo)

| Si falla | Mostrar en su lugar |
|----------|---------------------|
| Docker no arranca | `docs/appointments.md` § 7 (pipeline y suites) + `docs/skills-mcp/evidencias/gate-rls-agenda.md` (salidas ya registradas); correr solo `ruff` y `mypy` |
| El backend no levanta a tiempo | `docs/appointments.md` § 5 (curl del alta y del `409` con su salida) |
| context7 no responde | Tabla de consultas de `investigacion.md` + `tenant_context.py` |
| `openspec` no está en PATH | Los directorios de `openspec/changes/archive/` y `openspec/specs/` directamente |
| Playwright no arranca | `frontend/tests/e2e/appointments.spec.ts` abierto + `docs/appointments.md` § 6 (frontend) |
| El `EXCLUDE` sorprende en vivo | `backend/alembic/versions/007_agenda.py`: explicar `tsrange` sobre marcas UTC (por qué no `tstzrange`) |

---

## Frases que no conviene decir

- "La IA hizo todo": el video muestra decisiones, no autocompletado.
- "Los tests pasan": mostrar *qué* test fallaría si el constraint o el filtro de tenant desaparecieran.
- "Está terminado": el entregable del TPI está completo, el **producto** no; el resto del roadmap está
  en `CHANGES.md` y se dice así.
