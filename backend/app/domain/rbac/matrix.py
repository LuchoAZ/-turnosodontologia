"""Núcleo RBAC puro: catálogo de permisos, matriz rol→permiso y resolución.

Este módulo es la **segunda transcripción** de la tabla de
``knowledge-base/03_actores_y_roles.md`` líneas 33-48. La primera está en
``backend/tests/unit/rbac/test_matrix.py``: el test no importa la matriz para
construir la esperada, así que una edición de este archivo que no venga de la KB
falla el test de fidelidad (D1).

Reglas de derivación (mecánicas, aplicadas en este orden):

1. ``C`` → ``create``, ``R`` → ``read``, ``U`` → ``update``, ``D`` → ``delete``,
   ``—`` → sin permiso.
2. ``*C`` / ``*R`` son los accesos "propios" de la KB (``R (propia)``,
   ``C (propia)``…): se traducen a ``create_own`` / ``read_own``, **nunca** a
   ``create`` / ``read`` pleno.
3. ``T`` es la transferencia de ownership (``ownership.transfer``) y ``F`` el
   cierre de odontograma (``chart.finalize``): son operaciones que la KB marca
   aparte y que no caben en las cuatro letras.
4. Las 7 restricciones horizontales se aplican como excepciones explícitas en
   ``_apply_horizontal_exceptions``, en un solo bloque.

Ningún endpoint ni componente de UI compara roles: compara permisos. Un rol o un
permiso desconocido resuelve a conjunto vacío (fail-closed); no existe el rol
``SuperAdmin`` en el enum, así que no se modela (restricción horizontal 7).
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Final

from app.models.tenancy import Role


class Permission(StrEnum):
    """Los 57 permisos atómicos, nombrados ``recurso.accion``."""

    # tenant_settings — Configuración del tenant
    tenant_settings_create = "tenant_settings.create"
    tenant_settings_read = "tenant_settings.read"
    tenant_settings_update = "tenant_settings.update"
    # chair — Sillones
    chair_create = "chair.create"
    chair_read = "chair.read"
    chair_update = "chair.update"
    chair_delete = "chair.delete"
    # professional — Profesionales
    professional_create = "professional.create"
    professional_read = "professional.read"
    professional_update = "professional.update"
    # team — Usuarios y roles (CRUD de memberships)
    team_create = "team.create"
    team_read = "team.read"
    team_update = "team.update"
    team_delete = "team.delete"
    # ownership — Usuarios y roles (desdoblado: RN-TEN-04)
    ownership_transfer = "ownership.transfer"
    # clinical_record — Historias clínicas
    clinical_record_create = "clinical_record.create"
    clinical_record_read = "clinical_record.read"
    clinical_record_update = "clinical_record.update"
    clinical_record_read_own = "clinical_record.read_own"
    # chart — Odontograma / periodontograma
    chart_create = "chart.create"
    chart_read = "chart.read"
    chart_update = "chart.update"
    chart_finalize = "chart.finalize"
    chart_read_own = "chart.read_own"
    # consent — Consentimientos
    consent_create = "consent.create"
    consent_read = "consent.read"
    consent_read_own = "consent.read_own"
    # appointment — Turnos (agenda)
    appointment_create = "appointment.create"
    appointment_read = "appointment.read"
    appointment_update = "appointment.update"
    appointment_delete = "appointment.delete"
    appointment_create_own = "appointment.create_own"
    appointment_read_own = "appointment.read_own"
    # cash — Caja / movimientos
    cash_create = "cash.create"
    cash_read = "cash.read"
    cash_update = "cash.update"
    cash_read_own = "cash.read_own"
    # invoice — Comprobantes fiscales
    invoice_create = "invoice.create"
    invoice_read = "invoice.read"
    invoice_update = "invoice.update"
    invoice_read_own = "invoice.read_own"
    # settlement — Liquidaciones a profesionales
    settlement_create = "settlement.create"
    settlement_read = "settlement.read"
    settlement_update = "settlement.update"
    settlement_read_own = "settlement.read_own"
    # report_financial — Reportes financieros
    report_financial_read = "report_financial.read"
    # report_usage — Reportes de utilización
    report_usage_read = "report_usage.read"
    # migration — Migraciones
    migration_create = "migration.create"
    migration_read = "migration.read"
    migration_update = "migration.update"
    # aaip_request — Solicitudes AAIP
    aaip_request_create = "aaip_request.create"
    aaip_request_read = "aaip_request.read"
    aaip_request_create_own = "aaip_request.create_own"
    # whatsapp_config — Configuración de WhatsApp
    whatsapp_config_create = "whatsapp_config.create"
    whatsapp_config_read = "whatsapp_config.read"
    whatsapp_config_update = "whatsapp_config.update"
    # membership_event — Auditoría de RBAC (sin titulares)
    membership_event_read = "membership_event.read"


_NO_ACCESS: Final[str] = "—"
_LETTER_ACTIONS: Final[dict[str, str]] = {
    "C": "create",
    "R": "read",
    "U": "update",
    "D": "delete",
}
_OWN_ACTIONS: Final[dict[str, str]] = {"C": "create_own", "R": "read_own"}

# Transcripción de la KB (03 § RBAC, líneas 33-48), en el orden de la tabla.
# Columnas: owner, clinical_admin, professional, assistant, front_desk, billing,
# patient, external_lab, accountant. La fila "Usuarios y roles" aparece
# desdoblada en ``team`` (CRUD de memberships) y ``ownership`` (transferencia),
# porque RN-TEN-04 exige que sean operaciones distintas (D7).
_KB_MATRIX: Final[tuple[tuple[str, ...], ...]] = (
    ("tenant_settings", "CRU", "R", "R", "R", "R", "R", _NO_ACCESS, _NO_ACCESS, _NO_ACCESS),
    ("chair", "CRUD", "CRU", "R", "R", "R", _NO_ACCESS, _NO_ACCESS, _NO_ACCESS, _NO_ACCESS),
    (
        "professional",
        "CRU",
        "CRU",
        "R",
        "R",
        "R",
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
    ),
    (
        "team",
        "CRUD",
        "R",
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        "R",
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
    ),
    (
        "ownership",
        "T",
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
    ),
    (
        "clinical_record",
        "R",
        "R",
        "CRU",
        "CR",
        _NO_ACCESS,
        _NO_ACCESS,
        "*R",
        _NO_ACCESS,
        _NO_ACCESS,
    ),
    (
        "chart",
        "R",
        "R",
        "CRUF",
        "CR",
        _NO_ACCESS,
        _NO_ACCESS,
        "*R",
        _NO_ACCESS,
        _NO_ACCESS,
    ),
    (
        "consent",
        "R",
        "R",
        "CR",
        "CR",
        "R",
        _NO_ACCESS,
        "*R",
        _NO_ACCESS,
        _NO_ACCESS,
    ),
    (
        "appointment",
        "CRUD",
        "CRU",
        "R",
        "R",
        "CRUD",
        "R",
        "*C*R",
        "R",
        _NO_ACCESS,
    ),
    ("cash", "CRU", _NO_ACCESS, _NO_ACCESS, _NO_ACCESS, "CRU", "CRU", "*R", _NO_ACCESS, _NO_ACCESS),
    ("invoice", "CRU", "R", _NO_ACCESS, _NO_ACCESS, "CR", "CRU", "*R", _NO_ACCESS, "R"),
    ("settlement", "CRU", "R", "*R", "R", _NO_ACCESS, "CRU", _NO_ACCESS, _NO_ACCESS, "R"),
    (
        "report_financial",
        "R",
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        "R",
        "R",
        _NO_ACCESS,
        _NO_ACCESS,
        "R",
    ),
    ("report_usage", "R", "R", "R", "R", "R", "R", _NO_ACCESS, _NO_ACCESS, _NO_ACCESS),
    (
        "migration",
        "CRU",
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
    ),
    ("aaip_request", "CR", "R", _NO_ACCESS, _NO_ACCESS, "R", "R", "*C", _NO_ACCESS, _NO_ACCESS),
    (
        "whatsapp_config",
        "CRU",
        "R",
        _NO_ACCESS,
        _NO_ACCESS,
        "R",
        "R",
        _NO_ACCESS,
        _NO_ACCESS,
        _NO_ACCESS,
    ),
)

# Orden de las 9 columnas de la KB. ``ROLE_PERMISSIONS`` se publica con las 9
# entradas aunque un rol quede vacío: el enum ``Role`` es el contrato.
_ROLE_ORDER: Final[tuple[Role, ...]] = (
    Role.owner,
    Role.clinical_admin,
    Role.professional,
    Role.assistant,
    Role.front_desk,
    Role.billing,
    Role.patient,
    Role.external_lab,
    Role.accountant,
)

# Recurso de auditoría de RBAC: se declara para que la matriz sea explícita
# sobre la auditoría y **ningún rol** lo tenga (coherente con RN-CMP-03).
_AUDIT_RESOURCE: Final[str] = "membership_event"


def _expand(resource: str, cell: str) -> set[Permission]:
    """Traduce una celda de la KB (``"CRU"``, ``"*R"``, ``"CRUF"``…) a permisos."""
    if cell == _NO_ACCESS:
        return set()
    permissions: set[Permission] = set()
    index = 0
    while index < len(cell):
        token = cell[index]
        if token == "*":
            action = _OWN_ACTIONS[cell[index + 1]]
            permissions.add(Permission(f"{resource}.{action}"))
            index += 2
            continue
        if token == "T":
            permissions.add(Permission.ownership_transfer)
        elif token == "F":
            permissions.add(Permission.chart_finalize)
        elif token == "D" and resource in _NO_PHYSICAL_DELETE:
            # Restricción horizontal 4 / RN-CMP-02: la KB nunca da ``D`` sobre
            # historia clínica; si alguien lo agrega, el permiso no existe.
            index += 1
            continue
        else:
            permissions.add(Permission(f"{resource}.{_LETTER_ACTIONS[token]}"))
        index += 1
    return permissions


# Recursos clínicos sin ``delete`` físico en ningún rol (RN-CMP-02).
_NO_PHYSICAL_DELETE: Final[frozenset[str]] = frozenset({"clinical_record", "chart"})

# Restricciones horizontales 1, 3 y 6: fuera de los roles clínicos, el acceso a
# la historia clínica y al odontograma no existe. ``billing.can_read_clinical``
# (flag por tenant de la KB) queda como deuda explícita: el default es ``false``.
_NOT_CLINICAL: Final[frozenset[Role]] = frozenset(
    {Role.front_desk, Role.billing, Role.accountant, Role.external_lab}
)
_CLINICAL_ACCESS: Final[frozenset[Permission]] = frozenset(
    {Permission.clinical_record_read, Permission.chart_read, Permission.chart_finalize}
)


def _apply_horizontal_exceptions(
    base: dict[Role, set[Permission]],
) -> dict[Role, set[Permission]]:
    """Aplica las 7 restricciones horizontales de la KB sobre la matriz base."""
    # (1) Recepcionista sin lectura clínica, (3) administración sin editar
    # historia clínica, (6) laboratorio sin nada clínico.
    for role in _NOT_CLINICAL:
        base[role] -= _CLINICAL_ACCESS
    # (2) Solo el profesional cierra el odontograma: el ``U`` del higienista no
    # habilita ``FINALIZADO``.
    for role, permissions in base.items():
        if role is not Role.professional:
            permissions.discard(Permission.chart_finalize)
    base[Role.professional].add(Permission.chart_finalize)
    # (5) El paciente solo accede a lo propio: ningún permiso pleno.
    base[Role.patient] = {
        permission for permission in base[Role.patient] if permission.value.endswith("_own")
    }
    # (4) Nadie tiene ``delete`` físico sobre historia clínica ni odontograma: lo
    # garantiza ``_NO_PHYSICAL_DELETE`` en ``_expand`` y la ausencia del permiso
    # en ``Permission``. (7) No existe ``SuperAdmin`` en ``Role``.
    return base


def _build_role_permissions() -> dict[Role, frozenset[Permission]]:
    base: dict[Role, set[Permission]] = {role: set() for role in _ROLE_ORDER}
    for row in _KB_MATRIX:
        resource, *cells = row
        for role, cell in zip(_ROLE_ORDER, cells, strict=True):
            base[role].update(_expand(resource, cell))
    resolved = _apply_horizontal_exceptions(base)
    return {role: frozenset(permissions) for role, permissions in resolved.items()}


def _build_resource_actions() -> dict[str, frozenset[str]]:
    actions: dict[str, set[str]] = {}
    for row in _KB_MATRIX:
        resource, *cells = row
        bucket = actions.setdefault(resource, set())
        for cell in cells:
            for permission in _expand(resource, cell):
                bucket.add(permission.value.split(".", 1)[1])
    actions[_AUDIT_RESOURCE] = {"read"}
    return {resource: frozenset(values) for resource, values in actions.items()}


#: Permisos efectivos por rol: 9 entradas, ninguna vacía.
ROLE_PERMISSIONS: Final[dict[Role, frozenset[Permission]]] = _build_role_permissions()

#: Acciones declaradas por recurso, independientes de quién las tenga.
RESOURCE_ACTIONS: Final[dict[str, frozenset[str]]] = _build_resource_actions()

#: Los 18 recursos del dominio, en el orden de la KB.
DOMAIN_RESOURCES: Final[tuple[str, ...]] = tuple(RESOURCE_ACTIONS)


def resolve_permissions(roles: Iterable[Role | str]) -> frozenset[Permission]:
    """Unión de los permisos de las memberships activas (fail-closed).

    Un rol repetido no duplica nada (es un conjunto) y un rol desconocido se
    descarta: nunca "permite todo". La lista vacía es el conjunto vacío.
    """
    resolved: set[Permission] = set()
    for role in roles:
        try:
            normalized = Role(role)
        except ValueError:
            continue
        resolved |= ROLE_PERMISSIONS.get(normalized, frozenset())
    return frozenset(resolved)
