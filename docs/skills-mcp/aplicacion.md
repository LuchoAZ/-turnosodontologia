# Informe de aplicación — skill propia y MCP

**Proyecto**: Gestión Odontológica PyME (`odontologia-saas`) · **Integrantes**: 1 · **Fecha**: 2026-11-05 (actualizado 2026-11-12)
**Entrega**: TPI Metodología I (2026-11-20)
**Change elegido**: `c-02-core-models-tenancy` (archivado) · **Change revisado además**: `agendar-turno-sin-solapamiento`

Este documento cierra la sección de la entrega que pide **aplicar** la skill propia y el servidor MCP
sobre trabajo real del proyecto: qué se ejecutó, qué encontró, qué se corrigió, qué evidencia queda y
qué límites tiene el enfoque. La ficha de investigación previa está en
[`investigacion.md`](investigacion.md); las evidencias crudas, en [`evidencias/`](evidencias/).

---

## 1. Resumen

| Ítem | Resultado |
|------|-----------|
| Skill propia aplicada | `spec-scenario-review` sobre 2 changes (`c-02-core-models-tenancy` y `agendar-turno-sin-solapamiento`) |
| MCP aplicado | `context7` durante el diseño y la implementación de C-02 |
| Hueco real detectado y cerrado | **RN-TEN-04** (a lo sumo un `owner` activo por tenant) en C-02, con test RED verificado y prueba de mutación |
| Huecos detectados antes de codear | **6** en `agendar-turno-sin-solapamiento` (1.ª pasada: `FALTAN ESCENARIOS`), **corregidos y re-revisados** hasta `LISTO PARA APLICAR` (3.ª pasada) |
| Corrección técnica atribuida a context7 | `SET LOCAL … = :tenant_id` → `SELECT set_config('app.current_tenant', :tenant_id, true)` |
| Changes archivados | **7**: `c-01`…`c-06` y `2026-11-12-agendar-turno-sin-solapamiento` |
| Skill re-ejecutada como **gate pre-archive** | 4.ª pasada sobre `agendar-turno-sin-solapamiento` ya implementado: veredicto `LISTO PARA ARCHIVAR`; corrigió 5 defectos de redacción de la delta que habrían quedado congelados en la spec principal ([evidencia](evidencias/revision-agendar-turno-pre-archive.md)) |
| Verificación final | `ruff` 0 · `mypy app` 0 (79 archivos) · **695 tests passed** back · **128** unit front · **24** e2e |

El mínimo del TPI —dos changes completos, verificados y archivados— queda cumplido por C-01 y C-02.
La skill y el MCP no se usaron "de adorno": la skill cambió el alcance de C-02 (agregó RN-TEN-04),
frenó la implementación del change de agenda hasta definir seis casos borde y volvió a habilitarlo
cuando se cerraron; el MCP evitó escribir de memoria una API de PostgreSQL/SQLAlchemy que, mal usada,
rompe el aislamiento.

---

## 2. Cómo se aplicó

La skill se usó en los dos momentos en que aporta valor:

```
/opsx:propose  →  spec-scenario-review  →  /opsx:apply  →  spec-scenario-review  →  /opsx:archive
                        (antes de codear)                    (antes de archivar)
```

| Momento | Change | Qué se buscaba | Salida |
|---------|--------|----------------|--------|
| Antes de implementar | `agendar-turno-sin-solapamiento` | Que ningún requisito llegue a código con casos borde sin definir | Veredicto `FALTAN ESCENARIOS` + 6 huecos accionables |
| Tras corregir los 6 huecos | `agendar-turno-sin-solapamiento` | Verificar el cierre y detectar contradicciones de contrato | 2.ª pasada: 2 defectos (doble fuente de `fin`, `401` sin tarea) + ambigüedad de buffers → corregidos |
| Verificación final | `agendar-turno-sin-solapamiento` | Confirmar que la spec quedó implementable | Veredicto `LISTO PARA APLICAR` (6 requisitos, 24 escenarios, 24/24 con tarea) |
| Antes de archivar | `c-02-core-models-tenancy` | Que la spec implementada cubra todas las reglas de negocio y el gate de tenancy | Veredicto `LISTO PARA APLICAR` + 1 hueco cerrado (RN-TEN-04) |

El MCP se usó en la fase de diseño de C-02 (D2, D3 y el constraint de exclusión de C-06) y se volvió a
consultar durante la implementación cuando un test de integración puso en duda una decisión.

