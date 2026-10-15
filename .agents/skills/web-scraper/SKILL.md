---
name: web-scraper
description: >-
  Investiga competidores o soluciones existentes a partir de una URL: extrae problema que resuelve, usuarios objetivo, features, pricing y posicionamiento en notas markdown con esquema fijo, usando WebFetch/WebSearch sin API keys ni costos extra. Usala cuando el usuario pida investigar/scrapear un competidor a partir de una URL, o cuando discovery-research la invoque como sub-skill durante la etapa de Discovery. NO la uses para scraping masivo/crawling de sitios completos ni para sitios con JS pesado o anti-bot (documentado como extensión futura, no soportado en v1).
license: Apache-2.0
---

# Web Scraper

Convierte una URL de un competidor o solución existente en una nota markdown
estructurada y comparable. El principio que ordena todo: **el esquema de salida
es fijo, siempre** — para que quien lea 10 notas de 10 competidores distintos
encuentre la misma información en el mismo lugar, y para que `discovery-research`
pueda consumirlas de forma predecible sin tener que interpretar formatos libres.

## Cuándo aplica

El usuario tiene una URL concreta de un competidor, una solución existente, o
cualquier producto que quiere entender antes de decidir qué construir — típicamente
durante una etapa de Discovery, antes de armar la Knowledge Base de un proyecto
nuevo. También se invoca como sub-skill desde `discovery-research`, que junta las
notas de varios competidores antes de la Q&A guiada. No hace falta que el usuario
tenga cuenta ni API key de ningún servicio de scraping — solo la URL.

## Workflow

```
1. Recibir URL(s)         → validar que sean http(s) bien formadas
2. Fetch + extracción      → WebFetch con prompt estructurado por el esquema fijo
3. Normalizar y escribir   → discovery/sources/<slug>.md (esquema de references/output-schema.md)
```

Es una skill de solo lectura externa — no escribe nada del sistema del usuario ni
ejecuta acciones irreversibles, así que no necesita compuerta de aprobación antes
de scrapear una URL individual. Si el usuario pasa varias URLs, procesalas una por
una y reportá al final cuántas se resolvieron y cuántas fallaron (no aborts todo el
lote por una URL caída).

## Fase 1 — Recibir y validar

Tomá la URL (o lista de URLs) que te pasaron. Si falta el esquema (`http`/`https`),
agregalo. Si la URL claramente no es la home ni una página de producto/pricing
(por ejemplo, un PDF o un link roto a simple vista), preguntá si hay una URL más
específica antes de gastar el fetch — pero no bloquees por dudas menores, el
fetch en sí es barato y reversible.

## Fase 2 — Fetch + extracción con WebFetch

Llamá a `WebFetch` con un prompt que pida explícitamente los 8 campos del esquema
fijo (ver `references/output-schema.md` para el detalle exacto de cada campo y un
prompt de referencia). Si la página no tiene información pública para un campo
(ej. pricing oculto detrás de "contactanos"), dejá el campo con `(no publicado)`
en vez de inventar — nunca completes un campo con una suposición.

Si `WebFetch` devuelve contenido vacío, un shell de SPA sin datos, o un bloqueo
(403, paywall, CAPTCHA), NO reintentes con trucos de evasión — reportá la
limitación tal cual en el campo correspondiente y seguí con la siguiente URL. El
backend por defecto es liviano a propósito; sitios con JS pesado o anti-bot son un
caso conocido no cubierto en v1 (ver "Extensión futura" en
`references/output-schema.md`).

## Fase 3 — Normalizar y escribir

Generá el nombre de archivo con `scripts/slugify.py` (kebab-case, a partir del
nombre del competidor o del dominio) para que corridas repetidas sobre el mismo
competidor pisen el mismo archivo en vez de duplicar. Completá la plantilla de
`assets/example-source-note.md` con lo extraído y escribí el resultado en
`discovery/sources/<slug>.md`, relativo al directorio de trabajo del proyecto
actual (creá la carpeta `discovery/sources/` si no existe).

## Reglas duras

- **El esquema de salida no se negocia.** Los 8 campos van siempre, en el mismo
  orden, aunque alguno quede `(no publicado)` — es lo que hace que las notas sean
  comparables entre sí.
- **Nunca inventes un dato que la página no muestra.** Un campo vacío marcado
  como tal es más útil que un pricing o una feature inventada.
- **No hagas crawling ni scraping masivo de un sitio completo.** Esta skill
  procesa páginas puntuales que le pasan explícitamente; recorrer un sitio entero
  es un problema distinto (rate limits, robots.txt, volumen) fuera de este v1.

## Componentes de la skill

| Archivo | Para qué |
|---|---|
| `scripts/slugify.py` | Genera el nombre de archivo kebab-case consistente a partir de una URL o nombre de competidor, para que corridas repetidas no dupliquen notas |
| `references/output-schema.md` | Esquema fijo de las notas de salida, el prompt de referencia para `WebFetch`, y el punto de extensión futuro (Playwright / ScrapeGraph AI) |
| `assets/example-source-note.md` | Nota de ejemplo completa — el patrón exacto a seguir al escribir cada archivo |
