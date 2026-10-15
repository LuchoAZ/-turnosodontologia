# web-scraper

Convierte una **URL de un competidor** en una **nota markdown comparable**, sin
API keys ni servicios pagos de terceros.

> El esquema de salida es fijo, siempre — para que 10 competidores investigados
> en momentos distintos se lean igual de fácil que uno solo.

---

## ¿Qué hace?

Recibe una o varias URLs de competidores o soluciones existentes y produce una
nota estructurada por cada una, usando `WebFetch`/`WebSearch` (ya incluidos en
Claude Code) como backend:

1. **Recibir y validar** — normaliza la URL, chequea que apunte a algo con
   sentido (home, pricing, producto).
2. **Fetch + extracción** — pide a `WebFetch` los 8 campos del esquema fijo:
   problema que resuelve, usuarios objetivo, features, pricing, mensajes de
   posicionamiento y diferenciadores.
3. **Normalizar y escribir** — genera un nombre de archivo consistente
   (`scripts/slugify.py`) y escribe `discovery/sources/<slug>.md`.

No requiere `SGAI_API_KEY` ni ningún otro servicio de scraping pago — el
default nunca pide credenciales. Sitios con JS pesado o anti-bot quedan fuera
de este v1 (documentado como extensión futura en `references/output-schema.md`).

---

## Instalación

```bash
npx skills add https://github.com/Group-Active-IA/web-scraper
```

La skill queda disponible para tu agente y se carga sola cuando pedís
investigar un competidor a partir de una URL, o cuando `discovery-research` la
invoca como sub-skill durante la etapa de Discovery.

---

## Uso

Le decís al agente algo como:

```
"Investigá a este competidor: https://competidor-a.com"
"Scrapeá https://otra-solucion.com/pricing, quiero ver cómo cobran"
```

El agente valida la URL, llama a `WebFetch` con el esquema fijo, y te deja una
nota en `discovery/sources/<slug>.md` con los 8 campos completos (o marcados
`(no publicado)` si el sitio no los muestra).

---

## Estructura

```
web-scraper/
├── SKILL.md
├── README.md
├── scripts/
│   └── slugify.py
├── references/
│   └── output-schema.md
└── assets/
    └── example-source-note.md
```

---

## Por qué esta estructura

- **Esquema fijo en `references/`, no en `SKILL.md`** — el agente lo carga solo
  cuando escribe una nota, manteniendo `SKILL.md` corto y el detalle del formato
  en un solo lugar versionable.
- **`scripts/slugify.py` en vez de que el agente invente el nombre cada vez** —
  scrapear el mismo competidor dos veces en momentos distintos tiene que pisar
  el mismo archivo, no duplicarlo con nombres levemente distintos.
- **Sin backend pago por defecto** — a diferencia de otras skills de scraping
  del ecosistema (que dependen de una API key y créditos por operación), esta
  usa herramientas que Claude Code ya trae, así que instalarla no le suma costo
  ni fricción de setup a nadie.

---

## Licencia

Apache-2.0
