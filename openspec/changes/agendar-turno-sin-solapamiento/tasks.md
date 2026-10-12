# Tasks

> **Prerrequisitos (no son tasks de este change)**: aplicar este change requiere el stack de sus dependencias — C-01 (foundation-setup), C-02 (modelo `appointment` con `EXCLUDE USING gist` + RLS + extensión `btree_gist`, migración `008_agenda`), C-03 (sesión + scoping de tenant), C-05 (`chair`, `professional`, `availability_rule`), C-06 (`patient`). Si al momento del apply el modelo o la restricción `EXCLUDE` faltan, es un bloqueante de dependencia y se pausa — no se implementa el DDL acá.

## 1. Contrato compartido y cálculo de rango (TDD puro)

- [ ] 1.1 Definir en `packages/shared` el `CreateAppointmentSchema` (Zod: UUIDs de `professional_id`/`chair_id`, `patient_id` nullable, `inicio`/`fin` RFC 3339 coaccionados a `Date`, `fin > inicio`, `tipo_practica` opcional; `estado` por defecto `pendiente`, `origen` fijo `recepcion`) y la función pura `resolveTurnoRange` (RN-AG-03: duración por `tipo_practica`, buffers previo/posterior heredados de `availability_rule` — incluyéndolos en el rango ocupado, default `duracion_default_min` del profesional con buffers 0). Escribir primero los tests unitarios que fallan (payload válido, campos inválidos → issues de Zod, duración con buffers, sin tipo de práctica, `fin <= inicio` rechazado) y luego implementar hasta que `npm run test --workspace packages/shared` quede en verde. Verificación: la suite unitaria pasa y cubre schema y rango.

## 2. Alta del turno — 201 (backend)

- [ ] 2.1 RED: escribir el test de integración (Testcontainers Postgres real, siembra de **2 tenants**) de `POST /api/v1/appointments` autenticado con payload válido → `201` con el turno creado (`estado = pendiente`, `origen = recepcion`, `inicio`/`fin` en UTC) y que la respuesta no filtra `tenant_id`. Verificar que falla (aún no existe el módulo).
- [ ] 2.2 GREEN: crear el slice vertical `apps/api/src/appointments/` (controller + service, inyección por constructor): resolver `tenant_id` exclusivamente de la sesión/token (RN-TEN-03, guard provisto por C-03), abrir la transacción con `SET LOCAL app.current_tenant` y persistir con `prisma.$transaction`. Verificar que 2.1 pasa y que un `tenant_id` enviado en el body es ignorado.

## 3. Prevención de solapamiento — 409 (profesional y sillón)

- [ ] 3.1 RED→GREEN: escribir los tests de integración de solape por `professional_id` y por `chair_id` → `409` con `{ recurso, rangoEnConflicto }` (RN-AG-02), y que un turno `cancelado`/`no_asistio` **no** bloquea → `201`; implementar el overlap pre-check en aplicación (rango `[inicio, fin)`, estados activos, scoped al tenant) dentro de la transacción; corrida `npm run test:integration` en verde. Verificación: los tests de 409 pasan y nombran el recurso y el rango.

## 4. Garantía dura de la BD — doble booking bajo concurrencia

- [ ] 4.1 RED→GREEN: escribir el test de concurrencia (dos `create` simultáneos sobre el mismo `professional`/`chair`) → exactamente uno `201` y el otro `409` porque el `EXCLUDE USING gist` lo rechaza; implementar en el `ExceptionFilter` global el mapeo de la *exclusion violation* (`SQLSTATE 23P01`) al mismo contrato `409` de 3.1; verificar que la suite pasa y que ambos `409` (aplicación y BD) comparten el mismo shape. Verificación: el test de concurrencia pasa con Postgres real (sin mocks).

## 5. RN-AG-10 — paciente con turno solapado del mismo profesional

- [ ] 5.1 RED→GREEN: escribir los tests de RN-AG-10 (paciente con turno `pendiente`/`confirmado`/`en_curso` solapado del mismo `professional` → `409`; en otro rango, otro profesional, o `cancelado`/`no_asistio` → `201`) e implementar el chequeo del paciente dentro de la misma transacción. Verificación: la suite de integración de RN-AG-10 pasa.

## 6. Gate de aislamiento cross-tenant (RN-TEN-02) — tarea propia, gate de merge

- [ ] 6.1 Escribir el **test de aislamiento cross-tenant** como gate obligatorio de merge: con los 2 tenants sembrados, crear turnos homólogos solapados en ambos y verificar (a) que un request autenticado como A referenciando un `professional`/`chair`/`patient` del tenant B responde `404` (nunca `403` ni `200`) y no crea el turno, y (b) que los turnos de B no son visibles ni generan conflicto para A (RLS activa). La verificación incluye mutar temporalmente el scoping (quitar el filtro de tenant) y comprobar que el test **falla** — demostrando que el verde no es accidental. Verificación: `cross-tenant leak = 0`; sin este test el change no se mergea (RN-TEN-02).

## 7. UI — formulario mínimo de agendamiento (vertical slice)

- [ ] 7.1 RED→GREEN: implementar en `apps/web` la ruta `/turnos/nuevo` (Next.js 15 App Router + shadcn/ui): carga de `patient`/`professional`/`chair` en paralelo (sin waterfalls), validación pre-submit con el `CreateAppointmentSchema` compartido, conversión de hora local a UTC (RN-AG-09), y mapa de errores del endpoint (`409` → conflicto visible con recurso, `422` → errores por campo, `404` → "recurso no encontrado o sin acceso"); escribir el e2e Playwright (creación ok, solape visible, error 404 legible) y verificar que el formulario lo satisface. Verificación: `npx playwright test` en verde sobre el flujo del form.

## 8. Verificación de integración

- [ ] 8.1 Correr el pipeline completo del slice (`lint → typecheck → unit → integration → e2e`) en verde sobre el PR del change y documentar en `docs/appointments.md` el contrato del endpoint (`POST /api/v1/appointments`: `201`/`409` con recurso y rango /`422`/`404`/`401`, payload, reglas RN-AG citadas y ejemplo de curl). Verificación: pipeline en verde + documento con comandos ejecutables tal como están escritos.