---

## 3. Caso 1 — `agendar-turno-sin-solapamiento`: detectar antes de codear

**Entradas**: `proposal.md`, `design.md`, `specs/agenda/appointments/spec.md`, `tasks.md`,
`05_reglas_de_negocio.md` (§ Tenancy, § Agenda) y `04_modelo_de_datos.md` (§ Agenda).
**Spec revisada (estado inicial)**: 6 requisitos, 14 escenarios.
**Evidencia**: [`evidencias/revision-agendar-turno.md`](evidencias/revision-agendar-turno.md) y la verificación final en [`evidencias/revision-agendar-turno-post-fix.md`](evidencias/revision-agendar-turno-post-fix.md).

### Veredicto: `FALTAN ESCENARIOS`

La skill no reescribió la spec: produjo una tabla de cobertura y seis huecos concretos.

| Requisito | Esperado | Error de negocio | Borde | Resultado |
|-----------|----------|------------------|-------|-----------|
| Crear turno reservando profesional y sillón | ✅ | ⚠️ | ❌ | Falta borde (recurso inactivo) |
| Prevenir solapamiento por profesional y sillón | ✅ | ✅ | ❌ | Falta borde (turno contiguo) |
| Derivar duración y buffers | ✅ | ❌ | ✅ | Falta error de negocio |
| Almacenar horarios en UTC | ✅ | ❌ | ❌ | Faltan 2 escenarios |
| Prevenir turnos solapados del mismo paciente | ✅ | ✅ | ⚠️ | Ambigüedad de "activo" |
| Aislar la agenda por tenant | ✅ | ✅ | ❌ | Falta `tenant_id` en body ignorado |

Los seis huecos, en una línea cada uno:

1. Profesional inactivo o sillón deshabilitado → `404`/`409` y no se crea el turno.
2. Turno contiguo (`nuevo.inicio == existente.fin`) → `201`, porque el rango es `[inicio, fin)`.
3. `tipo_practica` inexistente en el tenant o duración ≤ 0 → `422`/`404`.
4. `inicio` sin offset de zona → `422`; turno que cruza medianoche o cambio de huso → se persiste en UTC y se muestra en la zona del tenant.
5. Reemplazar "estado activo" por la lista explícita de estados de RN-AG-10.
6. `tenant_id` del tenant B en el payload con sesión del tenant A → se ignora; el turno se crea (o falla por recurso ajeno) en A, nunca en B.

### Impacto

El change de agenda es el **entregable del TPI** y todavía no se implementó. Detectar estos seis casos
antes de escribir código evita el escenario caro: descubrir el borde del turno contiguo o el
`tenant_id` en el body cuando ya hay una migración y tres capas de código escritas. La revisión de
tenancy dio **completa**: el change toca `appointment`, `chair`, `professional` y `patient`, tiene
escenario cross-tenant y el test de aislamiento está en `tasks.md` (tarea 6.1, con prueba de mutación).
No hay bloqueante de tenancy; el veredicto es por escenarios faltantes, no por seguridad.

### Cierre del ciclo (2026-11-06)

Los seis huecos se corrigieron en los artefactos del change y se volvió a pasar la skill. La segunda
pasada encontró dos defectos que la primera no vio —**doble fuente de verdad para `fin`** (se enviaba
en el payload y además se derivaba) y **`401` sin tarea de verificación**— más una ambigüedad de
buffers en RN-AG-03. La tercera pasada dio **`LISTO PARA APLICAR`** con 6 requisitos, 24 escenarios y
24/24 escenarios con tarea.

| Hueco | Decisión adoptada |
|-------|-------------------|
| 1. Recurso inactivo | `409` con `{ recurso, motivo: "recurso_inactivo" }` |
| 2. Turno contiguo | `201` (rango semiabierto; caso explícito con buffers 0) |
| 3. Tipo de práctica inválido | `422` por enum Pydantic; duración ≤ 0 → `409 duracion_invalida` |
| 4. UTC | `inicio` con offset obligatorio; `fin` derivado; cruce de medianoche cubierto |
| 5. RN-AG-10 | lista explícita de estados; `patient_id NULL` no aplica |
| 6. `tenant_id` | se descarta de body/query/header antes de validar; nunca se lee ni se rechaza |

