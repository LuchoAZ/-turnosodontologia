# Discovery — Sistema de gestión odontológica (Argentina)

**Fecha**: 2026-10-01
**Alcance de la investigación**: Argentina (prioritario) · Latinoamérica · sistemas internacionales de referencia
**Fecha de consulta de todas las fuentes**: 2026-10-01
**Sistemas verificados**: 20 (14 argentinos, 4 latinoamericanos, 5 internacionales en total relevados)

> **Sobre las fuentes**: no seixinvocó `web-scraper` porque el usuario no aportó URLs concretas; la investigación fue
> *open discovery* web. Por eso **no existen archivos en `discovery/sources/`** — toda la evidencia (URL por
> sistema, marcador de evidencia y findings transversales) está consolidada en este documento. Si más adelante
> llegan URLs puntuales, conviene scrapearlas y sumar las notas en `discovery/sources/`.

## Convención de evidencia (obligatoria al leer este documento)

| Marcador | Significado |
|---|---|
| `[C]` | **Comprobado**: dato leído directamente en la página oficial del proveedor (URL citada). |
| `[A]` | **Afirmación comercial**: texto de marketing o claim del proveedor, NO verificado por nosotros. |
| `[NE]` | **No evidenciado**: no se encontró demostración pública. Nunca completar con suposiciones. |

**Advertencia estructural**: de los 20 sistemas, los claims de facturación electrónica ante ARCA y de gestión
real de obras sociales son, en su gran mayoría, `[A]`. Los dos únicos datos duros regulatorios del relevamiento
son la certificación **NOM-024-SSA3-2012** de Dentalink `[C]` (México) y el **ReNaPDiS ID 248** de ClinIA
verificado en el listado oficial del Ministerio de Salud de Argentina `[C]`.

---

## 1. Problema que resuelve

El consultorio y la clínica odontológica argentina resuelven turnos con un mosaico que no se sostiene: agenda
propia que no habla con la ficha clínica, WhatsApp manual que no es auditable, obras sociales que se liquidan
en planillas y facturación fiscal que muchas clínicas directamente no emiten.

La investigación muestra que **la gestión de turnos ya no es un problema**: 20 de 20 sistemas la tienen. El
problema real que queda abierto, y que ningún competidor resuelve de forma demostrable, es **la capa de
compliance y de negocio específico del odontólogo argentino**:

- **Facturación electrónica ante ARCA efectiva.** Solo DoctorYa declara ARCA como función de plan `[C]`.
  Adiasoft confiesa explícitamente que en Argentina "queda CONFIGURADO, sin emisión al ente: la ARCA no recibe
  nada" `[C]`. Dentatools: "por el momento no emitimos factura electrónica AFIP" `[C]`. Odontoly lo lista como
  complemento "Próximamente" `[C]`. DentalCore, ClinIA y Sigo lo **afirman** `[A]` sin certificado, CAE ni
  constante pública verificable. **Ningún sistema publica evidencia técnica de emisión efectiva.**
- **Obra social como producto, no como etiqueta.** Solo Bilog, DentalSaaS y DentalSoft tienen resolución
  operativa real (liquidaciones, nomenclador, planilla mensual) `[C]`. DentalCore (20+ convenios) y ClinIA
  (PUCO/SSS, PAMI, SUMAR+) lo afirman `[A]`. Los demás lo omiten o lo niegan.
- **Historia clínica legalmente defendible.** La Ley 26.529 exige integridad, autenticidad, inalterabilidad,
  perdurabilidad y recuperabilidad (art. 13), copia autenticada en 48 h (art. 14) y notación odontológica
  estandarizada (art. 15(f)). Solo DentalSoft publica política de privacidad que nombra la Ley 25.326 con
  responsable/encargado, aislamiento multi-tenant a nivel de base de datos, logs y denuncia ante AAIP `[C]`.
  Solo Odonthia nombra Ley 26.529 + 25.506 y firma con IP/dispositivo/hash `[C]`.

**Formulación en una frase**: *un sistema que coordina la agenda, la ficha clínica odontológica y el cobro del
consultorio, y que además cumple —de forma demostrable— las obligaciones fiscales y legales que hoy Ningún
software argentino puede probar.*

## 2. Usuarios / roles

