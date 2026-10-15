---
name: discovery-research
description: >-
  Corre la fase de Discovery/Investigacion antes de armar la Knowledge Base de un proyecto: investiga competidores via web-scraper si hay URLs, y guia una Q&A sobre el checklist completo (problema, usuarios, casos de uso, competidores, funcionalidades necesarias y opcionales, reglas de negocio, integraciones, restricciones, riesgos, preguntas abiertas). Usala cuando jr-orchestrator despache la fase discovery del flujo de fundacion, o cuando el usuario quiera investigar el mercado/pensar que construir antes de tener claridad. NO la uses para construir la Knowledge Base en si (eso es kb-creator, que consume el resultado de esta skill) ni para scrapear una URL suelta sin el resto del checklist (eso es web-scraper directamente).
license: Apache-2.0
---

# Discovery Research

Convierte "tengo una idea" en "sé qué voy a construir y por qué", ANTES de que
exista una Knowledge Base. El principio que ordena todo: **no completes un punto
del checklist con una suposición cuando podés preguntarlo o investigarlo** — esta
skill existe precisamente porque hoy el flujo salta directo a documentar sin
haber hecho esa tarea.

> **Nota de responsabilidad**: la decisión de "¿hacemos Discovery o no?" es de
> `jr-orchestrator`, no de esta skill. Cuando `discovery-research` arranca, asumí
> que esa decisión ya se tomó — tu trabajo es correr la fase, no decidir si
> corresponde.

## Cuándo aplica

El usuario tiene una idea de proyecto pero todavía no puede responder con
precisión quién lo va a usar, qué problema resuelve exactamente, o cómo se
compara con lo que ya existe. También aplica cuando `jr-orchestrator` despacha
la fase `discovery` (antes de `kb`) en `/jr-orchestrator:init`. El resultado de
esta skill (`discovery/discovery.md` + `state.discovery`) es el INSUMO de
`kb-creator`, no un reemplazo — `kb-creator` sigue siendo quien arma la
Knowledge Base final, ahora con menos preguntas repetidas.

## Workflow

```
1. Fuentes         → ¿hay URLs de competidores o docs? invocar web-scraper si sí
2. Checklist Q&A    → 11 puntos, guiado por references/checklist.md
3. Gate final       → resumen + confirmación explícita del usuario
4. Escribir         → discovery/discovery.md + state.discovery
```

Es una fase de gobernanza MEDIA: implementa con checkpoints y expone al usuario
las decisiones no obvias — igual nivel que `kb-creator` hoy. El paso 3 es la
compuerta de aprobación: nunca escribas `discovery/discovery.md` ni toques
`state.json` sin que el usuario haya confirmado el resumen.

## Fase 1 — Fuentes

Preguntale al usuario (una sola pregunta, no un cuestionario) si tiene fuentes
concretas para analizar: URLs de competidores o soluciones existentes, docs
propios, lo que sea. Si trae URLs, invocá la skill `web-scraper` una vez por
URL — ella misma valida, extrae y escribe `discovery/sources/<slug>.md` con el
esquema fijo (ver su propio `SKILL.md`). Vos no reimplementás el scraping acá,
solo lo orquestás.

Si el usuario no tiene fuentes, seguí igual a la Fase 2 — Discovery también
funciona sin scraping, apoyado enteramente en la Q&A. No bloquees el flujo
pidiendo URLs que el usuario no tiene.

Si hubo scraping, corré `scripts/collect_sources.py` antes de la Fase 2: te
arma una tabla comparativa rápida (competidor / problema / pricing /
diferenciador) leyendo todas las notas en `discovery/sources/`. Usala como
contexto para no repreguntar lo que el scraping ya reveló.

## Fase 2 — Checklist Q&A

Guiate por `references/checklist.md` — tiene las preguntas para los 11 puntos,
con el mismo formato que usa `kb-creator` (3-5 preguntas por ronda, opciones
a/b/c, "por qué importa" explícito, y una tabla de respuestas vagas a rechazar).
Regla de oro: si un punto del checklist ya está resuelto por lo que sacaste del
scraping (ej. "competidores" si ya scrapeaste 3), no lo preguntes de nuevo —
mostraselo como resumen y pedí que lo confirme o corrija.

Para la sección de **riesgos** y **preguntas abiertas**, usá el espíritu de
assumption-mapping: por cada funcionalidad o decisión que el usuario da por
sentada, preguntate "¿esto es un hecho verificado o un supuesto sin probar?" —
los supuestos sin probar son las entradas naturales de "riesgos" y "preguntas
abiertas". No hace falta nombrar el framework, solo aplicar la lógica.

## Fase 3 — Gate final

Antes de escribir ningún archivo, mostrale al usuario un resumen de los 11
puntos tal como quedaron entendidos, y esperá su confirmación explícita (mismo
patrón que el cierre de ronda de `kb-creator`: resumen + supuestos + próximos
pasos). Si corrige algo, ajustá y volvé a resumir — no generes archivos hasta
que el usuario diga que está bien.

## Fase 4 — Escribir discovery.md + state.discovery

Escribí `discovery/discovery.md` en prosa legible (no un JSON crudo) siguiendo
la estructura de `assets/example-discovery.md`. Después actualizá (o creá) la
sección `discovery` de `.jr-orchestrator-state.json` con el schema exacto
documentado en `references/state-contract.md` — escribís SOLO esa sección; el
resto del archivo (`version`, `step`, `owner`, y las secciones de otras fases)
no son tu responsabilidad.

## Componentes de la skill

| Archivo | Para qué |
|---|---|
| `scripts/collect_sources.py` | Lee `discovery/sources/*.md` (escritas por `web-scraper`) y arma una tabla comparativa rápida para la Fase 2 |
| `references/checklist.md` | Banco de preguntas de los 11 puntos, reglas de la ronda y anti-patrones a rechazar |
| `references/state-contract.md` | Schema exacto de `state.discovery`, y qué campos de `state.kb.discovery` puede pre-llenar `kb-creator` a partir de este resultado |
| `assets/example-discovery.md` | `discovery.md` de ejemplo completo — el patrón a seguir al escribir la salida final |

## Dependencia

Esta skill NO es autocontenida: cuando hay URLs, invoca a `web-scraper` como
sub-skill (instalada por separado, `Group-Active-IA/web-scraper`). Si
`web-scraper` no está disponible, seguí igual con la Q&A pura y avisale al
usuario que el scraping automático no corrió.
