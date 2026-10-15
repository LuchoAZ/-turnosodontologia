# agents-md-generator

Skill que genera el `AGENTS.md` / `CLAUDE.md` canónico de un proyecto a partir de su base de conocimiento (`knowledge-base/`) y su roadmap (`CHANGES.md`).

Consolida en un solo archivo:

- **Stack tecnológico** (desde `knowledge-base/02_descripcion_general.md`)
- **Referencia a la KB** (links a `knowledge-base/*.md`)
- **Skills disponibles por agente** (Backend Core / Aux / Frontend / Orquestación)
- **Roadmap de changes** (resumen de `CHANGES.md`: camino crítico, fases, primer change)
- **Reglas duras del proyecto** (contrato no negociable)

## Reglas duras incluidas

1. No buildear automático.
2. No commitear sin pedido explícito.
3. Conventional Commits sin `Co-Authored-By`.
4. Tests sin mocks de DB.
5. Pydantic schemas con `extra='forbid'`.
6. snake_case en Python.
7. PascalCase en componentes React.

## Instalación

```bash
npx skills add https://github.com/JuanCruzRobledo/agent-instruction
```

## Uso

Generá el `AGENTS.md` con:

```
"generar AGENTS.md" · "armar las reglas del proyecto" · "instrucciones para los agentes"
```

Pre-requisitos: `knowledge-base/` (corré `kb-creator`) y, opcionalmente, `CHANGES.md` (corré `roadmap-generator`).

## Estructura

```
agent-instruction/
├── SKILL.md                  # Skill principal
├── assets/
│   └── agents-template.md    # Plantilla completa de AGENTS.md
└── README.md
```

## Skills relacionadas

Parte de una trilogía que se encadena: `kb-creator` (documenta) → `roadmap-generator` (planifica) → `agents-md-generator` (instruye).

## Licencia

Apache-2.0
