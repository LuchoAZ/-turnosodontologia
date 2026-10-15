# {NombreProyecto} — Instrucciones para Agentes

> Este archivo (y su copia `CLAUDE.md`) es lo PRIMERO que todo agente lee al entrar al repo.
> Generado a partir de `knowledge-base/` y `CHANGES.md`. No editar a mano sin re-sincronizar ambos archivos.

---

## Stack Tecnológico

<!-- Copiar la tabla de knowledge-base/02_descripcion_general.md §Stack tecnológico -->

| Capa | Tecnología | Versión |
|------|------------|---------|
| Frontend | {React + TypeScript / Vite / Tailwind / Zustand / TanStack} | {x.x} |
| Backend | {FastAPI / SQLModel / PostgreSQL / Alembic} | {x.x} |
| Integraciones | {MercadoPago, ...} | — |

Detalle completo: [knowledge-base/02_descripcion_general.md](knowledge-base/02_descripcion_general.md)

---

## Base de Conocimiento

La fuente de verdad del dominio vive en `knowledge-base/`. **Leé el archivo relevante ANTES de implementar.**

| Archivo | Cuándo leerlo |
|---------|---------------|
| [01_vision_y_objetivos.md](knowledge-base/01_vision_y_objetivos.md) | Entender propósito y alcance |
| [03_actores_y_roles.md](knowledge-base/03_actores_y_roles.md) | Auth, RBAC, permisos |
| [04_modelo_de_datos.md](knowledge-base/04_modelo_de_datos.md) | Entidades, ERD, migraciones |
| [05_reglas_de_negocio.md](knowledge-base/05_reglas_de_negocio.md) | Reglas codificadas (RN-XX) |
| [06_funcionalidades.md](knowledge-base/06_funcionalidades.md) | Historias de usuario por épica |
| [07_flujos_principales.md](knowledge-base/07_flujos_principales.md) | Flujos E2E |
| [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md) | Patrones, estructura, env vars |
| [10_preguntas_abiertas.md](knowledge-base/10_preguntas_abiertas.md) | ⚠️ Inconsistencias a resolver ANTES de codear |

> ⚠️ Resolver las preguntas de prioridad **Alta** de `10_preguntas_abiertas.md` antes de arrancar el primer change.

---

## Skills Disponibles

<!-- Fuente de verdad: .atl/skill-registry.md (generado por skill-registry). Adaptar filas a las skills que lista el registry; fallback a .claude/skills/ y ~/.claude/skills/ si no existe. -->

| Agente | Rol | Skills que carga |
|--------|-----|------------------|
| **Backend Core** | FastAPI / SQLModel / UoW / migraciones | `fastapi-templates`, `python-testing-patterns`, `postgresql-table-design`, `test-driven-development` |
| **Backend Aux** | Servicios, integraciones, seguridad | `api-security-best-practices`, `postgresql-optimization` |
| **Frontend** | React / Zustand / TanStack / Tailwind | `typescript-advanced-types`, `tailwind-design-system`, `playwright-best-practices` |
| **Orquestación** | SDD / OPSX / docs | `kb-creator`, `roadmap-generator`, `agents-md-generator`, `skill-creator` |

Cargá la skill correspondiente al contexto ANTES de escribir código.

> Los compact rules de cada skill los resuelve el orquestador desde `.atl/skill-registry.md` (generado por `skill-registry`; no versionado — no está en el repo). Esta tabla solo mapea skill→rol.

---

## Roadmap de Changes

<!-- Resumen de CHANGES.md — NO duplicar el detalle completo -->

El plan de implementación completo está en [CHANGES.md](CHANGES.md). Resumen:

- **Total**: {N} changes en {M} fases.
- **Camino crítico** ({K}): `{C-01 → C-02 → ... → C-NN}`.
- **Primer change**: `C-01` ({nombre}).

**Antes de cualquier `/opsx:propose`**: leé [CHANGES.md](CHANGES.md), identificá las dependencias del change y los archivos de "Leer antes".

---

## Reglas Duras

> Reglas **globales** ya definidas en `~/.claude/CLAUDE.md` (orquestador, governance, TDD, engram): el proyecto las **hereda**, no se repiten acá.

Acá van: (a) las reglas específicas de este proyecto, derivadas de su stack ({stack}) y **confirmadas con el usuario**; y (b) cualquier regla universal que el global NO cubra todavía (ej. no buildear/commitear sin pedido, conventional commits sin co-autoría IA — incluir SOLO si no están en el global). Son contrato; romperlas es un defecto. Formato `NUNCA X → hacer Y`:

<!-- Reemplazar con las reglas confirmadas en el Paso 3 de la skill. Ejemplos por stack — NO copiar a ciegas: -->
<!-- Go:        NUNCA mergear sin `gofmt`/`go vet` limpios → correrlos antes de cada commit. -->
<!-- Python:    NUNCA schema Pydantic sin `extra='forbid'` → rechazar campos no declarados. -->
<!-- React/TS:  NUNCA usar `any` → tipar estricto; componentes en PascalCase. -->

- {Reglas confirmadas del proyecto. Si el usuario no agregó ninguna específica, dejá solo la línea de referencia al global de arriba — es válido.}

---

## Flujo de Trabajo

```
1. Leer la KB relevante (knowledge-base/)        → entender el dominio
2. Identificar el change en CHANGES.md           → respetar dependencias
3. /opsx:propose C-NN-nombre                     → proposal + design + specs + tasks
4. Implementar las tasks (cargando skills)       → respetando las reglas duras
5. /opsx:archive C-NN-nombre + marcar [x]        → cerrar el change
```

Aplicar TODAS las reglas duras en cada paso. Ante conflicto entre la KB y este archivo, las reglas duras prevalecen.
