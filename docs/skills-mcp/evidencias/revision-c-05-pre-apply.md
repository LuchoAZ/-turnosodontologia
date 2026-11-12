# Revisión de escenarios — c-05-clinic-setup (pre-apply)

> Gate de la skill `spec-scenario-review` ejecutado el **2026-11-11**, antes de escribir código.
> No evalúa "si la spec está linda": verifica que cada requisito tenga escenarios verificables
> (esperado / error de negocio / borde), que las reglas de negocio citadas no sean ambiguas y que el
> aislamiento cross-tenant esté cubierto. Ejecutado manualmente porque las sub-sesiones no tienen
> permiso para la tool `skill`.

## Veredicto

**LISTO PARA APLICAR**. 10 requisitos / 44 escenarios, todos con ≥3 escenarios, con las tres clases
cubiertas y con una tarea de verificación en `tasks.md` para cada escenario. Gate de tenancy completo
y bloqueante (task 6.4 incluye prueba de mutación).

> Ampliación del **2026-11-11** durante la implementación: el alta de profesional exige
> `especialidad_id` y no había forma de resolverlo sin hardcodear los UUID5 del seed. Se agregó el
> requisito **Catálogo visible de especialidades** (`GET /clinic/specialties`, S10.1–S10.3) y la task
> 4.7. La spec, el design (D1, D8) y el proposal quedaron actualizados y revalidados
> (`openspec validate c-05-clinic-setup --strict` → válido).
>
> Corrección del **2026-11-11** al cerrar el gate pre-archive: el requisito de desactivación ya exigía
> en prosa que un `id` de otro tenant respondiera `404 professional_not_found`, y el test
> `test_el_profesional_de_otro_tenant_es_indistinguible` ya lo verificaba, pero faltaba el escenario
> **S6.4**. Se agregó a la spec (44 escenarios) para que el artefacto y la prueba no diverjan. La task
> 4.6 y la lista de escenarios cross-tenant de esta revisión ya lo citaban.

## Cobertura por requisito

| Requisito | Escenarios | Esperado | Error de negocio | Borde | RN citada | Estado |
|---|---|---:|---|---|---|---|
| Lectura de sillones | S1.1–S1.3 | ✅ S1.1 | ✅ S1.2 | ✅ S1.3 | RN-EX-03, RN-TEN-02 | OK |
| Alta de sillón | S2.1–S2.5 | ✅ S2.1 | ✅ S2.2, S2.3 | ✅ S2.4, S2.5 | RN-AG-06, RN-TEN-04 | OK |
| Actualización y baja lógica de sillón | S3.1–S3.5 | ✅ S3.1, S3.2 | ✅ S3.4, S3.5 | ✅ S3.3 | RN-EX-03, RN-TEN-02 | OK |
| Lectura de profesionales | S4.1–S4.3 | ✅ S4.1 | ✅ S4.2 | ✅ S4.3 | RN-TEN-02 | OK |
| Alta de profesional | S5.1–S5.6 | ✅ S5.1 | ✅ S5.2–S5.5 | ✅ S5.6 | RN-TEN-04 | OK |
| Desactivación de profesional | S6.1–S6.4 | ✅ S6.1 | ✅ S6.2, S6.4 | ✅ S6.3 | RN-EX-03 | OK |
| Reglas de disponibilidad | S7.1–S7.8 | ✅ S7.1, S7.6 | ✅ S7.2–S7.5, S7.7, S7.8 | ✅ S7.5, S7.8 | RN-AG-03 | OK |
| Aislamiento cross-tenant | S8.1–S8.4 | ✅ S8.1 | ✅ S8.2, S8.4 | ✅ S8.3 | RN-TEN-02, RN-TEN-03 | OK |
| Pantalla de configuración | S9.1–S9.3 | ✅ S9.1 | ✅ S9.2, S9.3 | ✅ S9.3 | RN-TEN-04 | OK |
| Catálogo visible de especialidades | S10.1–S10.3 | ✅ S10.1 | ✅ S10.2 | ✅ S10.3 | RN-TEN-02 | OK |

## Huecos detectados

Ninguno bloqueante. Tres observaciones registradas para que no se pierdan:

1. **S2.4** (`dos sillones rx conviven`) no es un olvido de RN-AG-06: la regla es sobre *turnos
   solapados*, no sobre la cantidad de sillones. El escenario congela que C-05 **no** inventa una
   validación que la KB pone en la agenda; la tarea 1.2 deja el modelo preparado y la deuda anotada.
2. **S6.3** no puede verificar "la agenda no la ofrece" porque `appointment` no existe todavía: se
   verifica que la desactivación **no** borra las reglas, que es la parte que este change posee.
3. **S7.5** congela el solape parcial por servicio, no por `EXCLUDE`: `dia_semana` + `time` +
   `daterange` con columnas nullable no se expresan sin `btree_gist` y la KB no lo exige. La
   limitación de concurrencia está en `design.md` D6 y se documenta en `docs/clinic.md`.

## Tenancy (RN-TEN-02)

- [x] El change toca tres tablas nuevas con `tenant_id NOT NULL` (`chair`, `professional`,
      `availability_rule`).
- [x] Hay escenario cross-tenant explícito: S1.2, S2.5, S3.5, S5.4, S5.6, S6.4, S7.7, S8.1–S8.4,
      S10.3 (una especialidad propia de B no se lista ni se puede usar desde A).
- [x] El `tenant_id` sale del token/sesión; en body responde `422 invalid_request` y en query/header
      se ignora (S8.4).
- [x] `tasks.md` incluye el gate con prueba de mutación: 6.1, 6.2, 6.3 y 6.4.
- [x] La única tabla sin RLS (`specialty`) se valida explícitamente (`tenant_id IS NULL OR = :tid`)
      y tiene sus escenarios propios (S5.4 y S10.1–S10.3).

## Verificación en tasks.md

| Escenario (grupo) | Tareas |
|---|---|
| S1.1–S1.3 | 3.1, 3.2 |
| S2.1–S2.5 | 3.3 |
| S3.1–S3.5 | 3.4, 3.5 |
| S4.1–S4.3 | 4.1, 4.2 |
| S5.1–S5.6 | 4.3, 4.4, 4.5 |
| S6.1–S6.4 | 4.6 |
| S7.1–S7.8 | 5.1–5.7, 2.3–2.5 |
| S8.1–S8.4 | 1.4, 6.1–6.4 |
| S9.1–S9.3 | 7.1–7.5, 8.1, 8.2 |
| S10.1–S10.3 | 4.7 |

## Próximo paso

Aplicar con Strict TDD en el orden de `tasks.md`: migración y modelos (1.x), validación pura (2.x),
sillones (3.x), profesionales (4.x), disponibilidad (5.x), gate RLS (6.x), frontend (7.x), e2e (8.x) y
cierre (9.x). El gate de tenancy (6.4) es bloqueante de merge.
