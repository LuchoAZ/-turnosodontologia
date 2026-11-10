"""Hash de contraseñas con Argon2id (design D5/D6, RN-AU-04).

Los parámetros completos se usan siempre salvo en ``ENVIRONMENT=test``, donde se
reducen para que la suite no gaste 64 MiB por hash. El hash guarda sus propios
parámetros: ``verify_password`` no depende del entorno y ``needs_rehash`` compara
contra los parámetros vigentes para ese entorno.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Environment

_HASH_LEN = 32

# Producción/desarrollo: OWASP Argon2id baseline.
_STRONG = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=_HASH_LEN,
)

# Solo ENVIRONMENT=test: misma familia, coste mínimo.
_FAST = PasswordHasher(
    time_cost=1,
    memory_cost=8 * 1024,
    parallelism=1,
    hash_len=_HASH_LEN,
)


def _hasher(environment: Environment | str) -> PasswordHasher:
    return _FAST if Environment(environment) is Environment.test else _STRONG


def hash_password(password: str, environment: Environment | str = Environment.production) -> str:
    """Devuelve un hash Argon2id con sal aleatoria."""
    return _hasher(environment).hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """``True`` solo si ``password`` corresponde a ``password_hash``."""
    try:
        return _STRONG.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(
    password_hash: str, environment: Environment | str = Environment.production
) -> bool:
    """``True`` cuando el hash se generó con parámetros distintos a los vigentes."""
    try:
        return _hasher(environment).check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
