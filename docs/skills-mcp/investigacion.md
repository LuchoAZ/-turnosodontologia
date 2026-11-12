# Ficha de investigación — skill propia y servidor MCP

**Proyecto**: Gestión Odontológica PyME (`odontologia-saas`) · **Integrantes**: 1 · **Fecha**: 2026-11-05
**Entrega**: TPI Metodología I (2026-11-20) · **Change elegido**: `c-02-core-models-tenancy`

---

## 1. Necesidad detectada

El proyecto usa Spec-Driven Development: cada change nace como `proposal.md` + `design.md` +
`specs/**/spec.md` + `tasks.md` y recién después se implementa. En los changes ya escritos
(`c-01-foundation-setup`, `agendar-turno-sin-solapamiento`) detectamos dos tareas repetibles
que consumen tiempo y se hacen mal cuando hay apuro:

1. **Revisar la spec antes de codear.** Varios requisitos tenían un solo escenario (camino
   feliz) y ninguno de error de negocio ni de borde. El riesgo es concreto: una regla de
   negocio ambigua o un caso borde sin definir se descubre durante la implementación, cuando
   corregirla cuesta el doble. En este dominio el caso crítico es el aislamiento multi-tenant
   (RN-TEN-02): un requisito sin escenario cross-tenant es un leak esperando a pasar.
2. **Consultar documentación actualizada del stack.** El change `c-02` introduce Row Level
   Security de PostgreSQL, sesiones SQLAlchemy con `SET LOCAL` y un constraint de exclusión
   por rango. La sintaxis exacta (`CREATE POLICY`, `set_config`, `EXCLUDE USING gist`) no
   conviene escribirla de memoria: el modelo puede alucinar APIs o usar una versión vieja.

**Cómo ayudan las dos incorporaciones al mismo change**: la skill revisa los artefactos de
`c-02` y exige ≥3 escenarios verificables por requisito (esperado, error de negocio, borde) y
el check de tenancy; el MCP trae la documentación oficial de PostgreSQL/SQLAlchemy que se usa
para escribir el `design.md` y las migraciones. Una controla el *qué*, el otro informa el *cómo*.

---

## 2. Skill creadora y diseño de la skill propia

### Skill creadora investigada

| Ítem | Detalle |
|------|---------|
| Nombre | `skill-creator` |
| Fuente | Repositorio oficial de Anthropic: <https://github.com/anthropics/skills> (carpeta `skills/skill-creator`) |
| Estándar | Agent Skills (`SKILL.md` con frontmatter `name` + `description`; ver <https://agentskills.io>) |
| Compatibilidad | Cualquier agente que cargue skills por carpeta, incluido OpenCode (`~/.config/opencode/skills/` o `<repo>/.agents/skills/`) |
| Instalación en este proyecto | Ya vendorizada en `.agents/skills/skill-creator/` (viaja con el repo). Verificación: la skill aparece en la lista de skills disponibles y se invoca con la herramienta `skill`. |
| Uso | Se cargó `skill-creator`, se escribió el borrador de la skill propia y se adaptó al dominio y a las convenciones del repo (frontmatter, procedimiento, criterios de revisión y formato de salida fijo). |

### Skill propia: `spec-scenario-review`

| Campo | Definición |
|-------|------------|
| **Propósito** | Revisar `proposal.md`, `design.md`, `specs/**/spec.md` y `tasks.md` de un change **antes** de implementarlo, y emitir un veredicto accionable sobre si la spec está lista. |
| **Cuándo se activa** | Después de `/opsx:propose` o `/opsx:update`, antes de `/opsx:apply` y antes de archivar. También cuando el usuario pide "revisá la spec", "¿faltan casos borde?" o "¿están los escenarios?". |
| **Entradas** | El change a revisar + la KB relevante: `05_reglas_de_negocio.md` (códigos RN-XX), `04_modelo_de_datos.md` (entidades y `tenant_id`), `03_actores_y_roles.md` (permisos), `07_flujos_principales.md` (errores). |
| **Procedimiento** | 1) Extraer cada `### Requirement`. 2) Clasificar escenarios en esperado / error de negocio / borde. 3) Cruzar las reglas citadas contra la KB y marcar ambigüedades. 4) Verificar tenancy (RN-TEN-02): escenario cross-tenant, `tenant_id` del token y test de aislamiento en `tasks.md`. 5) Verificar que cada escenario tenga una tarea de verificación. 6) Emitir informe sin reescribir la spec. |
| **Resultado esperado** | Veredicto `LISTO PARA APLICAR` / `FALTAN ESCENARIOS` / `BLOQUEADO`, tabla de cobertura por requisito, lista de huecos con sugerencia de una línea, check de tenancy y próximo paso. |
| **Criterios para revisar el resultado** | Cada requisito con ≥3 escenarios (o justificación de por qué no aplica); cada escenario con tarea de verificación; reglas coincidentes con la KB; si hay `tenant_id`, el check de tenancy completo es bloqueante; nunca marcar `LISTO` con un bloqueante abierto. |
| **Ubicación** | `.agents/skills/spec-scenario-review/SKILL.md` (project-local, versionada). Registrada en `.atl/skill-registry.md` (sección *Own Skills*) y referenciada en `AGENTS.md` / `CLAUDE.md`. |

