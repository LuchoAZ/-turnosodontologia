# Revisión de escenarios — c-06-patients (pre-apply)

> Gate `spec-scenario-review` (`.agents/skills/spec-scenario-review/SKILL.md`) ejecutado el 2026-11-11
> sobre `proposal.md`, `design.md`, `specs/clinic/patients/spec.md`, `specs/platform-rbac/spec.md` y
> `tasks.md`, cruzado con `knowledge-base/03_actores_y_roles.md`, `04_modelo_de_datos.md`,
> `05_reglas_de_negocio.md`, `06_funcionalidades.md` (§ US-030), `10_preguntas_abiertas.md` y
> `openspec/specs/platform-rbac/spec.md`.
>
> **Segunda pasada**: este informe reemplaza el veredicto anterior (`FALTAN ESCENARIOS`). Se agregaron
> los bordes faltantes (S1.6, S2.6, S4.5, S4.6, S5.5, S5.6, S6.6, S6.7, S11.5), se corrigió el typo de
> S6.4, se cerró la ambigüedad del dedupe blando, se agregó el segundo `MODIFIED` de `platform-rbac`
> (fronteras duras: C-06 → C-09), se cambió la PQ a `PQ-17` y se corrigió `CHANGES.md` en la task 7.2.

## Veredicto

**LISTO PARA APLICAR**

La tenencia (RN-TEN-02) está completa, los 13 requisitos tienen camino esperado, error de negocio o
borde de secuencia, y cada escenario de la delta tiene al menos una tarea de verificación en
`tasks.md`. El delta `MODIFIED` de `platform-rbac` conserva ambos requisitos íntegros (verificado con
diff token a token: el primero solo cambia números y suma `patient.*`; el segundo solo cambia C-06 por
C-09). No quedan huecos bloqueantes.

## Cobertura por requisito

