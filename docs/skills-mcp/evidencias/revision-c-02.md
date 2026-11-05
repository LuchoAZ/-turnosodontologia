# Evidencia — `spec-scenario-review` sobre `c-02-core-models-tenancy`

**Fecha de ejecución**: 2026-11-05 · **Skill**: `spec-scenario-review` (`.agents/skills/spec-scenario-review/SKILL.md`)
**Change revisado**: `openspec/changes/c-02-core-models-tenancy/`
**Entradas leídas**: `proposal.md`, `design.md`, `specs/platform-tenancy/spec.md`, `tasks.md`,
`knowledge-base/05_reglas_de_negocio.md` (§ Tenancy, § Excepciones), `knowledge-base/04_modelo_de_datos.md`
(§ Tenancy, § Catálogos, § Estrategia de aislamiento), `knowledge-base/03_actores_y_roles.md` (§ roles base).

---

# Revisión de escenarios — c-02-core-models-tenancy

## Veredicto
**LISTO PARA APLICAR**

## Cobertura por requisito
| Requisito | Esperado | Error de negocio | Borde | RN citada | Estado |
|-----------|----------|------------------|-------|-----------|--------|
| Modelo base multi-tenant con migración versionada | ✅ | ✅ (sin tenant `23502`, user inexistente `23503`, global duplicado) | ✅ (global + override coexisten) | RN-TEN-01/02 | OK |
| Unicidad del owner activo por tenant | ✅ (primer owner) | ✅ (segundo owner `23505`) | ✅ (owner inactivo no bloquea) | RN-TEN-04 | OK |
| RLS fail-closed en tablas tenant-scoped | ✅ (solo sus filas) | ✅ (escritura `42501`, update/delete 0 filas) | ✅ (sin contexto 0 filas; catálogo global vs override) | RN-TEN-02 | OK |
| Contexto de tenant por transacción, parameterizado | ✅ | ✅ (UUID inválido rechazado) | ✅ (no leak entre transacciones del pool) | RN-TEN-02/03 | OK |
| TenantGuard resuelve el tenant del token, nunca del body | ✅ | ✅ (sin claim → `401`) | ✅ (claim inválido; `tenant_id` en body ignorado) | RN-TEN-03 | OK |
| Validación del CUIT del tenant | ✅ (normaliza) | ✅ (dígito verificador) | ✅ (longitud/caracteres inválidos) | RN-TEN-01 | OK |
| Seed de catálogos base | ✅ (2/9/80 + enum) | ✅ (tenant no escribe el global) | ✅ (downgrade reversible) | RN-EX-05, RN-TEN-02 | OK |

## Huecos detectados
**Ninguno pendiente.**

Durante la primera pasada se detectó y cerró un hueco real:

1. **Unicidad del owner activo (RN-TEN-04)**: la KB exige *exactamente un* `owner` activo por
   tenant y `membership` es de este change, pero la spec no lo cubría. **Cerrado**: se agregó el
   requisito con 3 escenarios y el índice único parcial `uq_membership_owner_activo`
   (`tenant_id WHERE rol = 'owner' AND activo`). La invariante "cero owners" queda explícitamente
   fuera de alcance (transacción de transferencia, C-04). RED verificado: sin el índice, el test
   del segundo owner falla con `DID NOT RAISE IntegrityError`.

## Tenancy (RN-TEN-02)
- [x] El change toca tablas con `tenant_id` (`membership`, `price_concept`)
- [x] Hay escenario cross-tenant (requisito "RLS fail-closed": A vs B en lectura, escritura,
      update y delete)
- [x] `tenant_id` sale del token, no del body (requisito "TenantGuard" + escenario del body
      ignorado)
- [x] `tasks.md` incluye el test de aislamiento (3.1, 3.3, 4.1) con **prueba de mutación** (4.1)

**Resultado del check**: completo. Sin bloqueantes de tenancy.

## Verificación en tasks.md
| Escenario | Tarea de verificación | Estado |
|-----------|----------------------|--------|
| Migración crea tablas, enum e índices | 2.1 / 2.2 | ✅ |
| Membership sin tenant (`23502`) / user inexistente (`23503`) | 2.1 / 2.2 | ✅ |
| Código global duplicado y override permitido | 2.1 / 2.2 | ✅ |
| Segundo owner activo (`23505`) / owner inactivo no bloquea | 2.5 / 2.6 | ✅ |
| Seed 2 monedas, 9 especialidades, 80 conceptos | 2.3 / 2.4 | ✅ |
| Un tenant solo ve sus filas | 3.1 / 3.2 | ✅ |
| Sin contexto → 0 filas | 3.1 / 3.2 | ✅ |
| Update/delete cross-tenant afectan 0 filas | 3.1 / 3.2 | ✅ |
| Escritura cross-tenant (`42501`) | 3.3 / 3.4 | ✅ |
| Tenant no escribe el catálogo global (`42501`) | 3.3 / 3.4 | ✅ |
| Catálogo global visible; override solo para su tenant | 3.3 / 3.4 | ✅ |
| Contexto aplicado / UUID inválido | 1.5 / 1.6 | ✅ |
| No leak entre transacciones del pool | 3.5 | ✅ |
| Tenant de claims / sin claim / claim inválido / body ignorado | 1.3 / 1.4 | ✅ |
| CUIT válido / dígito / formato | 1.1 / 1.2 | ✅ |
| Downgrade reversible | 5.2 | ✅ |
| Gate de mutación RN-TEN-02 | 4.1 | ✅ |
| Documentación | 5.3 | ✅ |

## Próximo paso
1. Archivar el change con `openspec archive c-02-core-models-tenancy --yes` (ya validado con
   `openspec validate --strict`).
2. Cargar el requisito `platform-tenancy` en las specs principales.
3. C-03 (auth-sessions) consume `TenantGuard` y `set_tenant_context` como dependencia FastAPI.