---

## 3. Comparación de servidores MCP y elección

| Criterio | **Context7** (Upstash) | **Playwright MCP** (Microsoft) |
|----------|------------------------|--------------------------------|
| Propósito | Documentación actualizada y ejemplos de código de librerías, directo al contexto del agente | Automatización de navegador con árbol de accesibilidad (navegar, clickear, llenar formularios, snapshots) |
| Capacidades | `resolve-library-id` (resuelve nombre → ID), `query-docs` (trae docs por ID, con ranking por lenguaje) | Automatización core, pestañas, red, storage, DevTools, PDF, vision (opt-in por `--caps`) |
| Tipo / conexión | Remoto (`https://mcp.context7.com/mcp`), sin instalación local | Local (`npx @playwright/mcp@latest`), requiere Node.js 18+ y navegador |
| Credenciales | Ninguna obligatoria; API key **opcional y gratuita** para más rate limit (header `Authorization: Bearer`) | Ninguna |
| Permisos / riesgos | Solo lectura de documentación pública. No accede al repo ni a la base | Controla un navegador real; puede navegar y escribir en páginas. El propio README aclara que **no es un security boundary** |
| Costo | Gratuito (MIT); API key opcional | Gratuito (Apache-2.0) |
| Aporte a `c-02` | **Directo**: sintaxis de RLS, `set_config`/`SET LOCAL` en SQLAlchemy y `EXCLUDE USING gist` para el anti-solapamiento | Indirecto: sirve para e2e de la UI, pero `c-02` es backend/infra y todavía no tiene pantalla |
| Compatibilidad con OpenCode | Documentada por OpenCode (`mcp.context7.com/mcp`, tipo `remote`) | Documentada por Microsoft (cliente `opencode` listado) |

**Elección: Context7.** Es el que aporta al change elegido: `c-02` se define por SQL de
PostgreSQL (RLS, políticas, constraint de exclusión) y por el manejo de la sesión en
SQLAlchemy. Playwright MCP se vuelve útil recién cuando exista la UI de agenda (C-07), y
además agrega herramientas que inflan el contexto sin uso concreto hoy. Context7 es remoto,
no requiere instalar nada, no necesita credenciales y es de solo lectura: el límite de acceso
es "documentación pública del stack", sin datos del proyecto.

> **Nota al 2026-11-12**: la decisión no cambió. La UI de agenda ya existe (`/turnos/nuevo`) y
> Playwright se usa como **herramienta de test** (24 e2e, incluido el flujo de agenda), no como
> servidor MCP.

### Evidencia de uso real (2026-11-05)