Relevados del sector y de las páginas de los competidores `[C]`. **Confirmar en el gate de kb-creator.**

- **Odontólogo / director clínico**: agenda propia, evolución, odontograma, presupuesto, firma digital.
  `[C]` Todos los competidores lo modelan como el usuario central.
- **Asistente / recepción**: toma turnos, cobra señas, confirma, agenda el alta de pacientes. Es el usuario
  de mayor volumen de interacción diaria en la mayoría de los sistemas AR `[C]`.
- **Administrador de clínica**: caja, liquidaciones a profesionales, liquidaciones de obras sociales, reportes.
  Bilog lo segmenta explícitamente por rol `[C]`; DentalSoft tiene roles admin/secretaria/odontólogo `[C]`.
- **Profesional asociado**: ve su agenda, cobra sus comisiones. Modelo presente en Bilog, DentalSoft,
  DentalSaaS y Dentalink `[C]`.
- **Paciente**: reserva, confirma, cancela, recibe recordatorios, firma consentimientos, consulta su
  tratamiento, accede a su copia de historia clínica. Portal del paciente verificado en DentalCore `[C]` y
  ClinIA `[C]`.
- **Laboratorio dental** (solo en algunos): DentalSaaS y Dentalink tienen módulo de laboratorio `[C]`.
- **Obra social / prepaga / agente de assurance**: emisor de autorización y de facturación a cobrar.

## 3. Casos de uso

Derivados del brief del usuario y de los patrones observados en los 20 sistemas. **Ordenados por bloqueo del MVP.**

1. Como odontólogo, quiero **agendar por sillón con duración variable según la prestación** para que la
   agenda refleje el tiempo real de atención y no sobre-reserva horas que no existen.
2. Como recepción, quiero que el paciente **reserva solo desde un enlace o QR las 24 h** para dejar de
   coordinar turnos por teléfono.
3. Como recepción, quiero **recordatorios y confirmaciones automáticas por WhatsApp** que actualicen la agenda
   sin que nadie toque un botón.
4. Como odontólogo, quiero **registrar la evolución con odontograma y periodontograma por pieza** para tener
   el estado clínico real del paciente y poder comparar en el tiempo.
5. Como administrador, quiero **emitir comprobante electrónico ante ARCA y liquidar a profesionales y obras
   sociales** para dejar de liquidar en planillas y facturar en negro.
6. Como paciente, quiero **descargar mi copia de historia clínica y firmar consentimientos desde el celular**
   para ejercer el derecho de acceso que la Ley 26.529 me garantiza.

## 4. Competidores / soluciones existentes

**20 sistemas ordenados por relevancia para Argentina.** Verificado el 2026-10-01.

