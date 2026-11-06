# Guion del video — TPI Metodología I

**Duración objetivo**: 9–10 minutos · **Formato**: grabación de pantalla + voz · **Integrantes**: 1
**Proyecto**: Gestión Odontológica PyME (`odontologia-saas`) · **Entrega**: 2026-11-20

> Regla del video: mostrar **evidencia ejecutada**, no diapositivas. Cada bloque termina con un
> archivo, un comando o una salida de terminal que se pueda verificar en el repo.

---

## Antes de grabar (checklist)

- [ ] Docker Desktop corriendo (los tests de integración usan Testcontainers).
- [ ] Terminal en la raíz del repo: `C:\Users\L\Desktop\Tpi Metodologia`.
- [ ] `cd backend` y `uv sync` ya ejecutados (sin descargas en el video).
- [ ] Zoom de terminal al 120 % y fuente legible.
- [ ] Cerrar pestañas con datos personales o secretos (`.env` **no** se muestra).
- [ ] Tener a mano: `README.md`, `docs/skills-mcp/aplicacion.md`,
      `docs/skills-mcp/evidencias/revision-c-02.md`, `docs/skills-mcp/evidencias/revision-agendar-turno.md`,
      `docs/skills-mcp/evidencias/revision-agendar-turno-post-fix.md`,
      `openspec/specs/platform-tenancy/spec.md`, `backend/tests/integration/test_core_tenancy_migration.py`.

---

## Bloque 1 — Presentación y problema (0:00–0:50)

**Decir**:

> "Este es el TPI de Metodología I: un SaaS multi-tenant de gestión para clínicas odontológicas PyME
> de Argentina. El riesgo dominante no es funcional, es de seguridad: un solo leak cross-tenant
> destruye la confianza de todas las clínicas. Por eso el proyecto usa Spec-Driven Development y el
> aislamiento por tenant es un gate de merge, no una tarea opcional. La entrega tiene dos changes
> archivados —C-01 foundation y C-02 core models + tenancy— más una skill propia y el MCP context7
> aplicados sobre trabajo real."

**Mostrar**: `README.md`, sección 1 y la tabla de estado (líneas 38–45).

---

## Bloque 2 — Estado del proyecto y changes archivados (0:50–2:10)

**Ejecutar**:

```powershell
openspec list
Get-ChildItem openspec\changes\archive -Directory -Name
Get-ChildItem openspec\specs -Recurse -File -Name
```

**Decir**:

> "OpenSpec es la fuente de verdad del estado. Hay dos changes archivados: C-01, que dejó el monorepo,
> los tests con Postgres y Redis reales y el CI; y C-02, que dejó las seis tablas base, RLS fail-closed,
> el seed de catálogos y el gate RN-TEN-02. Las specs principales quedaron en `platform-runtime` y
> `platform-tenancy`. El change de agenda sigue activo porque es el entregable y todavía no se
> implementó."

**Mostrar**: `openspec/specs/platform-tenancy/spec.md` — 7 requisitos, 25 escenarios. Bajar hasta el
requisito de RN-TEN-04 y leer los tres escenarios en voz alta.

---

## Bloque 3 — La skill propia: qué es y qué encontró (2:10–4:40)

**Mostrar**: `.agents/skills/spec-scenario-review/SKILL.md` (frontmatter + procedimiento).

**Decir**:

> "La skill se llama `spec-scenario-review`. Revisa proposal, design, specs y tasks antes de escribir
> código, y exige al menos tres escenarios verificables por requisito: funcionamiento esperado, error
> de negocio y caso borde. Además cruza las reglas RN-XX contra la knowledge base y bloquea si falta
> el check de tenancy. El veredicto es uno de tres: listo para aplicar, faltan escenarios o bloqueado."

### 3.1 Evidencia sobre el entregable: el ciclo completo (2:40–3:40)

**Abrir**: `docs/skills-mcp/evidencias/revision-agendar-turno.md`.