| Solicitud | Resultado obtenido | Aporte al change |
|-----------|--------------------|------------------|
| `resolve-library-id("PostgreSQL", "Row Level Security multi-tenant isolation SET LOCAL")` | `/websites/postgresql` (23.053 snippets, versiones 13–19) y `/postgres/postgres` | Fijó el ID de librería para consultar docs oficiales |
| `resolve-library-id("SQLAlchemy", "session SET LOCAL RLS connection pooling")` | `/sqlalchemy/sqlalchemy` | Fijó el ID de SQLAlchemy 2.0 |
| `query-docs(/websites/postgresql, "CREATE POLICY … ENABLE ROW LEVEL SECURITY")` | Sinopsis oficial de `CREATE POLICY` (`USING`, `WITH CHECK`, `TO`, `FOR`) y ejemplo completo con `ALTER TABLE … ENABLE ROW LEVEL SECURITY` | Base del `design.md` y de la migración `002_core_tenancy` |
| `query-docs(/sqlalchemy/sqlalchemy, "SET LOCAL … per transaction")` | `SET LOCAL` no acepta parámetros bindeados; la alternativa parameterizada es `set_config('app.current_tenant', :tid, true)` sobre la conexión, dentro de la transacción | Corrigió el diseño inicial (ver informe de aplicación) |
| `query-docs(/websites/postgresql, "EXCLUDE USING gist … tstzrange btree_gist")` | Sintaxis `EXCLUDE USING gist (room WITH =, during WITH &&)` y requisito de `btree_gist` | Deja preparado el constraint de C-06 (`agendar-turno`) |

---

## 4. Instalación y configuración

Context7 ya está conectado en la configuración **global** de OpenCode
(`C:\Users\L\.config\opencode\opencode.json`), sección `mcp`:

```json
{
  "mcp": {
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp",
      "enabled": true
    }
  }
}
```

- **Variables de entorno**: ninguna obligatoria. Opcional: `CONTEXT7_API_KEY` (gratuita) para
  más rate limit; se referencia como `{env:CONTEXT7_API_KEY}` y **nunca** se commitea el valor.
- **Comprobar conexión**: `opencode mcp list` muestra el servidor y su estado; en una sesión,
  pedir `use context7` y verificar que aparecen las tools `context7_resolve-library-id` y
  `context7_query-docs`. Si el CLI no está en el PATH, verificar que `mcp.context7.enabled = true`
  en el JSON de configuración y que la sesión liste las dos tools.
- **Ejecutar una herramienta**: `resolve-library-id` + `query-docs` (evidencia de la tabla
  anterior). La configuración reproducible sin secretos queda también en `README.md`.
- **Problema de instalación encontrado**: la configuración inicial no incluía el header de API
  key; las consultas funcionan igual (rate limit menor). No se agregó la key para no introducir
  secretos en el repo. Si el rate limit se agota, la solución documentada es exportar
  `CONTEXT7_API_KEY` en el entorno del cliente.

---

## 5. Archivos de la fundación que se actualizan

| Archivo | Cambio |
|---------|--------|
| `.agents/skills/spec-scenario-review/SKILL.md` | Skill propia (nueva) |
| `.atl/skill-registry.md` | Alta en *Own Skills* + compact rules |
| `AGENTS.md` y `CLAUDE.md` | Sección "Skill propia": cuándo usarla, qué necesita, cómo revisar el resultado (ambos archivos idénticos) |
| `README.md` | Configuración reproducible del MCP + requisitos |
| `docs/skills-mcp/investigacion.md` | Esta ficha |
| `docs/skills-mcp/aplicacion.md` | Informe de aplicación, evidencias y revisión crítica |

> **Pendiente verificado**: el registro de skills global (`~/.config/opencode/skills/skill-registry/`)
> no escanea `<repo>/.agents/skills/`; por eso la skill se registra a mano en
> `.atl/skill-registry.md` (versionado) y se referencia desde `AGENTS.md`. Queda como mejora
> futura parchear el escáner global.

---

## 6. Fuentes consultadas (fecha de consulta: 2026-11-05)

1. Anthropic — *Agent Skills* (repositorio oficial, incluye `skill-creator`):
   <https://github.com/anthropics/skills>
2. Agent Skills — especificación del formato `SKILL.md`:
   <https://agentskills.io>
3. Upstash — *Context7* (README oficial, tools `resolve-library-id` y `query-docs`):
   <https://github.com/upstash/context7>
4. Microsoft — *Playwright MCP* (README oficial, requisitos y configuración):
   <https://github.com/microsoft/playwright-mcp>
5. OpenCode — *MCP servers* (configuración `remote`/`local`, `opencode mcp list`, ejemplo Context7):
   <https://opencode.ai/docs/mcp-servers/>
6. PostgreSQL 16 — *CREATE POLICY* y *Row Security Policies* (vía Context7, `/websites/postgresql`):
   <https://www.postgresql.org/docs/current/sql-createpolicy.html> ·
   <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