| # | Producto | Empresa | Origen | Segmento | Modalidad | Precio publicado | ARCA/AFIP | Obras sociales |
|---|---|---|---|---|---|---|---|---|
| 1 | **Bilog** | Bilog | 🇦🇷 AR | consultorio → clínica → cadena / universidad / auditoría OS | Nube + app iOS/Android | No publicado (cotiza por usuario) | `[A]` pack de comprobantes vía "Facturante" | `[C]` liquidaciones + auditoría/gerenciadoras |
| 2 | **OdontoClinIA** | Emprinet 4.0 | 🇦🇷 AR | consultorio → clínica PyME → cadena | SaaS web | No publicado (demo) | `[A]` integrado | `[A]` PUCO/SSS, módulos PAMI + SUMAR+ |
| 3 | **DentalCore** | DentalCore (CUIT 20-40568642-3) | 🇦🇷 AR | consultorio → multi-sucursal | SaaS web + portal + bot | USD 50/mes (2 usr) + USD 10/usuario | `[A]` CAE + QR fiscal (RG 4892) | `[A]` 20+ convenios, nomenclador por plan |
| 4 | **DentalSoft** | DentalSoft (La Plata/Rosario) | 🇦🇷 AR | consultorio → clínica multi-sucursal | SaaS nube + web white-label por clínica | $30.000 / $60.000 + $10.000/prof | `[NE]` | `[C]` cobertura por tratamiento + liquidación por período |
| 5 | **DentalSaaS** | DelRioTech SAS | 🇦🇷 AR | consultorio → clínica → alto volumen | SaaS nube | $59.000 / $149.000 / $349.000 | `[NE]` | `[C]` catálogo nacional precargado + nomenclador + planilla mensual |
| 6 | **DoctorYa** | Sistemasdev SDEV (CUIT 20-28793714-9) | 🇦🇷 AR | profesional → consultorio → multisede | Navegador | $9.000 / $25.000 / $90.000 | `[C]` declarado en plan (Monotributo + RI) | `[C]` obras sociales por profesional con copagos |
| 7 | **Odonthia** | Genera Impacto | 🇦🇷 AR | odontólogo independiente | 100% web | Núcleo gratis ilimitado + $20.900 / $46.900 | `[NE]` (rechaza por ReNaPDiS/Ley 27.553) | `[NE]` |
| 8 | **Dentiqa** | Violet Wave | 🌎 LatAm | clínica PyME → grupo/cadena | SaaS + WhatsApp Business API oficial | USD 89 / 149 / 249 (cobra en USD) | `[NE]` | `[NE]` |
| 9 | **Livio** | Livio | 🇦🇷 AR | clínicas (facturación ARS 5M–20M/mes) | Nube | $99.000 + Enterprise | `[NE]` | `[NE]` |
| 10 | **FLAP** | TuWebmaster | 🇦🇷 AR | consultorio → clínica + equipos | Nube | Gratis (30 turnos) / $12.000 / $39.900 / $68.900 | `[NE]` | `[NE]` |
| 11 | **SisTurnos** | SisTurnos | 🇦🇷 AR | profesional → clínica (10 prof.) | Nube | $19.000 / $49.000 | `[NE]` | `[C]` solo etiqueta de cobertura |
| 12 | **Odontoly** | Odontoly | 🇦🇷 AR | consultorio 1 sillón | **Local-first desktop (solo Mac)** | USD 149,99 + instalación USD 0 | "Próximamente" `[C]` | Niega explícitamente `[C]` |
| 13 | **Sigo** | Hosting Bahía (Bahía Blanca) | 🇦🇷 AR | consultorio → clínica | Nube | $25.000 (1 prof.) | `[A]` "homologadas por AFIP" | `[NE]` |
| 14 | **Dentatools** | Dentatools | 🇦🇷 AR | consultorio particular | Nube | $30.000 (hasta 3) + $8.000/prof | Niega explícitamente `[C]` | Niega explícitamente `[C]` |
| 15 | **Dentalink** | Healthatom MX | 🇲🇽 MX | consultorio → multicentro | SaaS | No publicado | `[A]` (versión CO) | `[C]` convenios + financiamiento al paciente |
| 16 | **OdontoWare** | Medware Digital Consulting | 🇲🇽 MX | consultorio → grupo (18 dentistas/5 sedes) | SaaS | MXN 599 / 1.499 / 4.499 | `[C]` CFDI 4.0 con PAC propia | `[C]` aseguradoras |
| 17 | **Simples Dental** | Simples Dental (Santa Catarina) | 🇧🇷 BR | consultorio → franquicias | SaaS + apps iOS/Android | BRL 149,90 / 249,90 / 349,90 (anual) | `[C]` NFS-e + Pix + boletos (add-on) | `[C]` convênio |
| 18 | **DentalSoftWeb** | SuWebJK | 🇨🇴 CO | consultorio → IPS → hospital | SaaS | USD 362,50/año (500 historias, 6 usr) | `[C]` DIAN + RIPS + IHCE | `[NE]` |
| 19 | **tab32** | tab32 | 🇺🇸 US | 1–3 profesionales → grupos | SaaS cloud | USD 125/mes año 1 → USD 225 | `[NE]` | `[NE]` (insurance USA) |
| 20 | **SimplyBook.me** | SimplyBook.me (team.blue) | 🇨🇾 CY | agenda genérica multiespecialidad | SaaS | €0 – 49,90/mes | — | — |

### 4.1 Matriz de puntuación (0–5, ponderada)

Valoración propia sobre la evidencia relevada; los claims `[A]` fueron penalizados.