**Decir**:

> "La corrí sobre el change de agenda antes de implementarlo. Veredicto: faltan escenarios. Detectó
> seis huecos, por ejemplo: qué pasa si el profesional está inactivo, si el turno nuevo empieza
> exactamente cuando termina otro, si la fecha llega sin offset de zona, o si el payload trae un
> `tenant_id` de otra clínica. Ninguno es teórico: cada uno define un contrato de error. La revisión de
> tenancy dio completa, así que no hay bloqueante de seguridad; el veredicto es por escenarios."

**Mostrar**: la tabla de cobertura y los seis huecos. No hace falta leerlos todos.

**Cambiar a**: `docs/skills-mcp/evidencias/revision-agendar-turno-post-fix.md`.

**Decir**:

> "Corregimos los seis huecos y volvimos a pasar la skill. Y acá está el valor real del gate: la
> segunda pasada encontró dos defectos que la primera no vio. El payload aceptaba `fin` y además el
> servidor lo derivaba — dos fuentes de verdad para el mismo dato — y el `401` estaba en la spec pero
> no tenía ninguna tarea que lo verificara. La tercera pasada, ya sin defectos, dio listo para aplicar
> con seis requisitos, veinticuatro escenarios y veinticuatro de veinticuatro con tarea de
> verificación. El ciclo es visible en el historial del propio archivo: faltan escenarios, corrección,
> listo para aplicar."

**Mostrar**: la tabla "Historial de la revisión" al inicio de la evidencia y el veredicto final.

### 3.2 Evidencia sobre C-02: el hueco que encontró (3:40–4:40)

**Abrir**: `docs/skills-mcp/evidencias/revision-c-02.md`.

**Decir**:

> "En C-02 la skill encontró un hueco real que el proposal no había cubierto: la regla RN-TEN-04 de la
> knowledge base dice que un tenant tiene exactamente un owner activo, y `membership` es de este
> change. La spec no lo cubría. Sin la skill, el hueco aparecía en C-04 o en producción, con dos
> personas creyendo que administran la misma clínica. Lo cerramos con un requisito, tres escenarios y
> un índice único parcial sobre `tenant_id` donde el rol es owner y está activo."

**Mostrar en el editor**:

- `backend/app/models/tenancy.py` → bloque `uq_membership_owner_activo`.
- `backend/alembic/versions/002_core_tenancy.py` → el `op.create_index` con
  `postgresql_where=sa.text("rol = 'owner' AND activo")`.

**Decir**:

> "Y no nos quedamos con que el test pase: verificamos el RED. Sacamos el índice de la migración y el
> test falló con `DID NOT RAISE IntegrityError`; lo restauramos y volvió a verde. Eso es lo que
> convierte la regla en una garantía verificable."

---

## Bloque 4 — El MCP context7 y la corrección concreta (4:40–6:20)

**Mostrar**: `README.md` sección 5.4 (configuración reproducible) y
`docs/skills-mcp/investigacion.md` (tabla de consultas).

**Decir**:

> "El MCP elegido es context7, un servidor remoto de documentación actualizada del stack. Se compara
> con Playwright MCP en la ficha: context7 aporta directo a C-02 porque el change se define por SQL de
> PostgreSQL y por el manejo de la sesión en SQLAlchemy; Playwright se vuelve útil recién con la UI de
> agenda. Es remoto, no requiere instalación y es de solo lectura: el límite de acceso es documentación
> pública."

**Demo en vivo (si la sesión lo permite)**: pedir al agente:

1. `use context7` → `resolve-library-id` para SQLAlchemy.
2. `query-docs` con: *"SET LOCAL with bound parameters vs set_config per transaction"*.

**Mostrar mientras responde**: `backend/app/db/tenant_context.py`.

**Decir**:

> "La corrección concreta fue esta. El primer diseño usaba `SET LOCAL app.current_tenant = :tenant_id`.
> La documentación mostró que `SET` no acepta parámetros bindeados: o interpolás el UUID, con riesgo de
> inyección y quoting, o usás `set_config`, que sí acepta el parámetro. La versión final es
> `SELECT set_config('app.current_tenant', :tenant_id, true)`. El tercer argumento `true` es
> transaction-local: al commit o rollback la conexión vuelve al pool sin contexto. Sin ese `true`, el
> valor sobrevive al commit y se filtra a la siguiente request que reutilice la conexión."

**Si no hay demo en vivo**: mostrar la tabla de consultas de `investigacion.md` y el código final.

---

## Bloque 5 — El gate de tenancy y la suite (6:20–8:30)

**Abrir**: `backend/tests/integration/test_core_tenancy_migration.py`.

**Decir**:

> "El gate RN-TEN-02 no es un test más. Los tests de RLS hacen `SET ROLE odontologia_app` antes de
> consultar porque el usuario del contenedor es superusuario y un superusuario ignora Row Level
> Security: sin ese `SET ROLE`, el verde sería falso. La prueba de mutación corre el mismo `SELECT`
> como owner y como rol de app: como owner ve filas de A y de B; como app ve solo A. Eso demuestra que
> el filtro lo hace la política, no un `WHERE` accidental."

**Mostrar**: `test_mutacion_sin_rls_el_mismo_query_filtraria` y el test de
`test_el_contexto_de_tenant_no_se_filtra_entre_transacciones_del_pool`.

**Ejecutar**:

```powershell
cd backend
uv run ruff check .
uv run mypy app
uv run pytest tests/integration/test_core_tenancy_migration.py -q
uv run pytest -q
```

**Decir mientras corre**:

> "Ruff y mypy en cero. El gate de tenancy en verde y la suite completa en 56 tests, 17 de integración
> con Postgres 16 real. Ninguno skippeado: Docker está arriba."

**Mostrar**: `56 passed` y el `openspec validate --archived --strict` con los dos changes válidos.

---

## Bloque 6 — Revisión crítica y cierre (8:30–9:40)

**Decir**:

> "Qué funcionó: la skill encontró un hueco de negocio que el autor del proposal no vio y frenó el
> change de agenda antes de codear seis contratos de error; el MCP evitó una API inventada. Qué no
> funcionó o queda como límite: la skill es manual, no hay gate de CI que la ejecute; el registro
> global de skills no escanea `.agents/skills`, así que el alta fue manual en `.atl/skill-registry.md`;
> context7 sin API key tiene rate limit; y la prueba de mutación es una garantía de test, no de
> runtime: la garantía en producción sigue siendo RLS más un rol sin `BYPASSRLS`."

> "Estado de la entrega: C-01 y C-02 archivados, 22 de 22 tasks en C-02, 56 tests en verde, y la
> documentación completa en `docs/skills-mcp/`. El change de agenda ya pasó el gate con listo para
> aplicar; el próximo paso es implementar sus dependencias, C-03, C-05 y C-06, y recién entonces
> escribir el entregable. Gracias."

---

## Tomas de respaldo (si algo falla en vivo)

| Si falla | Mostrar en su lugar |
|----------|---------------------|
| Docker no arranca | `docs/core-tenancy.md` § 6 con la salida ya registrada (`56 passed`) y correr solo `ruff` + `mypy` |
| context7 no responde | Tabla de consultas de `investigacion.md` + `tenant_context.py` |
| `openspec` no está en PATH | Los archivos de `openspec/changes/archive/` y `openspec/specs/` directamente |
| El test de mutación tarda | Explicar el test y mostrar el código; la ejecución completa ya está en el bloque 5 |

---

## Frases que no conviene decir

- "La IA hizo todo": el video muestra decisiones, no autocompletado.
- "Los tests pasan": mostrar *qué* test fallaría si el constraint desapareciera.
- "Está terminado": el entregable de agenda sigue pendiente; decirlo con honestidad.