El ciclo también destapó un problema que la revisión de escenarios sola no habría encontrado: el change
asumía que C-02 aportaba `appointment`, pero C-02 lo había excluido explícitamente. Ahora el change es
dueño del modelo, del `EXCLUDE USING gist` y de su RLS (tareas 0.1 y 0.2).

**Estado en ese momento**: `LISTO PARA APLICAR`, condicionado a que existan C-03, C-05 y C-06 —que aún
no existían ni como changes ni como migraciones—. El apply quedó en pausa; la spec ya no era el
bloqueante. **Resultado (2026-11-12)**: C-03/C-05/C-06 se completaron, el change se aplicó con
`pytest` 695 / `vitest` 128 / `playwright` 24 en verde, pasó el gate pre-archive (`LISTO PARA
ARCHIVAR`, 26/26 escenarios con test) y se archivó como
`2026-11-12-agendar-turno-sin-solapamiento`.

---

## 4. Caso 2 — `c-02-core-models-tenancy`: el hueco que la skill encontró y el código no

**Entradas**: `proposal.md`, `design.md`, `specs/platform-tenancy/spec.md`, `tasks.md`,
`05_reglas_de_negocio.md` (§ Tenancy), `04_modelo_de_datos.md` (§ Tenancy, § Catálogos) y
`03_actores_y_roles.md` (§ roles base).
**Spec final**: 7 requisitos, 25 escenarios.
**Evidencia**: [`evidencias/revision-c-02.md`](evidencias/revision-c-02.md) · **Spec archivada**:
[`openspec/specs/platform-tenancy/spec.md`](../../openspec/specs/platform-tenancy/spec.md).

### El hueco: RN-TEN-04

La KB dice, textualmente:

> **RN-TEN-04** — Un tenant tiene **exactamente un** `owner` activo. La transferencia de ownership es
> una transacción atómica: se crea el nuevo owner y se desactiva el anterior en la misma transacción.
> No hay estado intermedio con cero owners.

El change crea `membership`, que es exactamente la tabla donde vive el rol. La spec inicial cubría
`UNIQUE (tenant_id, user_id, rol)`, RLS, seed y CUIT, pero **no** la unicidad del owner activo. El
procedimiento de la skill (paso 3: cruzar cada regla RN citada contra la KB y buscar las que aplican
al alcance) la marcó como faltante.

Sin la skill, el hueco se descubría en C-04 (transferencia de ownership) o, peor, en producción: dos
owners activos en la misma clínica, con dos personas creyendo que administran el tenant.

### El cierre

| Antes | Después |
|-------|---------|
| Sin requisito de owner único | Requisito "Unicidad del owner activo por tenant (RN-TEN-04)" con 3 escenarios |
| Sin constraint | Índice único parcial `uq_membership_owner_activo` sobre `tenant_id WHERE rol = 'owner' AND activo` |
| Sin tests | 2 tests de integración: segundo owner activo → `23505`; owner inactivo no bloquea al nuevo owner activo |
| Invariante "cero owners" sin definir | Declarada **fuera de alcance** y asignada a la transacción atómica de C-04 (no se esconde como si estuviera resuelta) |

El índice parcial se agregó en el modelo (`backend/app/models/tenancy.py`) y en la migración
(`backend/alembic/versions/002_core_tenancy.py`). El `WHERE rol = 'owner' AND activo` es lo que hace
que un owner inactivo no bloquee al nuevo: el índice solo cubre filas activas.

### RED verificado (no es un test que pasa por casualidad)

Para probar que el test realmente detecta la ausencia del constraint, se quitó temporalmente el índice
de la migración y se corrió el test:

```
FAILED tests/integration/test_core_tenancy_migration.py::test_segundo_owner_activo_es_rechazado
E   Failed: DID NOT RAISE IntegrityError
```

Se restauró el índice y la suite volvió a verde. Esto es la diferencia entre "el test pasa" y "el test
fallaría si el constraint desapareciera"; el mismo criterio se usó para el gate RN-TEN-02 con la
prueba de mutación de RLS (`test_mutacion_sin_rls_el_mismo_query_filtraria`).

### Veredicto final: `LISTO PARA APLICAR`

Con el requisito cerrado, las 7 filas de la tabla de cobertura quedaron completas, el check de tenancy
quedó completo y cada escenario tuvo su tarea de verificación en `tasks.md`. El change se archivó con
**22/22 tasks** y `isComplete: true`.

---

## 5. Caso 3 — `context7` durante C-02

