"""Lockout progresivo como estado del ``user`` (design D6, RN-AU-05).

Funciones puras: reciben el estado persistido (``failed_login_count``,
``lockout_strikes``, ``locked_until``) y ``now``, y devuelven el estado nuevo.
La atomicidad la da el ``UPDATE ... RETURNING`` de la capa de servicio; acá solo
vive la regla.

Estados:

- ``NORMAL``   → ``locked_until IS NULL`` o ya venció: se comparan credenciales.
- ``LOCKED``   → ``locked_until > now``: se rechaza **antes** de mirar el password.
- ``RESET``    → login correcto: contadores y rachas a cero.

Ventana: 15 min por 2^(strikes-1), tope 24 h. La racha sobrevive al vencimiento
(para que el segundo bloqueo consecutivo duplique); el contador de fallos no.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

MAX_FAILED_LOGIN_COUNT = 5
BASE_LOCK_MINUTES = 15
MAX_LOCK_MINUTES = 24 * 60


@dataclass(frozen=True)
class LockoutState:
    failed_login_count: int = 0
    lockout_strikes: int = 0
    locked_until: datetime | None = None


def is_locked(state: LockoutState, now: datetime) -> bool:
    return state.locked_until is not None and state.locked_until > now


def retry_after_seconds(state: LockoutState, now: datetime) -> int:
    if not is_locked(state, now):
        return 0
    assert state.locked_until is not None  # narrowed by is_locked
    return max(0, int((state.locked_until - now).total_seconds()))


def normalize(state: LockoutState, now: datetime) -> LockoutState:
    """Estado vigente: un bloqueo vencido vuelve a ``NORMAL`` con contador en 0.

    La racha (``lockout_strikes``) no se pierde: el siguiente bloqueo consecutivo
    la duplica.
    """
    if state.locked_until is not None and state.locked_until <= now:
        return replace(state, failed_login_count=0, locked_until=None)
    return state


def register_failure(state: LockoutState, now: datetime) -> LockoutState:
    """Suma un fallo; al quinto, bloquea con la ventana exponencial."""
    current = normalize(state, now)
    if is_locked(current, now):
        return current

    failed = current.failed_login_count + 1
    if failed < MAX_FAILED_LOGIN_COUNT:
        return replace(current, failed_login_count=failed)

    strikes = current.lockout_strikes + 1
    lock_minutes = min(MAX_LOCK_MINUTES, BASE_LOCK_MINUTES * 2 ** (strikes - 1))
    return replace(
        current,
        failed_login_count=MAX_FAILED_LOGIN_COUNT,
        lockout_strikes=strikes,
        locked_until=now + timedelta(minutes=lock_minutes),
    )


def register_success(state: LockoutState, now: datetime) -> LockoutState:
    """Login correcto: resetea todo, salvo que la cuenta siga bloqueada."""
    if is_locked(state, now):
        return state
    return LockoutState()
