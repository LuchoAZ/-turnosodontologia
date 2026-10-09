# Actores y Roles

## Actors del sistema

| Actor | Descripción | Cómo interactúa |
|-------|-------------|-----------------|
| **SuperAdmin (nuestro)** | Operador del SaaS. Da de alta tenants, monitorea integraciones, NO ve datos clínicos de pacientes. | Consola interna `/admin`. Acceso **auditado y justificado**. Solo.metadata y soporte; jamás ficha ni odontograma. |
| **Owner / Administrador** | Dueño de la clínica. Decide todo: config, precios, roles, facturación. | UI interna. Único que puede dar de baja usuarios, editarliquidaciones y ver reportes financieros. |
| **Dirección clínica** | Responsable del trabajo clínico. Administra agenda de los profesionales, sin acceso a lo financiero. | UI interna, scope `clinical_admin`. |
| **Odontólogo** | Profesional tratante. Escribe historia clínica y odontograma. | UI interna + modo "en consulta" optimizado para tablet/teléfono. |
| **Higienista / Asistente** | Ejecuta procedimientos delegables (limpieza, control de placa). | Mismo modo consulta, **su propio login**, sin poder firmar odontograma final. |
| **Recepcionista** | Agenda, reprograma, confirma, cobra en mostrador. | UI interna, scope `front_desk`. Ve agenda y datos de contacto; **no** ve la historia clínica. |
| **Administración / Facturación** | Emite comprobantes, gestiona caja y conciliaciones. | UI interna, scope `billing`. Ve lo económico; **no** edita historia clínica. |
| **Paciente** | Usuario final. Agenda turno, ve sus propios datos, pide copia de su documentación. | Portal web + WhatsApp. Autenticado por **OTP a su celular/DNI**, nunca por email+s密码 reutilizable. |
| **Profesional externo (laboratorio)** | Recibe el pedido de trabajo. | Portal externo **de alcance mínimo**: solo los datos del trabajo, no la historia clínica completa. |
| **Contador externo** | Asesor fiscal del tenant. Necesita ver comprobantes emitidos. | Acceso de solo lectura **a lo que el Owner le comparta explícitamente**. Ve PDFs/XML, no ficha clínica. |

### Regla de oro de roles

**Ninguna persona tiene un rol único fijo.** Un odontólogo puede ser Owner de otra clínica.
El modelo es `user` → `membership` → `role`, con el `tenant_id` en la membership, no en el user.
Esto es lo que permite que un mismo humano use el sistema en dos clínicas con permisos
distintos sin duplicar cuentas. → DD-07

## RBAC — Matriz de permisos

`C`=crear, `R`=leer, `U`=update, `D`=delete (bloqueado por política en casi todo), `—`=sin acceso.

### Recursos estructurales

| Recurso | Owner | Dir. clínica | Odontólogo | Higienista | Recepcionista | Administración | Paciente | Lab. | Contador |
|---------|-------|-------------|-----------|-----------|---------------|---------------|---------|------|---------|
| Configuración del tenant | C R U | R | R | R | R | R | — | — | — |
| Sillones | C R U D | C R U | R | R | R | — | — | — | — |
| Profesionales | C R U | C R U | R | R | R | — | — | — | — |
| Usuarios y roles | C R U D | R | — | — | — | R | — | — | — |
| **Historias clínicas** | R | R | **C R U** | **C R** | — | — | **R (propia)** | — | — |
| Odontograma / periodontograma | R | R | **C R U** | **C R** | — | — | R (propio) | — | — |
| Consentimientos | R | R | C R | C R | R | — | **R (propios)** | — | — |
| Turnos (agenda) | C R U D | C R U | R | R | **C R U D** | R | **C R (propios)** | R | — |
| Caja / movimientos | C R U | — | — | — | **C R U** | **C R U** | R (propios) | — | — |
| **Comprobantes fiscales** | **C R U** | R | — | — | C R | **C R U** | **R (propios)** | — | **R** |
| Liquidaciones a profesionales | C R U | R | **R (propias)** | R | — | C R U | — | — | R |
| Reportes financieros | **R** | — | — | — | R | **R** | — | — | R |
| Reportes de utilización | R | R | R | R | R | R | — | — | — |
| Migraciones | C R U | — | — | — | — | — | — | — | — |
| Solicitudes AAIP | C R | R | — | — | R | R | C (propia) | — | — |
| Configuración de WhatsApp | C R U | R | — | — | R | R | — | — | — |

### Restricciones horizontales (suman a la matriz)

1. **Recepcionista NO ve historia clínica ni odontograma.** Ni lectura. Es una frontera dura,
   no una preferencia de UI. Si el recepcionista necesita un dato clínico para explicar algo,
   el sistema no se lo da.