### Consultas y aporte

| Consulta | Resultado | Dónde se aplicó |
|----------|-----------|-----------------|
| `resolve-library-id("PostgreSQL", "Row Level Security multi-tenant isolation SET LOCAL")` | `/websites/postgresql` (versiones 13–19) | Fijó el ID para consultar docs oficiales |
| `resolve-library-id("SQLAlchemy", "session SET LOCAL RLS connection pooling")` | `/sqlalchemy/sqlalchemy` | Fijó el ID de SQLAlchemy 2.0 |
| `query-docs(/websites/postgresql, "CREATE POLICY … ENABLE ROW LEVEL SECURITY")` | Sinopsis de `CREATE POLICY` (`USING`, `WITH CHECK`, `TO`, `FOR`) y ejemplo de `ALTER TABLE … ENABLE ROW LEVEL SECURITY` | `design.md` D2 y migración `002_core_tenancy` |
| `query-docs(/sqlalchemy/sqlalchemy, "SET LOCAL … per transaction")` | `SET LOCAL` no acepta parámetros bindeados; la alternativa parameterizada es `set_config('app.current_tenant', :tid, true)` | `design.md` D3 y `backend/app/db/tenant_context.py` |
| `query-docs(/websites/postgresql, "EXCLUDE USING gist … tstzrange btree_gist")` | `EXCLUDE USING gist (room WITH =, during WITH &&)` y requisito de `btree_gist` | Deja preparado el constraint anti-solapamiento de C-06 |

### La corrección concreta: `SET LOCAL` → `set_config`

El primer borrador del diseño resolvía el contexto de tenant así:

```python
# Antes (descartado): SET LOCAL no acepta parámetros bindeados.
# Interpolar el UUID en el SQL abre la puerta a inyección y a errores de quoting.
connection.execute(text(f"SET LOCAL app.current_tenant = '{tenant_id}'"))
```

La documentación de SQLAlchemy/PostgreSQL consultada con Context7 mostró que `SET` no admite
parámetros bindeados y que la forma parameterizada y transaction-local es `set_config`:

```python
# Después (implementado)
TENANT_SETTING_SQL = text("SELECT set_config('app.current_tenant', :tenant_id, true)")

def set_tenant_context(connection: Connection, tenant_id: UUID | str) -> None:
    valor = _normalizar_tenant_id(tenant_id)
    connection.execute(TENANT_SETTING_SQL, {"tenant_id": valor})
```

El tercer argumento `true` es lo que hace que, al commit o rollback, la conexión vuelva al pool sin
contexto. Sin ese `true`, el valor sobrevive al commit y se filtra a la siguiente request que reutilice
la conexión: un leak cross-tenant silencioso. El test
`test_el_contexto_de_tenant_no_se_filtra_entre_transacciones_del_pool` cubre exactamente eso.

### Un segundo aprendizaje, este no atribuido a context7

Durante la integración apareció un error que no venía de la documentación sino de la realidad del
motor: `current_setting('app.current_tenant', true)` devuelve `NULL` si nunca se seteó, pero devuelve
la **cadena vacía** si la transacción anterior usó `set_config(..., true)` y commiteó. Sin `NULLIF`, el
cast `''::uuid` lanza `invalid input syntax for type uuid` en vez de fallar cerrado. La política final
usa:

```sql
NULLIF(current_setting('app.current_tenant', true), '')::uuid
```

Queda documentado en [`docs/core-tenancy.md`](../core-tenancy.md) § 2 para que no se "simplifique" en
una migración futura.

---

## 6. Evidencias reproducibles

### Archivos que produjo la aplicación

