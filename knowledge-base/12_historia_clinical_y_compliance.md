# Historia Clínica y Compliance

> **Extra de dominio** — la capa normativa que define el posicionamiento (DD-01) y la que más
> riesgo legal tiene. Módulo: `apps/api/src/modules/clinical` + `compliance`.
> Épica: E5 (`06_funcionalidades.md` US-040 a US-043). Flujo: 5 (`07_flujos_principales.md`).
> Reglas: RN-CMP-01 a RN-CMP-08 (`05_reglas_de_negocio.md`).

> ⚠️ **Advertencia de veracidad**: este documento describe el diseño técnico esperado y el marco
> normativo que el research identificó. **Los plazos, requisitos y textos legales concretos deben
> verificarse con asesoría legal antes de implementar.** El research los marcó como `[A]` o
> `[NE]`. Ver PQ-02, PQ-03, PQ-04, PQ-07. **Nada de este documento es asesoramiento legal.**

---

## Marco normativo aplicable

| Norma | Qué regula | Impacto en el sistema |
|-------|-----------|----------------------|
| **Ley 25.326** (Protección de Datos Personales) | Tratamiento de datos personales; derecho de acceso, rectificación, supresión | Solicitudes de acceso del paciente (AAIP), consentimiento, cifrado, auditoría |
| **Ley 26.529** (Profesionales de la Salud) | Derechos del paciente sobre su historia clínica; documentación de prácticas | Historia clínica, copia al paciente, consentimiento informado |
| **Ley provincial de ejercicio profesional** | Habilitación para el registro de prácticas | Parte del onboarding del profesional |

> **Verificar**: los plazos exactos de entrega de copia y de respuesta a solicitudes de acceso,
> y la交互 del contenido obligatorio, con la fuentes oficiales y un abogado. PQ-02, PQ-03.

---

## Historia clínica: inmutabilidad como principio de diseño

La historia clínica (`clinical_record`) y el odontograma (`chart_entry`) son **append-only por
trigger de base de datos** (RN-CMP-02):

```sql
-- Un UPDATE o DELETE sobre clinical_record lanza excepción. No hay excepción posible.
CREATE TRIGGER clinical_record_immutable
BEFORE UPDATE OR DELETE ON clinical_record
FOR EACH ROW EXECUTE FUNCTION reject_mutation();
```

**Por qué trigger de BD y no "no expongas un endpoint de borrado"**: porque un bug de ORM, un
script manual, o un futuro endpoint mal diseñado podrían saltarse la capa de aplicación. El
motor no. La inmutabilidad garantizada en la capa más baja posible.

**Cómo se corrige un error** (no se borra, se anexa):

```
clinical_record (v1, contenido="Pieza 16 = obturado")   -- el original queda intacto
        ↑ supersedes_id
clinical_record (v2, contenido="Pieza 16 = IMPLANTE (corrección de v1)", author=dentista2)
```

El estado vigente de una pieza es el de la entrada no-superseded más reciente (RN-CLI-03). La
historia completa queda para siempre — que es exactamente lo que un profesional de salud
necesita para defender su tratamiento.

---

## Cifrado de datos de salud (RN-CMP-01)

- `clinical_record.contenido`, los datos del odontograma y del periodontograma se cifran **en
  reposo** con una clave **por tenant**, derivada de una clave maestra en KMS.
- La rotación de claves se soporta vía `key_version` en los datos cifrados (sin downtime).
- En tránsito: TLS 1.3 a todos los servicios.
- **Los logs de aplicación nunca contienen datos clínicos** — esto es un **test automatizado**
  (RN-CMP-08), no una convención. Un log con un dato de salud o una clave fiscal en un agregador
  es una fuga de datos personales y de salud.

## Auditoría (`audit_log`) — append-only (RN-CMP-03)

Todo acceso a datos sensibles queda registrado:

```
tenant_id, actor_user_id, actor_rol, recurso, recurso_id, patient_id,
accion (READ|CREATE|UPDATE|DELETE|EXPORT|SIGN|ACCESS_REQUEST),
campos_afectados (para UPDATE), ip, user_agent, justificacion, created_at
```

- **Nadie** puede modificarlo ni borrarlo: ni el owner, ni el SuperAdmin. Trigger de BD.
- Registra: lectura de historia clínica, escritura, **exportación**, firma de consentimiento,
  y acceso de soporte con justificación.
- Es la defensa en caso de incidente ("¿quién vio la ficha de este paciente?") y el
  cumplimiento del principio de accountability de la Ley 25.326.

---

## Consentimiento informado (RN-CMP-05)

- **Plantillas versionadas**: `consent_template` con `version`. Un paciente que firmó la v2
  tiene firmado el texto de la v2, **aunque después actualices la plantilla a v3**.
- El `consent` guarda `template_version` **congelado** al firmar.
- **Evidencia de firma**: timestamp, IP, user agent, y **hash del PDF** firmado.
- **PDF inmutable** en S3 con versionado de bucket.
- **Firmado** bloquea procedimientos que lo requieren (RN-CLI-06): los marcados en
  `consent_template.obligatorio_para` (ej. extracción, endodoncia, radiografía).

> **Las plantillas base necesitan revisión legal** (SU-07, PQ-04). El sistema seedea
> marcadores/estructuras, pero el contenido legal debe ser aprobado antes de producción. No se
> escribe "consentimiento genérico" sin abogado: eso es un riesgo legal directo.

---

## Copia autenticada de historia clínica (US-041)

**Regla de negocio clave**: se **verifica la identidad del solicitante antes de entregar**
(RN-AU-06). No se entrega porque alguien con el DNI lo pidió.