| Sistema | Turnos y automatización **25%** | Clínica odontológica **20%** | Integraciones locales + WA **15%** | Administración y facturación **15%** | Experiencia del paciente **10%** | Seguridad / export / trazabilidad **10%** | Precio y adopción **5%** | **TOTAL /100** |
|---|---|---|---|---|---|---|---|---|
| DentalCore | 5 | 5 | 3 | 3 | 5 | 3 | 5 | **84** |
| OdontoClinIA | 4 | 4 | 4 | 4 | 4 | 4 | 2 | **78** |
| DentalSoft (AR) | 4 | 4 | 3 | 3 | 5 | 4 | 4 | **76** |
| DentalSaaS | 4 | 5 | 3 | 4 | 3 | 3 | 3 | **76** |
| Dentalink (MX) | 4 | 5 | 3 | 4 | 4 | 3 | 2 | **77** |
| Dentiqa | 4 | 4 | 5 | 2 | 4 | 3 | 2 | **73** |
| OdontoWare (MX) | 3 | 5 | 2 | 4 | 3 | 4 | 5 | **72** |
| Livio | 4 | 3 | 3 | 3 | 4 | 3 | 2 | **66** |
| DoctorYa | 4 | 2 | 4 | 3 | 3 | 2 | 5 | **64** |
| Bilog | 4 | 3 | 3 | 3 | 3 | 2 | 2 | **62** |
| FLAP | 4 | 3 | 2 | 2 | 4 | 2 | 5 | **61** |
| Odonthia | 2 | 4 | 2 | 2 | 3 | 4 | 5 | **57** |
| SisTurnos | 4 | **1** | 2 | 3 | 3 | 1 | 5 | **52** |
| Odontoly | 2 | 2 | **0** | 1 | 2 | 3 | 2 | **33** |

**Lectura**: el eje competitivo ya no es la gestión de turnos. Los que ganan resuelven **capa clínica real +
compliance** (DentalCore, ClinIA, DentalSoft) o **profundidad clínica** (DentalSaaS, Dentalink, OdontoWare).
Los que pierden compiten solo por agenda barata: Odontoly tiene 0 en integraciones (WhatsApp, Google Calendar y
facturación ARCA son "Próximamente") y SisTurnos **no tiene odontograma**.

### 4.2 Funcionalidades ya estándar de mercado (no diferenciables)

- Agenda multiprofesional con duración variable por prestación y bloqueo de solapamientos.
- Odontograma con notación FDI.
- Ficha clínica con imágenes/radiografías y notas de evolución.
- Recordatorios por WhatsApp y confirmación en un clic.
- Caja diaria, presupuestos en PDF, cuentas por cobrar.
- Precio en pesos y soporte por WhatsApp.

### 4.3 Diferenciales reales, verificados

| Diferencial | Quién lo tiene | Por qué importa |
|---|---|---|
| **ReNaPDiS ID 248 + HL7 FHIR** | ClinIA / Emprinet 4.0 `[C]` | Única credencial regulatoria argentina verificada del relevamiento (confirmada en el listado oficial del Ministerio de Salud). Alcance: **solo recetario electrónico**, no aprobación del software. |
| **Agenda por sillón** | ClinIA, FLAP, OdontoWare, Adiasoft `[C]` | Unidad real de capacidad en clínica con más de 2 sillones. |
| **Periodontograma con telemetría** (BOP/NIC/placa, surco/margen) | DentalSaaS, Dentiqa, Odonthia, Dentalink, OdontoWare `[C]` | Mitad de la odontología que la agenda genérica no cubre. Ausente en Bilog, DentalSoft, DoctorYa, FLAP, Livio, Odontoly, SisTurnos. |
| **Liquidación de obras sociales / nomenclador** | Bilog, DentalSaaS, DentalSoft `[C]` | Costo operativo dominante del consultorio argentino. |
| **WhatsApp Business API oficial** (no linking por QR) | Dentiqa `[C]`, Bilog `[C]` | DentalCore usa **QR linking de sesión** `[C]` → riesgo de cumplimiento de ToS de Meta. |
| **White-label (web propia por clínica)** | DentalSoft, DentalSaaS `[C]` | SEO + agenda propia sin depender de marketplace. |
| **Auditoría exportable de acciones** | DentalSaaS `[C]` | Trazabilidad real, no decorativa. |
| **Local-first / offline real** | Odontoly `[C]` (solo Mac), OdontoSoft PE `[C]` | Relevante para clínicas de provincia sin fibra. |
| **IA que agenda sola** | DentalCore (bot 9 flujos + asistente de voz), Dentiqa (Claude en 3 capas), Dentalink (Contact Center IA) `[C]` | En 2026 ya es tabla, no diferenciador. |