| Archivo | Qué contiene |
|---------|--------------|
| `.agents/skills/spec-scenario-review/SKILL.md` | La skill propia, versionada |
| `.atl/skill-registry.md` | Alta en *Own Skills* + compact rules |
| `AGENTS.md` / `CLAUDE.md` | Sección "Skill propia" (ambos idénticos) |
| `docs/skills-mcp/investigacion.md` | Ficha de investigación y elección del MCP |
| `docs/skills-mcp/evidencias/revision-agendar-turno.md` | 1.ª pasada: `FALTAN ESCENARIOS` y 6 huecos |
| `docs/skills-mcp/evidencias/revision-agendar-turno-post-fix.md` | 2.ª y 3.ª pasada: defectos de contrato cerrados y veredicto final `LISTO PARA APLICAR` (24/24 escenarios con tarea) |
| `docs/skills-mcp/evidencias/revision-c-02.md` | Revisión con veredicto `LISTO PARA APLICAR` y RN-TEN-04 cerrado |
| `docs/core-tenancy.md` | Modelo, RLS, rol, seed, prueba de mutación y comandos |
| `backend/app/db/tenant_context.py` | `set_config` parameterizado y transaction-local |
| `backend/app/core/tenant_guard.py` | Resolución del tenant desde claims, nunca desde el body |
| `backend/app/domain/tenancy/cuit.py` | Validación de CUIT módulo 11 (RN-TEN-01) |
| `backend/app/models/{base,tenancy,catalog}.py` | Modelos SQLAlchemy 2.0 tipados |
| `backend/alembic/versions/002_core_tenancy.py` | Migración: DDL, enum, rol, seed, RLS y RN-TEN-04 |
| `backend/tests/integration/{test_core_tenancy_migration,test_migration_reversibility}.py` | Gate RN-TEN-02, mutación, RN-TEN-04 y reversibilidad |

### Comandos y resultados (2026-11-05)

```powershell
cd backend
uv run ruff check .      # All checks passed!
uv run mypy app          # Success: no issues found in 22 source files
uv run pytest            # 56 passed (17 integration, 0 skipped con Docker arriba)
```

```powershell
# Ejecutados antes de archivar el change:
openspec validate c-02-core-models-tenancy --strict   # Change ... is valid
openspec status --change c-02-core-models-tenancy     # isComplete: true

# Revalidación posterior al archivo (sobre el repo tal como queda):
openspec validate --archived --strict                 # 2 archived changes válidos
openspec validate --specs --strict                    # 2 specs principales válidas
```

Los tests de integración necesitan Docker Desktop corriendo (Testcontainers con `postgres:16-alpine`
y `redis:7-alpine`); si no está, se skippean y el verde de integración no es válido. Para reproducir el
gate de tenancy alcanza con:

```powershell
uv run pytest tests/integration/test_core_tenancy_migration.py -q
uv run pytest tests/integration/test_migration_reversibility.py -q
```

---

## 7. Revisión crítica

### Qué funcionó

- **La skill encontró un hueco que el autor del proposal no vio.** RN-TEN-04 no era un detalle
  cosmético: era una regla de negocio de la KB que aplicaba al alcance y no estaba en la spec. Sin el
  paso de cruzar RN-XX contra la KB, se implementaba `membership` sin la restricción y el hueco
  aparecía recién en C-04. Es el mejor argumento para que la skill exista.
- **La skill obligó a probar el RED.** No aceptó "el test pasa": pidió la prueba de que el test falla
  sin el constraint. Eso convirtió RN-TEN-04 en una garantía verificable, no en una línea de spec.
- **Frenó el change de agenda antes de codear, y después lo habilitó.** Los seis huecos son, en su
  mayoría, decisiones de contrato (¿qué HTTP status para un recurso inactivo?, ¿el turno contiguo
  solapa o no?). Escribir código antes de decidirlas garantiza retrabajo. Corregidos los huecos, la
  skill volvió a pasar y dio `LISTO PARA APLICAR`: el gate no es un freno permanente, es un criterio
  de salida.
- **Context7 evitó una API inventada.** `SET`/`SET LOCAL` con parámetros bindeados es exactamente el
  tipo de cosa que un modelo "completa" mal. La consulta fue barata y la corrección quedó en el
  diseño y en el código, con un test que la respalda.
- **El costo de integración fue bajo.** Context7 es remoto, sin instalación ni credenciales
  obligatorias. La skill es un archivo markdown versionado, sin dependencias.

### Qué no funcionó o queda como límite

- **La skill es manual.** Se ejecuta si alguien la invoca; no hay un gate de CI que verifique que
  cada requisito tenga ≥3 escenarios. Un proyecto con más gente debería automatizar al menos la
  estructura (requisito → escenarios → tarea) para que no dependa de la disciplina.
- **La skill revisa, no genera.** No reemplaza escribir un buen proposal: en C-02 el hueco existió
  hasta que la revisión lo marcó. Sirve como red, no como fuente.
- **El registro global de skills no escanea `.agents/skills/`.** La skill se registró a mano en
  `.atl/skill-registry.md` (versionado) y se referencia desde `AGENTS.md`. Queda como mejora futura
  parchear el escáner; hoy la reproducibilidad depende de que el archivo esté en el repo.