2. **Higienista no puede cerrar un odontograma como autor.** Puede agregar procedimientos,
   pero el estado `FINALIZADO` requiere un profesional con permiso `chart.finalize`.
3. **Administración no edita historia clínica.** Puede leerla solo si el Owner lo habilita
   por tenant (flag `billing.can_read_clinical`, default `false`).
4. **Ningún rol interno tiene `D` físico sobre historia clínica.** Ver RN-CMP-02.
5. **Paciente solo accede a sus propios registros**, resueltos por identidad verificada
   (OTP + DNI), no por sesión administrativa.
6. **Laboratorio nunca ve la historia clínica.** Solo el pedido con los campos que necesita.
7. **SuperAdmin no tiene lectura de historia clínica.** Su acceso es de soporte técnico:
   logs, integraciones, configuración. Si hay que leer un dato clínico para debugging, se
   hace por ticketJustificado y auditado.

## Detalle de roles base (seed)

| Rol | Scope | Descripción |
|-----|-------|-------------|
| `owner` | tenant | Todos los permisos del tenant. Único transferible (ver `ownership_transfer`). |
| `clinical_admin` | tenant | Dirección clínica. Gestiona sillones, profesionales, agenda. Sin acceso financiero de escritura. |
| `professional` | tenant | Odontólogo tratante. Escribe y cierra historia clínica y odontograma. |
| `assistant` | tenant | Higienista/asistente. Ejecuta procedimientos delegables. |
| `front_desk` | tenant | Recepcionista. Agenda y cobra en mostrador. Sin datos clínicos. |
| `billing` | tenant | Administración. Emite comprobantes, gestiona caja. |
| `patient` | patient_portal | Portal del paciente. Solo sus datos. |
| `external_lab` | external | Portal de laboratorio. Mínimo alcance. |
| `accountant` | tenant | Contador externo. Solo lectura de lo que el Owner comparte. |

## Rutas públicas

Accesibles **sin sesión de usuario interno**. Cada una tiene su propia forma de autenticación.

| Ruta | Método | Auth | Mitigaciones |
|------|--------|------|-------------|
| `/login` | GET | ninguna | rate limit por IP + CAPTCHA después de N intentos |
| `/auth/login` | POST | ninguna | rate limit + lockout progresivo + bloquear por hash de password (anti credential stuffing) |
| `/auth/refresh` | POST | refresh cookie httpOnly | rotación: cada refresh invalida el anterior; detección de reuse |
| `/forgot-password`, `/reset-password` | POST | token opaco | token de un solo uso, expira en 30 min |
| `/paciente/reservar` | GET | ninguna | ver flujo 3; rate limit estricto |
| `/paciente/otp/verify` | POST | OTP de 6 dígitos | máx 5 intentos, expira 10 min, rate limit por número |
| `/paciente/turno/:token` | GET | token opaco firmable | token de un solo uso por turno; sin info clínica |
| `/portal/consentimientos/:id` | GET | token firmable | solo el documento a firmar |
| `/webhooks/whatsapp` | POST | `X-Hub-Signature-256` | **obligatorio**; sin esto se rechaza. Rate limit por IP de Meta |
| `/webhooks/arca` | POST | token/mTLS | ver `11_facturacion_arca.md` |
| `/api/v1/public/professionals` | GET | ninguna | **solo** información de contacto y specialties. Nunca agenda ni turnos |
| `/health`, `/ready` | GET | ninguna | sin datos de negocio |
| `/legal/tos`, `/legal/privacy` | GET | ninguna | política de datos personales; el cliente tiene que poder leerla sin login |

### Superficie de API pública (no es "ruta pública", es API key de tenant)

| Ruta | Auth | Nota |
|------|------|------|
| `POST /api/v1/public/{apiKey}/appointments` | API key del tenant | Para integraciones de terceros. Scope limitado a crear turnos. Rate limit por key. |
| `GET /api/v1/public/{apiKey}/availability` | API key | Solo disponibilidad. No expone datos de pacientes. |

## Audit de accesos sensibles

Toda lectura o escritura de **historia clínica, odontograma o comprobante fiscal** genera un
`audit_log` append-only con: `tenant_id`, `user_id`, `patient_id`, `resource`, `resource_id`,
`action`, `ip`, `user_agent`, `timestamp`, `justification` (opcional pero requerida para
accesos de soporte). El `audit_log` **no** es modificable ni borrable por ningún rol,
incluido `owner`. Ver RN-CMP-03 y `12_historia_clinical_y_compliance.md`.