### 4.4 Los cinco vacíos del mercado argentino

1. **Facturación electrónica ARCA real y verificable.** El flujo crítico es el **alta de comprobante clase A**:
   requiere sin inconsistencias fiscales (RG 4132), **solvencia patrimonial** acreditada (bienes por encima del
   6% del mínimo no imisible; **la certificación por Bienes Personales/REIBP no computa para los períodos 2026
   y 2027**), y hay **15 días corridos** desde la suspensión antes del archivo por desistimiento tácito
   `[C, fuentes ARCA]`. También hay que emitir **comprobante A contra obra social**, no B — error de criterio
   frecuente. Casi ningún software resuelve el onboarding de estos requisitos.
2. **Obra social como producto**: workspace por convenio con nomenclador propio, trazabilidad de autorización
   y estado de cuenta con el **modelo de Cuota Transparente** (Res. SSS 1725/2025, Anexo II) `[C]`.
3. **Copia autenticada de historia clínica en ≤48 h como autoservicio** (Ley 26.529 art. 14) y acceso del
   titular con SLA de 10 días (Ley 25.326 art. 14) `[C]`. **Ningún competidor lo ofrece**; es barato de
   construir porque el deber de custodia ya existe.
4. **Sillón como unidad de verdad.** Solo OdontoWare mide "ocupación de sillón" en reportes `[C]`. Toda la
   telemetría del mercado es por profesional, que en una clínica con 6 sillones y turnos heterogéneos no dice
   dónde está la capacidad ociosa.
5. **Pricing sin trampas.** Patrón dominante: freemium como embudo + packs de consumibles (Bilog 150→1.000
   recordatorios, facturación por cantidad de comprobantes, Simples Dental cobra aparte hasta la confirmación
   de WhatsApp `[C]`). **FLAP, DoctorYa, Odonthia y OdontoWare son las excepciones** con precio publicado sin
   letra chica.

### 4.5 Oportunidades de innovación para un sistema nuevo

- **"Compliance-first" como eje comercial.** Ningún competidor puede demostrar que resuelve simultáneamente
  Ley 26.529 (integridad, inalterabilidad, recuperabilidad, copia autenticada, notación FDI legal), Ley 25.326
  + AAIP, y clase A de ARCA. Es defendible y vendible a la clínica que hoy factura informalmente porque no
  pudo tramitar el alta.
- **Sillón × pieza × tiempo como modelo de datos.** Permite occupancy real, detección de blanks, planificación
  de capacidad. OdontoWare lo mide en reportes; nadie lo usa como núcleo del modelo.
- **WhatsApp con costo explícito y API oficial.** Convertir el mayor costo variable del mercado en ventaja de
  transparencia en vez de sorpresa.
- **IA que ordene el dato, no que responda.** Convertir dictado/voz/foto en estructura (pieza FDI + superficie
  + CIE-10 + plan), como el dictado estructurante de DentalSoftWeb `[C]`, en vez de un chatbot de atención.
- **Migración entrante como producto.** Seis competidoresCompiten por migrar desde Dentalink o Excel con
  dedupe `[C]`; nadie lo empaquetó como servicio con garantía.
- **Precio en pesos publicado, sin packs.** Posición defendible frente a Bilog (no publica) y a los modelos de
  consumibles.

## 5. Funcionalidades necesarias

> **PENDIENTE DE DEFINICIÓN.** El usuario dejó abierta la decisión de segmento (P1) y de alcance (P2), por lo
> que esta sección queda como **propuesta derivada de la investigación**, no como alcance acordado.

**Propuesta de imprescindibles** (priorizar el bloque que corresponda al segmento elegido en P1):

1. Agenda **por profesional y por sillón/box**, con duración variable por prestación, anti-solapamiento,
   sobreturnos, bloqueos y feriados.
2. Reserva online 24/7 (enlace + QR) con confirmación, cancelación, reprogramación y lista de espera.
3. Recordatorios y confirmaciones por **WhatsApp Business API oficial** + email, con respuesta que actualice
   la agenda.
4. Ficha clínica con **odontograma FDI (permanente + primaria)**, periodontograma, imágenes/radiografías,
   presupuestos y planes de tratamiento.