- **Context7 sin API key tiene rate limit.** Se decidió no introducir la key para no sumar secretos al
  repo; si el límite se agota, la salida documentada es exportar `CONTEXT7_API_KEY` en el entorno.
  La calidad de la respuesta también depende de resolver bien el `library-id`; una resolución
  equivocada trae documentación de otra librería.
- **Trampa de RLS en los tests.** El usuario del contenedor es superusuario e **ignora** RLS aunque la
  política esté `FORCE`. Los tests hacen `SET ROLE odontologia_app` antes de consultar; sin eso, el
  verde sería falso. Quedó documentado en `docs/core-tenancy.md` y en el docstring del test.
- **`mypy` bare falla por dos `conftest.py`.** Es preexistente (no lo introdujo C-02) y el CI corre
  `mypy app`, que pasa. Se documenta para que nadie lo confunda con una regresión del change.
- **Alcance declarado, no maquillado.** RN-TEN-04 garantiza *a lo sumo* un owner activo; la
  invariante *exactamente uno* (cero owners) requiere la transacción atómica de C-04 y así quedó
  escrito. Los seis huecos de agenda se cerraron, la spec quedó `LISTO PARA APLICAR` y después se
  implementó y archivó con un gate pre-archive extra que corrigió 5 defectos de la delta.
- **La prueba de mutación es una garantía de test, no de runtime.** Demuestra que la suite detecta la
  ausencia de la política/constraint; la garantía en producción sigue siendo RLS + el rol sin
  `BYPASSRLS`.

### Qué haría distinto

1. Correr la skill **antes** de cerrar el `design.md`, no después: el hueco de RN-TEN-04 se habría
   detectado una iteración antes y el `design.md` habría nacido con el índice parcial.
2. Agregar al `tasks.md` de cada change una tarea explícita "pasar `spec-scenario-review` y adjuntar
   la evidencia", como se hizo en C-02 (tarea 5.4), para que no dependa de la memoria.
3. Para el próximo change, pasar la skill **dos veces** cuando se corrijan huecos: la segunda pasada
   del change de agenda encontró dos defectos que la primera no vio (doble fuente para `fin` y `401`
   sin tarea). Una sola pasada verde no alcanza después de tocar la spec. **Y una tercera sobre el
   change ya implementado**: el gate pre-archive de la agenda encontró 5 defectos de redacción que
   iban a quedar congelados en la spec principal (precedencia RN-AG-10/RN-AG-02, `tsrange` vs
   `tstzrange`, solape por buffers, `403` sin permiso, guarda de `duracion_invalida`). La lección:
   `LISTO PARA APLICAR` no implica `LISTO PARA ARCHIVAR`.

---

## 8. Conclusión y próximo paso

La aplicación de la skill y del MCP dejó resultados verificables, no una declaración de intención:

- **C-01 y C-02 archivados** (mínimo del TPI cumplido), con 22/22 tasks en C-02 y 56 tests en verde.
- **RN-TEN-04 cerrado** con requisito, índice parcial, dos tests y RED demostrado.
- **Ciclo completo sobre la agenda**: seis huecos detectados antes de escribir la primera línea del
  entregable, corregidos, re-revisados y veredicto final `LISTO PARA APLICAR` (6 requisitos,
  24 escenarios, 24/24 con tarea). Después del apply, la skill volvió a correr como **gate
  pre-archive** y corrigió 5 defectos de la delta (precedencia RN-AG-10/RN-AG-02, `tsrange` vs
  `tstzrange`, solape solo por buffers, `403` sin permiso, guarda de `duracion_invalida`) antes de
  que se congelaran en la spec principal: 6 requisitos, **26 escenarios**, 26/26 con test.
- **Una corrección técnica concreta** (`set_config` parameterizado) que evita un leak entre
  transacciones del pool.

**Próximo paso**: ninguna dependencia bloquea la entrega. Los 7 changes del sprint están archivados
(`pytest` 695, `vitest` 128, `playwright` 24) y el entregable `agendar-turno-sin-solapamiento` quedó
implementado punta a punta (API + `/turnos/nuevo` + e2e contra el backend real). Lo que sigue es
backlog post-deadline. La documentación de la entrega (video y TXT) se apoya en este informe y en
[`investigacion.md`](investigacion.md).