| Requisito | Escenarios | Esperado | Error de negocio | Borde | RN citada | Estado |
|---|---|---|---|---|---|---|
| Listado de pacientes del tenant | S1.1–S1.6 (6) | ✅ S1.1 | ✅ S1.2 (403) | ✅ S1.3 vacío, S1.4 paginación, S1.5 cross-tenant, S1.6 `incluir_inactivos` | RN-TEN-02 / RN-TEN-03 (Purpose) | ✅ |
| Búsqueda por nombre, DNI o teléfono | S2.1–S2.6 (6) | ✅ S2.1, S2.2 | ✅ S2.5 (422, límite) | ✅ S2.3 comodines `%`/`_`/`\`, S2.4 cross-tenant, S2.6 `q` vacío | RN-TEN-02 (S2.4) | ✅ |
| Alta de paciente con HCE | S3.1–S3.6 (6) | ✅ S3.1, S3.5 | ✅ S3.2 (403), S3.3 (reservados) | ✅ S3.4 datos inválidos, S3.6 trim | RN-CMP-04 (S3.5) | ✅ |
| HCE secuencial y no reciclable | S4.1–S4.6 (6) | ✅ S4.1, S4.2 | n/a (la red es el `UNIQUE`; se cubre con S4.5) | ✅ S4.3 no reciclado, S4.4 concurrencia, S4.5 sin huecos, S4.6 desborde | RN-CLI-01 ✅ | ✅ |
| Duplicado por DNI | S5.1–S5.6 (6) | ✅ S5.1 | ✅ S5.2 (`confirmar_duplicado` no lo vence) | ✅ S5.3 cross-tenant, S5.4 varios `NULL`, S5.5 carrera→409, S5.6 DNI de baja lógica | RN-CLI-01 / RN-EX-03 ✅ | ✅ |
| Posible duplicado por nombre o teléfono | S6.1–S6.7 (7) | ✅ S6.3, S6.4 | ✅ S6.1, S6.2 | ✅ S6.5 cross-tenant, S6.6 homónimo inactivo, S6.7 tope de 5 candidatos | RN-CLI-01 (implícita) / RN-EX-03 | ✅ |
| Lectura de un paciente por id | S7.1–S7.3 (3) | ✅ S7.1 | ✅ S7.3 (403) | ✅ S7.2 404 indistinguible | RN-TEN-02 (S7.2) | ✅ |
| Actualización de la ficha | S8.1–S8.6 (6) | ✅ S8.1, S8.5 | ✅ S8.3 (409), S8.6 (403) | ✅ S8.2 reservados, S8.4 cross-tenant | RN-TEN-02, RN-CLI-01 | ✅ |
| Frontera clínica de la ficha | S9.1–S9.3 (3) | ✅ S9.1, S9.2 | ✅ S9.3 | ✅ S9.1 recorre los 4 endpoints | RN-CMP-04 ✅ | ✅ |
| Permisos de pacientes en la matriz RBAC | S10.1–S10.3 (3) | ✅ S10.1 | ✅ S10.2 | ✅ S10.3 fail-closed | KB 03 (`03_actores_y_roles.md:29-48`) | ✅ |
| Pantalla de pacientes en el SPA | S11.1–S11.5 (5) | ✅ S11.1, S11.2, S11.4 | ✅ S11.3 (DNI duplicado), S11.5 (`forbidden`) | ✅ S11.5 sin `patient.read` y sin `patient.update` | — | ✅ |
| **platform-rbac** (MODIFIED 1): catálogo y matriz | S1.1–S1.4 (4) | ✅ S1.1 | ✅ S1.3 | ✅ S1.4 fail-closed, 9×19 | KB 03 | ✅ |
| **platform-rbac** (MODIFIED 2): fronteras duras | S3.1–S3.5 (5) | ✅ S3.1, S3.2 | ✅ S3.3, S3.5 | ✅ S3.4 unión de memberships | RN-CMP-04 ✅ | ✅ |

**Integridad del delta `MODIFIED` de `platform-rbac`** (diff token a token contra
`openspec/specs/platform-rbac/spec.md`):

- Requisito "Catálogo de permisos atómicos y matriz rol→permiso completa": 465 → 474 tokens; las 10
  diferencias son exactamente `18→19`, `16→17`, `17→18`, `(18)→(19)`, `(líneas 33-48)` →
  `(§ Recursos estructurales)`, `patient.*` sumado en S1.1 y S1.3, `filas→roles` y `18→19` en S1.4.
  No se perdió texto ni escenarios.
- Requisito "Fronteras duras clínicas (RN-CMP-04)": 473 → 483 tokens; las 2 diferencias son
  `Mientras el dominio clínico no exista (C-06)` → `(llega con C-09; la ficha demográfica de C-06 no lo
  reemplaza)` y `la capacidad se completa en C-06` → `C-09`. Los 5 escenarios (S3.1–S3.5) están
  íntegros.

## Huecos del gate anterior — estado

| # | Hueco | Estado |
|---|---|---|
| 1 | PQ-12 pisaba una pregunta existente | ✅ Corregido: `PQ-17` en `proposal.md:74`, `design.md:245` y `tasks.md` 1.3. `grep PQ-12` en el change: 0 resultados. |
| 2 | S10.3 sin tarea | ✅ `tasks.md` 1.1 lo cita y describe la verificación fail-closed. |
| 3 | HCE "alta fallida no deja hueco" | ✅ `S4.5` + requisito (revertir juntos) + task 3.2/4.4. |
| 4 | HCE desborde >999999 | ✅ `S4.6` + requisito (`f"{secuencia:06d}"` y 7 dígitos) + task 3.2. |
| 5 | DNI carrera chequeo→INSERT | ✅ `S5.5` + requisito ("nunca `500`") + task 3.4/4.4. |
| 6 | DNI de paciente con `deleted_at` | ✅ `S5.6` + requisito ("el índice no filtra por baja lógica") + task 3.4/4.4. |
| 7 | Dedupe blando ambiguo | ✅ Requisito fija `deleted_at IS NULL` y `S6.6`. |
| 8 | Tope de 5 candidatos | ✅ Requisito ("como máximo 5") + `S6.7`. |
| 9 | Typo S6.4 | ✅ "responde `201` con la ficha y su `numero_historia_clinica`". |
| 10 | Pantalla sin `forbidden` ni edición oculta | ✅ `S11.5` + tasks 5.2/5.5. |
| 11 | `incluir_inactivos` sin escenario | ✅ `S1.6` + task 4.2. |
| 12 | `q` vacío sin escenario | ✅ `S2.6` + task 4.2. |
| 13 | S2.3 no probaba `_` ni `\` | ✅ S2.3 extendido + task 3.5/4.2. |
| 14 | `platform-rbac` con "se completa en C-06" | ✅ Segundo `MODIFIED` con C-09 y 5 escenarios íntegros. |
| 15 | `CHANGES.md` contradice el alcance | ✅ Task 7.2 ordena quitar `timeline` (línea ~267) y "Alergias… destacadas" (línea ~270). |
| 16 | `patient.user_id` sin integridad cross-tenant | ✅ `design.md` D3 registra la deuda: nullable, ningún DTO lo escribe, FK simple por `user` global; task 7.1 la documenta. |

Observaciones menores ya resueltas o justificadas:

- **S4.3** (baja lógica) se monta por fixture/SQL directo, no por HTTP, porque C-06 no expone `DELETE`.
  La task 3.2 lo dice explícitamente.
- **`patient.delete` sin endpoint** es decisión justificada (se declara para no cambiar la matriz dos
  veces; la baja con motivo es C-13) y `patient` **no** entra en `_NO_PHYSICAL_DELETE`, que es solo
  para HC/odontograma (RN-CMP-02).
- **`alergias`/`alerta_clinica` diferidos a C-09** es coherente con RN-CMP-04 y con
  `04_modelo_de_datos.md:245-246`; la contradicción con US-030 queda registrada como PQ-17 (task 1.3).

## Tenancy (RN-TEN-02)

- [x] El change toca tablas con `tenant_id`: `patient` y `patient_counter`, ambas `tenant_id uuid NOT
      NULL` (`design.md` D3).
- [x] RLS activa y forzada: `ENABLE` + `FORCE ROW LEVEL SECURITY` + política `USING`/`WITH CHECK` con
      `app.current_tenant`, grants a `odontologia_app`, downgrade que no deja RLS huérfana.
- [x] Escenarios cross-tenant explícitos para **leer/listar** (S1.5), **buscar** (S2.4), **crear**
      (S5.3, S6.5), **actualizar** (S8.4) y **HCE independiente** (S4.2).
- [x] El `tenant_id` sale del token y nunca del body/query: requisito del alta + S3.3 (`tenant_id` en
      el cuerpo → `422` sin crear fila).
- [x] `tasks.md` incluye el test de aislamiento **con mutación**: 2.5, 4.8 y 4.9
      (`ALTER TABLE patient DISABLE ROW LEVEL SECURITY`) con evidencia en
      `docs/skills-mcp/evidencias/gate-rls-c-06.md`, cubriendo también `patient_counter`.
- [x] `patient.user_id` no puede apuntar a otro tenant: ningún DTO lo acepta (`extra="forbid"`) y la
      deuda queda documentada.

Sin bloqueantes de aislamiento.

## Verificación en tasks.md

| Escenario | Tarea de verificación | Estado |
|---|---|---|
| S1.1–S1.6 (listado, paginación, inactivos, cross-tenant) | 4.2 (+4.8 para S1.5) | ✅ |
| S2.1–S2.6 (búsqueda, comodines, `q` vacío, límite, cross-tenant) | 4.2 + 3.1 + 3.5 (+4.8 para S2.4) | ✅ |
| S3.1–S3.6 (alta, 403, reservados, inválidos, trim) | 4.4 (+4.1 para S3.3/S3.4/S3.6) | ✅ |
| S4.1–S4.6 (secuencia, por tenant, baja lógica, concurrencia, sin huecos, desborde) | 3.2 (+4.4 para S4.5) | ✅ |
| S5.1–S5.6 (DNI duplicado, confirmar, cross-tenant, NULL, carrera, baja lógica) | 4.4 + 3.4 (+4.8 para S5.3) | ✅ |
| S6.1–S6.7 (dedupe blando, confirmar, sin coincidencias, cross-tenant, inactivo, tope) | 4.4 + 3.4 (+4.8 para S6.5) | ✅ |
| S7.1–S7.3 (lectura, 404 indistinguible, 403) | 4.3 (+4.8 para S7.2) | ✅ |
| S8.1–S8.6 (update, reservados, DNI 409, 404 ajeno, búsqueda, 403) | 4.5 (+4.1 para S8.2, +4.8 para S8.4) | ✅ |
| S9.1–S9.3 (contrato sin clínicos, recepción fuera de HC, campo clínico 422) | 4.1 + 4.2 + 4.6 + 4.7 | ✅ |
| S10.1–S10.3 (matriz, catálogo 19/61, fail-closed) | 1.1 + 1.2 | ✅ |
| S11.1–S11.5 (backend real, alta con HCE, DNI duplicado, confirmación, permisos) | 5.2 + 5.3 + 5.4 + 5.5 + 5.6 | ✅ |
| platform-rbac S1.1–S1.4 | 1.1 + 1.3 + 1.4 | ✅ |
| platform-rbac S3.1–S3.2 | 4.6 (sonda: `403` a recepción, `501` a clínicos) | ✅ |
| platform-rbac S3.3–S3.5 | Tests preexistentes de C-04 (`test_matrix.py`, `test_guard.py`), sin cambio de comportamiento (task 1.4) | ✅ |

## Próximo paso

- Aplicar el change con `/opsx:apply c-06-patients` (tasks 1 a 8, Strict TDD por bloque).
- Al implementar, mantener la PQ-17 en `knowledge-base/10_preguntas_abiertas.md` (task 1.3) y la
  corrección de `CHANGES.md:267`/`:270` en la task 7.2.
- Antes de archivar, volver a correr el gate contra lo implementado (task 8.3) y guardar
  `docs/skills-mcp/evidencias/revision-c-06-pre-archive.md` con escenario → test ejecutado.
