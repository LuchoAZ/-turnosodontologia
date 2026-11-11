"""Fidelidad de la matriz RBAC contra `knowledge-base/03_actores_y_roles.md` (D1).

La tabla de abajo es una transcripción **literal** de las líneas 33-48 de la KB
(9 columnas de rol, 16 filas de recurso) más las 7 restricciones horizontales.
No importa nada de la implementación para construirla: si `matrix.py` cambia la
matriz, este test falla.
"""

from __future__ import annotations

import pytest
from app.domain.rbac import matrix
from app.domain.rbac.matrix import (
    DOMAIN_RESOURCES,
    RESOURCE_ACTIONS,
    ROLE_PERMISSIONS,
    Permission,
    resolve_permissions,
)
from app.models.tenancy import Role

# (recurso, owner, clinical_admin, professional, assistant, front_desk, billing,
#  patient, external_lab, accountant) — letras C R U D y "—" tal como la KB.
# Tokens especiales: "T" = ownership.transfer, "*C" = create_own, "*R" = read_own,
# "F" = chart.finalize.
KB_TABLE: tuple[tuple[str, ...], ...] = (
    ("tenant_settings", "CRU", "R", "R", "R", "R", "R", "—", "—", "—"),
    ("chair", "CRUD", "CRU", "R", "R", "R", "—", "—", "—", "—"),
    ("professional", "CRU", "CRU", "R", "R", "R", "—", "—", "—", "—"),
    ("team", "CRUDT", "R", "—", "—", "—", "R", "—", "—", "—"),
    ("clinical_record", "R", "R", "CRU", "CR", "—", "—", "*R", "—", "—"),
    ("chart", "R", "R", "CRUF", "CR", "—", "—", "*R", "—", "—"),
    ("consent", "R", "R", "CR", "CR", "R", "—", "*R", "—", "—"),
    ("appointment", "CRUD", "CRU", "R", "R", "CRUD", "R", "*C*R", "R", "—"),
    ("cash", "CRU", "—", "—", "—", "CRU", "CRU", "*R", "—", "—"),
    ("invoice", "CRU", "R", "—", "—", "CR", "CRU", "*R", "—", "R"),
    ("settlement", "CRU", "R", "*R", "R", "—", "CRU", "—", "—", "R"),
    ("report_financial", "R", "—", "—", "—", "R", "R", "—", "—", "R"),
    ("report_usage", "R", "R", "R", "R", "R", "R", "—", "—", "—"),
    ("migration", "CRU", "—", "—", "—", "—", "—", "—", "—", "—"),
    ("aaip_request", "CR", "R", "—", "—", "R", "R", "*C", "—", "—"),
    ("whatsapp_config", "CRU", "R", "—", "—", "R", "R", "—", "—", "—"),
)