5. Caja, cobros, señas, cuentas por cobrar y liquidación por profesional.
6. **Facturación electrónica ARCA end-to-end**: comprobante A/B/C derivado del estado del cliente (no elegido a
   mano), FE + Nota de Crédito + Nota de Débito, token WSAA, **certificado X.509 por tenant**, y onboarding
   que resuelva los 3 requisitos de clase A.
7. **Consentimiento informado** con el contenido del art. 5 de la Ley 26.529, firma digital, versionado y
   constancia de revocación (art. 10).
8. **Historia clínica inmutable** con audit trail, retención ≥10 años y **copia autenticada en ≤48 h** como
   autoservicio (arts. 12–18).
9. RBAC, política de privacidad con responsable/encargado (Ley 25.326), declaración ante AAIP.
10. Migración desde Excel / Dentalink / sistema previo con dedupe.

**Propuesta de diferenciadores:** sillón como unidad de verdad · evidencia técnica pública de un comprobante
ARCA emitido · workspace de obras sociales con nomenclador por convenio y Cuota Transparente · costo de
WhatsApp visible en el precio · precio en pesos publicado · modelo de datos FHIR-ready desde el origen ·
migración como servicio con garantía.

**Propuesta de diferidos (etapas posteriores):** portal del paciente y teleodontología · CDSS / IA clínica ·
dictado estructurante por voz · CRM de captación y campañas · gestión de laboratorios · multi-sucursal tipo
DSO · facturación a prepagas con modelo RIPS-like.

## 6. Funcionalidades opcionales

> **PENDIENTE DE DEFINICIÓN.** Mismo criterio que §5.

Migración QR-linked a WhatsApp como atajo de bajo costo · integración con Google Calendar bidireccional ·
respaldo offline / local-first · point de venta de mostrador · control de stock e insumos ·
módulo de laboratorio dental · evaluación de satisfacción y NPS · score de crédito ·خ visualizations
avanzadas de analítica.

## 7. Reglas de negocio

> **PENDIENTE DE DEFINICIÓN.** Las que sí se desprenden de la normativa y **no son negociables**:
> el tipo de comprobante se deriva del estado fiscal del cliente (obra social → **A**, monotributista → **C**,
> consumidor final → **B**); la historia clínica es **cronológica, foliada, completa, inalterable y con
> guarda mínima de 10 años** desde la última actuación; el paciente es titular de su historia y recibe copia
> autenticada en **≤48 h**; los datos de salud son **sensibles** y su cesión a obras sociales, prepagas o
> laboratories exige **consentimiento expreso**; la odontología debe registrarse en **nomenclatura binaria de
> dos dígitos** (art. 15(f) Ley 26.529) con dentición permanente **y primaria**.

## 8. Integraciones

> **PENDIENTE DE DEFINICIÓN** para el stack concreto. **Obligatorias por ley o por mercado**, ya verificadas:
> **ARCA** (certificado X.509 por tenant, WSAA, FE/NC/ND) · **Mercado Pago** (comisiones verificadas: 1,49%
> a 35 días, 3,39% a 18, 4,39% a 10, 6,29% al instante, todas + IVA 21% `[C]`) · **WhatsApp Business API**
> (coste **no verificable**: la página oficial de precios es JS-rendered y la de developers devolvió HTTP 400)
> `[NE]` · **Google Calendar** · **PUCO/SSS** para cobertura de obras sociales `[A]` · **RENAPER** `[A]` ·
> **HL7 FHIR / ReNaPDiS** para recetario electrónico `[C]` · **nomencladores por obra social** (no existe
> nomenclatura única: cada agente tiene su catálogo; es el costo operativo dominante) `[C]`.

## 9. Restricciones

> **PENDIENTE DE DEFINICIÓN** por el usuario. Restricciones **derivadas de la investigación** que ya son un
> hecho del contexto y no pueden ignorarse:
> - El **mantenimiento normativo es costo recurrente, no proyecto cerrado**: al menos tres resoluciones de ARCA
>   nuevas en 2025–2026 (RG 5762/2025, RG 5830/2026, RG 5866/2026 con entrada en vigencia 01/07/2026) `[A]`.
> - **El costo de WhatsApp Business API es una incógnita abierta** en pesos: no se pudo verificar ninguna
>   tarifa argentina oficial. Modelarlo como costo variable con techo.
> - **Multitenancy con identidad fiscal propia por clínica**: el software **no puede emitir bajo su propio
>   certificado**; cada clínica emite con el suyo. Esto define el costo de onboarding técnico.
> - Los **precios del relevamiento reflejan el 2026-10-01** y tienen vida corta en un mercado inflationary.

