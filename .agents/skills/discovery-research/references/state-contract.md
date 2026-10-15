# State contract — sección `discovery`

`discovery-research` es dueña ÚNICA de la sección `discovery` dentro de
`.jr-orchestrator-state.json`. No toca `version`, `step`, `owner`, ni ninguna
otra sección (`kb`, `roadmap`, `skills`, `agents`, `registry`) — esas las
escriben sus respectivos dueños.

## Shape exacto

```json
{
  "discovery": {
    "created_by": "discovery-research",
    "sources": ["https://competidor-a.com", "https://competidor-b.com"],
    "competitors": [
      { "name": "Competidor A", "notes_file": "discovery/sources/competidor-a.md" }
    ],
    "problema": "...",
    "usuarios": ["..."],
    "casos_de_uso": ["..."],
    "funcionalidades_necesarias": ["..."],
    "funcionalidades_opcionales": ["..."],
    "reglas_de_negocio": ["..."],
    "integraciones": ["..."],
    "restricciones": ["..."],
    "riesgos": ["..."],
    "preguntas_abiertas": ["..."]
  }
}
```

Si el usuario decidió NO hacer Discovery (decisión de `jr-orchestrator`, antes
de que esta skill se invoque), `jr-orchestrator` es quien deja constancia con
`"discovery": { "skipped": true }` — esta skill nunca escribe ese shape, solo
el shape completo de arriba, porque si `discovery-research` corrió es porque
sí se decidió hacer Discovery.

## Campos libres

Igual que pasa hoy con `registry.skills_count` o `agents.reglas_applied` (que
no están en el ejemplo mínimo de `jr-orchestrator` pero sí aparecen en
proyectos reales), esta sección puede crecer con campos adicionales si la
corrida lo amerita (ej. `sources_fetched_at`, notas libres) — el shape de
arriba es el mínimo garantizado, no un techo.

## Qué lee `kb-creator` de acá

`kb-creator` (downstream, no esta skill) hace una lectura best-effort de
`state.discovery` al arrancar, para pre-llenar lo que pueda de
`state.kb.discovery` y no repreguntar:

| `state.discovery` | pre-llena en `state.kb.discovery` |
|---|---|
| `problema` | `problem` |
| `integraciones` (si hay alguna que implique infra propia) | `needs_infra` |
| `usuarios` (tamaño/naturaleza del público) | `scale` (orientativo, no definitivo) |

`system_type` y `stack` de `kb-creator` casi nunca salen de Discovery (son
decisiones técnicas, no de producto) — `kb-creator` sigue preguntándolos
directamente salvo que el usuario ya los haya mencionado.

Este mapeo vive documentado acá y no en `kb-creator` porque el contrato lo
define quien PRODUCE los datos (`discovery-research`); quien los consume solo
necesita saber qué shape esperar, no reinterpretarlo cada vez.
