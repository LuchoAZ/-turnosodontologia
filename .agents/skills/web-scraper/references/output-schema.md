# Esquema fijo de salida

Cada nota generada en `discovery/sources/<slug>.md` tiene EXACTAMENTE estos 8
campos, en este orden. Si un campo no tiene información pública en la página,
se deja como `(no publicado)` — nunca se completa con una suposición.

```markdown
# {{Nombre del competidor/solución}}

- **URL**: {{url investigada}}
- **Fecha de investigación**: {{YYYY-MM-DD}}

## Problema que resuelve

{{1-3 líneas: qué problema dice resolver, con sus propias palabras/mensajes}}

## Usuarios objetivo

{{A quién le habla — roles, tipo de empresa, segmento}}

## Features detectadas

- {{feature 1}}
- {{feature 2}}
- ...

## Pricing

{{Planes y precios si son públicos, o "(no publicado)"}}

## Posicionamiento

{{Mensajes clave, tagline, cómo se describe a sí mismo}}

## Diferenciadores

{{Qué dice que lo distingue de otras soluciones — según su propio discurso}}

## Notas del investigador

{{Observaciones libres: limitaciones del fetch, cosas que llamaron la atención,
dudas para preguntarle al usuario en la Q&A de discovery-research}}
```

## Prompt de referencia para WebFetch

Al llamar a `WebFetch`, usá un prompt parecido a este (ajustalo al contenido
real de la página, pero pedí siempre los mismos campos):

```
Analizá esta página de producto/competidor y extraé, en la medida en que la
página lo muestre:
1. Qué problema dice resolver (con sus propias palabras)
2. A qué usuarios/roles le habla
3. Lista de features/funcionalidades visibles
4. Pricing (planes y precios, si son públicos)
5. Mensajes de posicionamiento / tagline
6. Qué dice que lo diferencia de otras soluciones

Si algún punto no aparece en la página, decilo explícitamente en vez de
inferirlo o inventarlo.
```

## Cuándo un campo queda `(no publicado)`

- Pricing detrás de "contactanos" o un formulario de ventas.
- Features que requieren login para verse.
- Cualquier campo donde `WebFetch` no encontró información directa en la página
  (no completar con conocimiento previo del modelo sobre la empresa).

## Extensión futura (no implementada en v1)

El backend por defecto (`WebFetch`/`WebSearch`) no requiere credenciales, pero
tiene un límite conocido: sitios con mucho JavaScript client-side (SPAs que
renderizan el contenido después de cargar) o con protección anti-bot pueden
devolver una página vacía o un bloqueo.

Si en el futuro hace falta cubrir esos casos, el punto de extensión es la Fase 2
(`SKILL.md`): agregar un backend alternativo opcional, por ejemplo:

- **Playwright headless** — corre un navegador real, ejecuta el JS de la
  página, y extrae el HTML renderizado. No requiere API key, pero sí instalar
  Playwright y sus navegadores (`pip install playwright && playwright install`).
- **ScrapeGraph AI** (`SGAI_API_KEY`) — servicio cloud pago, útil para sitios
  particularmente hostiles al scraping. Solo tiene sentido si el usuario ya
  tiene su propia cuenta y key — nunca como dependencia obligatoria del v1.

Cualquiera de los dos sería un fallback opcional cuando `WebFetch` devuelve
contenido vacío o bloqueado, no un reemplazo del default.
