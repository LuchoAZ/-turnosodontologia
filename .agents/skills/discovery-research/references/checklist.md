# Checklist de Discovery — banco de preguntas por los 11 puntos

Mismo espíritu que el banco de `kb-creator`: tu trabajo no es rellenar campos
automáticamente sino hacer que el usuario (y, cuando hay scraping, los datos
reales de los competidores) clarifiquen el pensamiento antes de documentar.

## Reglas para hacer preguntas

1. **3-5 preguntas máximo por ronda.** Más es ruido — el usuario se cansa y
   empieza a responder cualquier cosa.
2. Cada pregunta con **opciones (a/b/c)** cuando tenga sentido, y un **"por qué
   importa"** explícito — si no podés explicar por qué importa, probablemente
   no haga falta preguntarla.
3. Si el scraping (Fase 1) ya respondió un punto, **no lo preguntes** — mostralo
   como afirmación a confirmar ("Vi que tus 3 competidores cobran entre $X y
   $Y, ¿tu rango de precio va por ahí o pensás algo distinto?").
4. **Detectá supuestos.** Si el usuario da algo por sentado ("obvio que va a
   necesitar login social"), preguntá el porqué — puede ser sesgo, no dato.

## Los 11 puntos

### 1. Problema que resuelve

> ¿Cuál es el problema concreto que este proyecto resuelve, y para quién
> específicamente?

**Por qué importa**: si no se puede responder en una frase, todo lo demás es
ruido — mismo criterio que P1 de `kb-creator`. Si hubo scraping, contrastá:
¿el problema que plantea el usuario es el mismo que resuelven los competidores,
o es distinto? Esa diferencia (o su ausencia) es información valiosa.

### 2. Usuarios / roles

> ¿Quiénes lo van a usar? Listá los roles con un verbo principal cada uno.

**Por qué importa**: define el RBAC futuro y la mitad de las pantallas. Si el
scraping mostró a quién le hablan los competidores, usalo de referencia — pero
no asumas que el usuario objetivo es el mismo.

### 3. Casos de uso

> Dame los 3-5 casos de uso principales, en formato "como [rol], quiero
> [acción] para [resultado]".

**Por qué importa**: son la base de las historias de usuario y de la Knowledge
Base que arma `kb-creator` después. Priorizá los que bloquean el MVP.

### 4. Competidores / soluciones existentes

> ¿Qué usás o mirás hoy para resolver esto (aunque sea a medias)? ¿Conocés
> alguna solución existente que se le parezca?

**Por qué importa**: si hubo scraping, esta pregunta ya viene resuelta —
mostrá el resumen de `scripts/collect_sources.py` y pedí que lo valide o
agregue algo que faltó. Si NO hubo scraping y el usuario menciona un
competidor concreto, ofrecé invocar `web-scraper` sobre esa URL antes de
seguir — es mejor dato real que suposición.

### 5. Funcionalidades necesarias

> De todo lo que este proyecto podría hacer, ¿qué es innegociable para la
> primera versión?

**Por qué importa**: define el MVP real, no el wishlist. Si el usuario da una
lista larga, empujá a priorizar (mismo patrón que "todo lo que se pueda" en la
tabla de anti-patrones más abajo).

### 6. Funcionalidades opcionales

> ¿Qué te gustaría tener pero no es bloqueante para lanzar?

**Por qué importa**: separar esto de "necesarias" evita que el scope crezca
antes de tener un MVP. Va directo al backlog post-lanzamiento.

### 7. Reglas de negocio

> ¿Hay reglas específicas del dominio que el sistema tiene que respetar sí o
> sí? (ej. "no se puede cancelar una reserva con menos de 24hs", límites,
> validaciones de negocio)

**Por qué importa**: estas reglas suelen vivir solo en la cabeza del usuario —
si no se documentan acá, se pierden y aparecen como bugs meses después.

### 8. Integraciones

> ¿Con qué sistemas externos tiene que hablar? (pagos, calendarios, WhatsApp,
> APIs de terceros, sistemas legacy de la organización)

**Por qué importa**: cada integración es una dependencia externa con su propio
riesgo (rate limits, costos, disponibilidad) — mapea directo a
`state.kb.discovery.needs_infra` y al stack que va a proponer `kb-creator`.

### 9. Restricciones

> ¿Hay algo dado de arriba que no se puede cambiar? (presupuesto, plazo,
> stack obligatorio, compliance, compatibilidad con algo existente)

**Por qué importa**: si la restricción es real, condiciona toda la
arquitectura. Distinguí restricción real de preferencia disfrazada de
restricción (mismo criterio que P4 de `kb-creator`).

### 10. Riesgos

> De todo lo que hablamos, ¿qué es lo que MÁS te preocupa que salga mal o que
> no sepas todavía?

**Por qué importa**: acá aplicás el espíritu de assumption-mapping — revisá
cada funcionalidad/decisión de los puntos 1-9 y preguntate cuáles son hechos
verificados y cuáles son supuestos sin probar. Los supuestos sin probar SON
los riesgos.

### 11. Preguntas abiertas

> ¿Qué quedó sin resolver? Cosas que ninguno de los dos sabe todavía y que hay
> que decidir antes de (o durante) construir.

**Por qué importa**: dejarlas explícitas en vez de que se resuelvan solas por
default en medio de la implementación. Es la lista que revisa el usuario antes
de dar por cerrado el Discovery.

## Patrones de respuesta a evitar

| Respuesta vaga | Tu respuesta |
|---|---|
| "todo lo que se pueda" | "no podemos hacer 'todo'. Dame 3 cosas concretas en orden de prioridad para la v1." |
| "el mismo problema que todos" | "decime en una frase el problema, con tus palabras, para tu usuario concreto — no la versión genérica." |
| "no sé, lo que sea normal" | "'normal' según quién — dame el contexto: quién lo usa, con qué presupuesto, con qué urgencia." |
| "no tengo competidores" | "¿cómo resuelve esto la gente hoy, aunque sea con una planilla o WhatsApp? eso también es competencia." |

## Cierre de cada ronda

Al final de cada ronda (y siempre antes del gate final de la Fase 3 del
`SKILL.md`), escribí:

```markdown
**Resumen de lo que entendí**:
- [Punto del checklist resuelto]
- ...

**Supuestos que estoy haciendo** (corregilos si no son ciertos):
- **Suposición**: [...]

**Preguntas abiertas / riesgos detectados**:
- [...]
```

Esto fuerza al usuario a corregir antes de que se escriba algo mal en
`discovery.md` — igual lógica que el cierre de ronda de `kb-creator`.
