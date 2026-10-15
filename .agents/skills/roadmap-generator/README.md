# roadmap-generator

Skill para generar **`CHANGES.md`** — el índice operativo y canónico de todos los changes necesarios para implementar un sistema desde cero hasta producción.

---

## ¿Qué hace?

Lee tu base de conocimiento estructurada en `knowledge-base/` y genera `CHANGES.md` en la raíz del proyecto con:

- **Árbol de dependencias** visual (ASCII art jerárquico).
- **Paralelismo por fase** con gates explícitos y asignación sugerida de agentes.
- **Camino crítico**: mínimo irreducible de changes para llegar a producción.
- **Plan óptimo con 3 agentes**: tabla de asignaciones por paso.
- **Por cada change**: estado checkbox, scope operacional, dependencias, nivel de governance y archivos KB a leer antes.

Es **fire-and-forget**: no hace preguntas, va directo al output.

---

## ¿Por qué no es solo "un roadmap"?

Un roadmap clásico es informativo (qué viene y en qué orden). `CHANGES.md` es **operativo**: te dice cómo paralelizar el trabajo entre múltiples agentes o personas, qué es el mínimo irreducible si te falta tiempo, qué archivos KB debe leer el agente antes de proponer cada change, y qué nivel de revisión humana requiere cada uno.

Diferencias clave con un roadmap simple:

| Aspecto | Roadmap simple | CHANGES.md |
|---------|---------------|------------|
| Dependencias | Tabla 1-a-1 | Árbol jerárquico + gates |
| Paralelización | Implícita o nula | Explícita, con asignación a agentes |
| Priorización ante tiempo limitado | Difícil de inferir | Camino crítico marcado |
| Contrato con la KB | Implícito | Sección "Leer antes" por change |
| Nivel de riesgo | No declarado | Governance: BAJO/MEDIO/ALTO/CRITICO |
| Scope por change | Descriptivo | Operacional (modelos, endpoints, migraciones) |
| Tracking de progreso | No | Checkboxes `[ ]` / `[x]` |

---

## Pre-requisitos

Antes de invocar esta skill necesitás:

1. **Base de conocimiento generada** en `knowledge-base/` (raíz). Si no la tenés, corré primero la skill [`kb-creator`](https://github.com/Group-Active-IA/kb-creator).
2. **OpenSpec inicializado** en el proyecto:
   ```bash
   npx @fission-ai/openspec@latest init
   ```

Si falta cualquiera de los dos, la skill te avisa y se detiene **sin escribir nada**.

---

## Instalación

```bash
npx skills add https://github.com/Group-Active-IA/roadmap-generator
```

---

## Uso

```
Tu repo:
proyecto/
├── docs/                        # Documentos fuente
├── knowledge-base/              # KB generada por kb-creator
└── openspec/                    # OpenSpec inicializado

Le decís al agente:
"generá el CHANGES.md del proyecto"
```

→ El agente lee la KB y escribe `CHANGES.md` en la raíz.

---

## Estructura del output

```markdown
# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto X.

## Cómo usar este documento
(5 pasos)

## Árbol de dependencias
(ASCII art jerárquico)

### Paralelismo por fase
(GATES con asignación a agentes)

### Camino crítico
(cadena lineal irreducible)

### Plan óptimo con 3 agentes
(tabla paso × agente)

## FASE 0 — Cimientos
### [C-01] `foundation-setup`
- Estado: [ ] pendiente
- Scope: bullets operacionales
- Dependencias: ninguna
- Governance: BAJO
- Leer antes:
  - knowledge-base/01_vision_y_objetivos.md
  - ...

## FASE 1A — Autenticación
### [C-03] `auth`
- ...
```

---

## Reglas que aplica para inferir dependencias

1. **Infra primero**: C-01 nunca depende de nada.
2. **Modelos core antes que features**: C-02 es típicamente core-models.
3. **Auth antes que recursos protegidos**.
4. **Entidad referenciada antes que la que referencia** (`categorías` antes que `productos`).
5. **Backend antes que frontend acoplado**.
6. **Integraciones externas (pagos, webhooks) al final**.
7. **Admin / dashboards al final** (dependen de datos que muestran).
8. **Refactors visuales / UI restyle al final del todo** (requieren producto estable).

## Niveles de governance

| Nivel | Cuándo se usa |
|-------|---------------|
| **BAJO** | Scaffolding, CRUDs simples, pages frontend sin lógica crítica. |
| **MEDIO** | Flujos con estado, sesiones, máquinas de estado, WS no críticos. |
| **ALTO** | Notificaciones, gestión de roles, WS gateway, observabilidad. |
| **CRITICO** | Auth, pagos, datos de seguridad, audit trail, modelos core. |

---

## Output al cerrar

```
✅ CHANGES.md creado en la raíz con 10 changes en 4 fases.
Camino crítico: 7 changes
Gates de paralelismo: 5
Primer change recomendado: C-01 (foundation-setup)
Para arrancar: /opsx:propose C-01-foundation-setup
```

---

## Licencia

Apache-2.0