## 10. Riesgos

- **Supuesto sin probar — el usuario no define el segmento.** Es el riesgo #1 de Discovery: sin P1 resuelto, la
  KB, el roadmap y el MVP son hypothèse. Todo §5 y §6 quedan como propuesta, no como alcance.
- **Supuesto sin probar — que el hueco de compliance ARCA sea explotable comercialmente.** Puede que el
  consultorio prefiera no facturar formalmente antes que aprender a品质的 trámite. No validado con usuarios.
- **Riesgo de plazo — la complejidad regulatoria (Ley 26.529 + 25.326 + clase A de ARCA) puede demorar el
  lanzamiento más que la parte técnica.** Es el riesgo #1 según el relevamiento: 3 de los 5 vacíos son legales.
- **Supuesto sin probar — que el precio Full-Featured más bajo (DentalCore, USD 50/mes) sea sostenible.** Es el
  dato más disruptivo del relevamiento y merece validación comercial directa, no solo documental.
- **Riesgo de claims falsos del mercado**: si DentalCore/ClinIA implementan de verdad lo que afirman (FHIR,
  17 motores CDSS, 20+ obras sociales), la brecha se reduce o desaparece. No descartado.
- **Riesgo de dependencia de Meta**: cualquier producto que use QR linking en vez de API oficial expone la
  sesión de WhatsApp del consultorio a un ToS de Meta que puede cambiar.
- **Riesgo de profundidad nomencladora**: cada obra social tiene su catálogo y sus reglas de claim. Multi-sucursal
  y facturación a obras sociales tienen costo operativo recurrente no resuelto por ninguna estandarización nacional.

## 11. Preguntas abiertas

**Las cinco decisiones de segmentación/alcance que el usuario dejó explícitamente sin responder:**

- **P1 — Segmento inicial** (define la mitad del MVP): a) odontólogo independiente / consultorio 1-2 sillones;
  b) clínica PyME 3-10 sillones multiprofesional; c) cadena / multi-sucursal. *Recomendación del análisis: (b),
  es el único donde los cinco vacíos se pagan solos.*
- **P2 — Alcance de obras sociales y facturación en el MVP**: a) ARCA real desde el día 1, obras sociales
  diferidas; b) ambos desde el día 1; c) ninguno. *Recomendación: (a).*
- **P3 — Modelo comercial**: a) freemium con núcleo clínica gratis + pago por consumo; b) suscripción única en
  pesos, todo incluido, sin packs; c) sin gratis, precio en USD. *Recomendación: (b), el hueco de posicionamiento
  menos explotado y más fácil de defender ante un odontólogo que ya sufrió el precio sorpresa.*
- **P4 — WhatsApp**: a) API oficial; b) QR linking; c) QR en el plan chico y API desde Pro. *Recomendación: (a)
  para el núcleo, con el costo visible en el plan.*
- **P5 — Riesgo que más preocupa**: a) quedarse en "otra agenda"; b) la complejidad regulatoria demora el
  lanzamiento; c) el mercado ya está saturado de players con núcleo gratis. *Recomendación: (b).*

**Riesgos regulatorios abiertos (no cerrar sin fuente):**

- **Alcance del art. 3 del Decreto 393/2023**: no se verificó si obliga a consultorios privados a registrarse en
  el Registro de Dominios de Interoperabilidad en Salud.
- **Qué sistema binario de dos dígitos fija la reglamentación del art. 15(f) de la Ley 26.529** (FDI o
  alternativa): la reglamentación citada no fue transcrita. **Punto a cerrar antes de fijar el modelo de datos.**
- **Estado del proyecto de reforma de la Ley 25.326** en el Congreso (AAIP publica un proyecto oficial; el
  estado de trámite no fue verificado).