ROLE_ORDER: tuple[Role, ...] = (
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

_LETTERS = {"C": "create", "R": "read", "U": "update", "D": "delete"}


def _expand(resource: str, cell: str) -> set[str]:
    if cell == "—":
        return set()
    permissions: set[str] = set()
    index = 0
    while index < len(cell):
        char = cell[index]
        if char == "*":
            action = "create_own" if cell[index + 1] == "C" else "read_own"
            permissions.add(f"{resource}.{action}")
            index += 2
            continue
        if char == "T":
            permissions.add("ownership.transfer")
        elif char == "F":
            permissions.add("chart.finalize")
        else:
            permissions.add(f"{resource}.{_LETTERS[char]}")
        index += 1
    return permissions


def _expected_by_role() -> dict[Role, set[str]]:
    expected: dict[Role, set[str]] = {role: set() for role in ROLE_ORDER}
    for row in KB_TABLE:
        resource, *cells = row
        for role, cell in zip(ROLE_ORDER, cells, strict=True):
            expected[role].update(_expand(resource, cell))
    return expected


def test_matriz_completa_coincide_con_la_kb() -> None:
    expected = _expected_by_role()
    actual = {
        role: {permission.value for permission in perms}
        for role, perms in ROLE_PERMISSIONS.items()
    }

    assert actual == {role: expected[role] for role in ROLE_PERMISSIONS}


def test_owner_no_es_un_superusuario() -> None:
    owner = {permission.value for permission in ROLE_PERMISSIONS[Role.owner]}

    assert "ownership.transfer" in owner
    assert "team.delete" in owner
    assert "chart.finalize" not in owner
    assert "chart.create" not in owner
    assert "clinical_record.update" not in owner


def test_solo_el_profesional_finaliza_odontograma() -> None:
    holders = {
        role
        for role, permissions in ROLE_PERMISSIONS.items()
        if Permission.chart_finalize in permissions
    }

    assert holders == {Role.professional}


@pytest.mark.parametrize(
    "role",
    [Role.front_desk, Role.billing, Role.accountant, Role.external_lab],
)
def test_frontera_clinica_por_permiso(role: Role) -> None:
    permissions = ROLE_PERMISSIONS[role]

    assert Permission.clinical_record_read not in permissions
    assert Permission.chart_read not in permissions
    assert Permission.chart_finalize not in permissions


def test_los_permisos_propios_no_se_mezclan_con_los_plenos() -> None:
    patient = ROLE_PERMISSIONS[Role.patient]

    assert Permission.appointment_create_own in patient
    assert Permission.appointment_read_own in patient
    assert Permission.appointment_create not in patient
    assert Permission.appointment_read not in patient
    assert Permission.settlement_read_own in ROLE_PERMISSIONS[Role.professional]
    assert Permission.settlement_read_own not in patient


def test_catalogo_de_recursos_y_enum_coherentes() -> None:
    assert len(DOMAIN_RESOURCES) == 18
    assert set(RESOURCE_ACTIONS) == set(DOMAIN_RESOURCES)
    assert {permission.split(".")[0] for permission in (p.value for p in Permission)} == set(
        DOMAIN_RESOURCES
    )
    assert len(Permission) == 57


def test_ningun_rol_tiene_lectura_de_auditoria() -> None:
    assert all(
        Permission.membership_event_read not in permissions
        for permissions in ROLE_PERMISSIONS.values()
    )


def test_resolve_permissions_es_la_union_y_falla_cerrado() -> None:
    assert resolve_permissions([Role.front_desk]) == ROLE_PERMISSIONS[Role.front_desk]
    assert resolve_permissions([Role.front_desk, Role.professional]) == (
        ROLE_PERMISSIONS[Role.front_desk] | ROLE_PERMISSIONS[Role.professional]
    )
    assert resolve_permissions([]) == frozenset()
    assert resolve_permissions(["rol_inexistente"]) == frozenset()
    assert resolve_permissions(["owner"]) == ROLE_PERMISSIONS[Role.owner]
    # Rol repetido: la unión es un conjunto, no duplica ni suma.
    assert resolve_permissions([Role.front_desk, Role.front_desk]) == (
        ROLE_PERMISSIONS[Role.front_desk]
    )


def test_recursos_desdoblados_y_auditoria_sin_titulares() -> None:
    # "Usuarios y roles" se desdobla: el CRUD de memberships no incluye la
    # transferencia de ownership (RN-TEN-04) y viceversa.
    assert RESOURCE_ACTIONS["team"] == frozenset({"create", "read", "update", "delete"})
    assert RESOURCE_ACTIONS["ownership"] == frozenset({"transfer"})
    assert RESOURCE_ACTIONS["membership_event"] == frozenset({"read"})
    # El catálogo declara las acciones clínicas sin ``delete`` físico (RN-CMP-02).
    assert "delete" not in RESOURCE_ACTIONS["clinical_record"]
    assert "delete" not in RESOURCE_ACTIONS["chart"]


def test_fail_closed_si_falta_la_clave_en_la_matriz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una clave ausente en la matriz resuelve a vacío, nunca a "todo permitido"."""
    monkeypatch.setattr(matrix, "ROLE_PERMISSIONS", {})

    assert resolve_permissions([Role.owner, Role.professional]) == frozenset()
