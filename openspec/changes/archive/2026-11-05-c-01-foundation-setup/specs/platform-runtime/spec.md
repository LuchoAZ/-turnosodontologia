# Spec Delta

## Purpose

Define el contrato operativo de arranque y estado de los servicios de la plataforma: validación fail-fast de la configuración, sondas de salud y readiness, y el bootstrap de observabilidad que los changes posteriores extienden.

## ADDED Requirements

### Requirement: Validación de configuración al arranque

El runtime MUST validar toda la configuración de entorno al iniciar y MUST negarse a arrancar si falta o es inválida una variable requerida. La validación MUST ocurrir antes de aceptar tráfico; no se permite descubrir la falta de configuración en runtime.

#### Scenario: Arranque con configuración completa

- **WHEN** el proceso inicia con todas las variables de entorno requeridas presentes y válidas
- **THEN** el servicio arranca correctamente y expone sus sondas operativas

#### Scenario: Arranque con una variable requerida ausente

- **WHEN** el proceso inicia con una variable de entorno requerida ausente
- **THEN** el proceso termina con estado de error y el mensaje identifica la variable faltante

#### Scenario: Arranque con una variable requerida inválida

- **WHEN** el proceso inicia con una variable requerida presente pero con un valor inválido
- **THEN** el proceso termina con estado de error y el mensaje identifica la variable y el motivo de invalidez

### Requirement: Sonda de liveness

El servicio MUST exponer `GET /health` como sonda de liveness. La respuesta MUST indicar que el proceso está vivo y MUST NOT incluir datos de negocio ni depender de recursos externos para responder.

#### Scenario: Proceso vivo responde liveness

- **WHEN** se invoca `GET /health` sobre un proceso en ejecución
- **THEN** la respuesta es `200` e indica estado saludable sin incluir datos de negocio

#### Scenario: Liveness no depende de servicios externos

- **WHEN** una dependencia externa (base de datos o cola) está caída
- **THEN** `GET /health` sigue respondiendo `200` porque la liveness solo refleja el proceso

### Requirement: Sonda de readiness

El servicio MUST exponer `GET /ready` como sonda de readiness. La respuesta MUST verificar que las dependencias requeridas (base de datos y cola) estén alcanzables: `200` cuando todas lo están y `503` cuando alguna no lo está.

#### Scenario: Readiness con dependencias alcanzables

- **WHEN** se invoca `GET /ready` y la base de datos y la cola están alcanzables
- **THEN** la respuesta es `200` e indica que el servicio puede recibir tráfico

#### Scenario: Readiness con una dependencia caída

- **WHEN** se invoca `GET /ready` y alguna dependencia requerida no está alcanzable
- **THEN** la respuesta es `503` e identifica la dependencia no disponible

### Requirement: Bootstrap de trazabilidad distribuida

El runtime MUST inicializar una traza distribuida (OpenTelemetry) al arrancar, MUST registrar un nombre de servicio y MUST exponer un contexto de correlación extensible que los changes posteriores enriquecen con atributos de dominio (por ejemplo `tenant_id`). Si el exportador no está configurado, el servicio MUST arrancar igual sin bloquearse.

#### Scenario: Arranque con exportador configurado

- **WHEN** el proceso inicia con un endpoint de exportación de trazas configurado
- **THEN** la traza queda inicializada con el nombre de servicio del runtime

#### Scenario: Arranque sin exportador configurado

- **WHEN** el proceso inicia sin endpoint de exportación de trazas
- **THEN** el servicio arranca normalmente en modo degradado, sin fallar por ausencia del exportador

### Requirement: Captura de errores no manejados

El runtime MUST inicializar la captura de errores (Sentry) al arrancar cuando hay un DSN configurado, de modo que los errores no manejados del proceso queden reportados. Si no hay DSN configurado, el servicio MUST arrancar igual sin bloquearse.

#### Scenario: Error no manejado se reporta

- **WHEN** el proceso arranca con un DSN configurado y ocurre un error no manejado
- **THEN** el error se envía al colector de errores

#### Scenario: Arranque sin DSN

- **WHEN** el proceso inicia sin DSN de errores configurado
- **THEN** el servicio arranca normalmente en modo degradado, sin fallar por ausencia del DSN
