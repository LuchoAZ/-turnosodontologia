# Gestión Odontológica PyME — Base de Conocimiento

Base de conocimiento generada **interactivamente** (`kb-creator`, Mode B) a partir de:
- Research competitivo de 20 sistemas verificados (`discovery/discovery.md`, 2026-10-01)
- Ronda 1 de preguntas estratégicas (Q1–Q5), respondida con defaults aprobados por el usuario

> **Estado**: v0.1 — MVP. Documento de arquitectura y producto, **no** es documentación de código.
> Todo lo relativo a normativa (ARCA, Ley 25.326, Ley 26.529) requiere validación contra
> el texto oficial vigente y asesoría legal antes de implementar. Ver
> [`10_preguntas_abiertas.md`](10_preguntas_abiertas.md).

## Índice de Archivos

| # | Archivo | Contenido | Owner |
|---|---------|-----------|-------|
| 01 | [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito, enfoque compliance-first, actores, alcance v0.1, fuera de alcance, métricas | Product Owner |
| 02 | [02_descripcion_general.md](02_descripcion_general.md) | Stack TypeScript, arquitectura multi-tenant, integraciones externas, superficie REST | Tech Lead |
| 03 | [03_actores_y_roles.md](03_actores_y_roles.md) | 9 actores, matriz RBAC, rutas públicas | Product + Tech Lead |
| 04 | [04_modelo_de_datos.md](04_modelo_de_datos.md) | 8 dominios, ERD, ~30 entidades, aislamiento por tenant, seed data | Tech Lead |
| 05 | [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | RN codificadas en 9 dominios + excepciones globales | Domain Owner |
| 06 | [06_funcionalidades.md](06_funcionalidades.md) | 10 épicas, 38 historias de usuario con criterios de aceptación | Product Owner |
| 07 | [07_flujos_principales.md](07_flujos_principales.md) | 6 flujos end-to-end con casos de error | Tech Lead |
| 08 | [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Patrones, estructura de directorios, seguridad, env vars | Tech Lead |
| 09 | [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | 11 decisiones documentadas (DD) + 9 supuestos (SU) | Tech Lead + PO |
| 10 | [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | 5 inconsistencias detectadas + 11 preguntas priorizadas | Product Owner |
| 11 | [11_facturacion_arca.md](11_facturacion_arca.md) | *Extra* — Comprobantes A/B/C/M, habilitación, WSAA, X.509 por tenant, idempotencia | Domain Owner |
| 12 | [12_historia_clinical_y_compliance.md](12_historia_clinical_y_compliance.md) | *Extra* — Ley 26.529, Ley 25.326 + AAIP, inmutabilidad, copia autenticada | Domain Owner |

## Quick Start para Desarrolladores

1. **Entender el dominio y por qué** → [`01_vision_y_objetivos.md`](01_vision_y_objetivos.md)
2. **Entender quién hace qué y con qué permisos** → [`03_actores_y_roles.md`](03_actores_y_roles.md)
3. **Entender los datos y el aislamiento multi-tenant** → [`04_modelo_de_datos.md`](04_modelo_de_datos.md)
4. **Entender las reglas que NO se pueden romper** → [`05_reglas_de_negocio.md`](05_reglas_de_negocio.md)
5. **Entender la arquitectura y el stack** → [`02_descripcion_general.md`](02_descripcion_general.md), [`08_arquitectura_propuesta.md`](08_arquitectura_propuesta.md)
6. **Entender las dos piezas de mayor riesgo** → [`11_facturacion_arca.md`](11_facturacion_arca.md), [`12_historia_clinical_y_compliance.md`](12_historia_clinical_y_compliance.md)
7. **Implementar** → [`07_flujos_principales.md`](07_flujos_principales.md), [`06_funcionalidades.md`](06_funcionalidades.md)
8. **Antes de codificar cualquier cosa** → [`10_preguntas_abiertas.md`](10_preguntas_abiertas.md)

## Las dos piezas de mayor riesgo

El proyecto tiene **dos** fuentes de riesgo dominante, y ninguna de las dos es "programar una agenda":

1. **Facturación ARCA end-to-end con identidad fiscal por tenant**
   Cada clínica emite con **su propio certificado X.509**. No es "integrar con AFIP una vez";
   es 1 integración N veces, con altas, vencimientos yToken WSAA por cliente.
   → [`11_facturacion_arca.md`](11_facturacion_arca.md)

2. **Historia clínica legalmente defendible**
   Datos sensibles de salud, inmutabilidad real, copia autenticada y respuesta a la AAIP.
   → [`12_historia_clinical_y_compliance.md`](12_historia_clinical_y_compliance.md)

## Resumen Ejecutivo

Sistema SaaS multi-tenant de gestión odontológica para **clínicas PyME de 3 a 10 sillones**
multiprofesionales en Argentina, con stack TypeScript end-to-end (Next.js + NestJS +
PostgreSQL + Redis) sobre nube.

El **posicionamiento es compliance-first**, no features-first. El relevamiento de 20
competidores dio un resultado que define la estrategia: **la agenda con reservas online ya no
es un problema** — los 20 la tienen. Los vacíos reales están en la capa normativa
(ARCA clase A real, nomencladores por obra social, historia clínica defendible bajo
Ley 26.529 + Ley 25.326) y en la unidad de capacidad **sillón**, que casi nadie modela bien.

El MVP cubre 10 capacidades imprescindibles y **excluye explícitamente obra social**
(la alternativa (c) fue rechazada: es el mayor costo operativo recurrente y agrega ~2 meses
de plazo). Se comercializa por **suscripción en pesos, sin packs de consumibles y sin tier
gratis** — el único free ya documentado y bien crcído está cubierto por competidores.

Equipo asumido: **2–4 devs, sin deadline duro, fases por capability y no por calendario.**
