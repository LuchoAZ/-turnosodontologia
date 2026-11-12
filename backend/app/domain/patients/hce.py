"""Número de historia clínica secuencial y no reciclable (C-06, D4).

El número sale de ``patient_counter`` con un upsert atómico y solo avanza: un
paciente dado de baja no libera su número (RN-CLI-01). El formato es de al menos
6 dígitos y crece a 7 o más sin romper la columna ``varchar(20)``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

_DIGITOS_MINIMOS = 6

_SIGUIENTE_SQL = text(
    """
    INSERT INTO patient_counter (tenant_id, ultimo_numero)
    VALUES (:tenant_id, 1)
    ON CONFLICT (tenant_id) DO UPDATE
      SET ultimo_numero = patient_counter.ultimo_numero + 1,
          updated_at = now()
    RETURNING ultimo_numero
    """
)


def formatear_numero(secuencia: int) -> str:
    """``1`` → ``"000001"``; ``1_000_000`` → ``"1000000"`` (crece sin romper el formato)."""
    if secuencia < 1:
        raise ValueError("La secuencia de historia clínica arranca en 1.")
    return f"{secuencia:0{_DIGITOS_MINIMOS}d}"


def siguiente_numero_historia_clinica(db: Session, tenant_id: UUID) -> str:
    """Reserva el próximo número del tenant con un upsert atómico (D4).

    Corre dentro de la transacción del llamador: si el alta falla después y la
    transacción revierte, el incremento se revierte con ella y no queda hueco
    (S4.5). El ``ON CONFLICT DO UPDATE`` toma un lock de fila sobre el contador,
    así que dos altas concurrentes del mismo tenant se serializan (S4.4).
    """
    secuencia = db.execute(_SIGUIENTE_SQL, {"tenant_id": tenant_id}).scalar_one()
    return formatear_numero(int(secuencia))