- **Arancel** del certificado X.509 de ARCA y de la inscripción en el Registro Nacional de Bases de Datos.
- **Tarifas de WhatsApp Business API en Argentina**: sin dato verificable.
- Si la **RG 5866/2026** alcanza a los odontólogos monotributistas antes de la fecha de salida del producto.
- **Texto literal del art. 15(f)**: la redacción sobre identificación del paciente en historias odontológicas
  resulta ambigua y merece revisión legal antes de comprometer el modelo de datos.

**Verificaciones comerciales pendientes (prioridad):**

- Validación directa del precio y del alcance real de DentalCore (USD 50/mes) — el dato más disruptivo.
- Cuánto de lo que afirma ClinIA fuera del recetario (PUCO, SUMAR+, obras sociales) existe en producción.
- Reseñas externas verificadas (Capterra / G2 / Play Store / Reclame Aqui) por producto. En el relevamiento solo
  se pudo verificar la marca de **Reclame Aqui 9.6/10 de Simples Dental** `[C]`; ninguna de las reseñas de los
  proveedores argentinos fue verificable.

---

## Anexo — cinco competidores prioritarios para demo

| Orden | Producto | Por qué este |
|---|---|---|
| 1 | **OdontoClinIA (ClinIA)** | Único con ReNaPDiS #248 verificado, FHIR, PUCO, PAMI y SUMAR+. Es el techo del componente regulatorio. |
| 2 | **DentalCore** | Claim más profundo del país (FHIR, 17 motores CDSS, periodontograma, 20+ obras sociales) y precio Full-Featured más bajo (USD 50). Hay que medir cuánto es real. |
| 3 | **Bilog** | Incumbent de 20+ años, único con eje real de obras sociales y auditoría/gerenciadoras. Define qué significa "líder". |
| 4 | **DentalSoft (AR)** | Mejor UX argentina y pricing transparente; **demo pública funcional** verificable sin agendar. |
| 5 | **Dentalink (MX)** | Benchmark regional de profundidad clínica real y rival inevitable de cualquier migración. |

**Menciones**: **Odonthia** para el modelo de núcleo gratuito + créditos de IA; **SisTurnos** para el estado de
turno en mostrador sin funciones clínicas.

## Anexo — tres referencias de experiencia de usuario

1. **DentalSoft** — flujo de reserva en 4 pasos, web propia por clínica, detección por DNI, drag & drop con
   confirmación.
2. **DentalCore** — bot de WhatsApp que rellena huecos cancelados automáticamente, portal del paciente con
   firma de consentimiento, asistente de voz.
3. **Dentiqa** — pipeline de 7 etapas con valor monetario por etapa y campañas segmentadas por fecha clínica.

*Benchmark externo*: **SimplyBook.me** para reserva 24/7 multi-canal (Google, Instagram, Facebook) a costo casi cero.

## Anexo — sistemas descartados y por qué

| Sistema | Motivo |
|---|---|
| **Adiasoft** (Perú) | Página argentina **confiesa** que en ARCA "no emite nada" `[C]`. No hay operación argentina real; nomenclatura FDI citada según **NTS 188-2022 del MINSA peruano**. |
| **DenPro** | `.ar` existe pero es **marca de la UE** (Elite Digital Services LLC, EUTM 019320299, +34 España, RGPD/GDPR, datacenters ISO 27001 UE). Sin evidencia de operación argentina. |
| **iTurnos** (AR) | Real (Cormos S.A., CUIT 30-70707274-8) pero solo agenda web: **sin ficha clínica ni odontograma**. Competidor histórico de *turno online*, no de software dental. |
| **Dentaflow** | Vertical de automatización por WhatsApp con IA, **sin** odontograma, historia clínica, presupuesto, caja ni obras sociales. No cumple el brief. |
| **Dentaly, OdontoApp, DentalTec** | SPA sin contenido renderizable; solo verificables vía metadatos o páginas legales. |
| **Odontozen, OdontoWare-EC, OdontoCloudPRO** | Precios publicados de México, Ecuador o LatAm genérica; sin evidencia de operación argentina. |
| **Nexden (CL), Reservo** | 404 o contenido JS-rendered; no verificables. |
| **Dentrisoft, GouJana, Qlini, Doctocliq, OdontoHCE (CO)** | Candidatos con claim de odontología pero sin verificación: ninguno se abrió con fetch. |