Flujo completo en [Flujo 5](07_flujos_principales.md#flujo-5-copia-autenticada-de-historia-clínica-compliance).

- PDF legible, gratuito, con **sello de autenticidad y hash**.
- Se genera asíncronamente (job) y se entrega por canal seguro.
- El acceso a los datos **para generar la copia** queda auditado (RN-CMP-03).
- **Nunca se marca la solicitud `ATENDIDA` sin que la copia exista.**

> **El plazo legal de entrega está sin confirmar** (PQ-02). Está **parametrizado** en el código
> (`plazo_vencimiento`), no hardcodeado, para poder ajustarlo sin refactor cuando Legal confirme.

## Solicitudes de acceso (Ley 25.326 / AAIP) — US-042

`access_request` modela el derecho de acceso/rectificación/supresión/portabilidad:

```
recibida → en_verificacion → en_proceso → atendida
                                  └──→ denegada (con motivo)
                                  └──→ fuera_de_plazo
```

- Se registra **solicitante, DNI, tipo y fecha** de la solicitud.
- **Verificación de identidad antes de entregar** (RN-AU-06).
- Control de **plazo legal** (parametrizado; valor a confirmar — PQ-03).
- Alerta al owner cuando el plazo se acerca a vencer.
- Todo en `audit_log` (RN-CMP-03).

---

## Derechos de los pacientes y sus límites

| Derecho (Ley 25.326 / 26.529) | Cómo lo soporta el sistema |
|--------------------------------|------------------------------|
| Acceso a sus datos | `access_request` + copia autenticada |
| Rectificación | `access_request` tipo `rectificacion`; los datos clínicos se corrigen con `supersedes` (no se borran) |
| Supresión | `access_request` tipo `supresion`; se evalúa si aplica (datos de salud tienen，哪个義務 de conservación) — **verificar con Legal** |
| Portabilidad | Exportación de sus datos en formato libre (US-093 incluye, o standalone) |
| Baja de comunicaciones | `RN-COM-05`: baja de marketing, sin perder esenciales |

> **Tensión real**: el derecho de supresión vs. la obligación de conservar la historia clínica
> (que tiene plazos de conservación y es un deber del profesional). **Esta tensión legal no está
> resuelta** y debe ser resuelta con Legal antes de implementar la supresión (PQ-03 relacionado).

---

## RBAC de datos clínicos — fronteras duras (RN-CMP-04)

| Rol | Lectura de historia clínica | Escritura | Notas |
|-----|--------------------------|-----------|-------|
| Odontólogo | Sí, de sus turnos | Sí | Puede finalizar |
| Higienista/Asistente | Sí, scope limitado | Sí, dentro de su scope | **No** finaliza |
| Dirección clínica | Sí | Sí (agenda) | |
| Recepcionista | **NO** | **NO** | **Frontera dura**, no preferencia de UI |
| Administración/Facturación | Solo si el owner lo habilita por tenant (`billing.can_read_clinical`, default `false`) | NO | |
| Paciente | Solo la propia | No | Via OTP verificado |
| Laboratorio | **NO** | NO | Solo el pedido de trabajo |
| SuperAdmin | **NO** | NO | Acceso a logs/integraciones, no a la clínica |

**RN-EX-06**: ningún dato de salud de un paciente de un tenant es accesible desde otro tenant,
**incluyendo a través del SuperAdmin o de un job de soporte**.

> **La recepción no lee historia clínica** es una decisión deliberada y una frontera dura. Si la
> recepcionista necesita un dato clínico para explicar algo al paciente, **el sistema no se lo
> da** — el odontólogo se lo dice. Es lo que hace que la compliance sea una ventaja real y no un
> checkbox.

---

## Exportación y portabilidad (RN-CMP-07)

- Exportación de datos de un tenant: **asíncrona** (job), no en el request (puede ser lento).
- Genera `audit_log` tipo `EXPORT` con justificación.
- Formato **legible y libre** (no atado al sistema) — principio de portabilidad.
- No incluye datos de **otros** tenants (RN-EX-06).

---

## Checklist de implementación (E5)

- [ ] Triggers de BD para inmutabilidad de `clinical_record`, `chart_entry`, `audit_log`.
- [ ] Cifrado de contenido clínico en reposo (clave por tenant vía KMS) + `key_version`.
- [ ] Test automatizado de sanitizado de logs (falla el build si hay dato clínico o clave).
- [ ] `audit_log` append-only + endpoints de auditoría filtrados.
- [ ] Plantillas de consentimiento versionadas + congelado de versión al firmar.
- [ ] Firma digital (web) con evidencia + PDF inmutable en S3 (versionado).
- [ ] Generación de copia autenticada (PDF + hash + sello) en job.
- [ ] Flujo de `access_request` con verificación de identidad y control de plazo parametrizado.
- [ ] Guards de rol que **impiden** lectura clínica a recepción/admin/lab/superadmin (tests).
- [ ] Exportación asíncrona + audit.
- [ ] **Revisión legal** de plantillas y plazos antes de producción (PQ-02, PQ-03, PQ-04).

---

## Referencias (verificar vigencia con Legal)

- Texto oficial de la Ley 25.326 y suschandeyendas.
- Texto oficial de la Ley 26.529 (profesionales de la salud).
-(Guidelines de la AAIP sobre datos personales y salud.
- Jurisprudencia relevante si aplica.

> Este documento **no** es asesoramiento legal. Los plazos, requisitos y redacciones deben ser
> validados por un profesional del derecho antes de implementarse o moverse a producción.
