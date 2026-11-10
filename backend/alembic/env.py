"""Alembic runtime environment.

La URL sale de ``sqlalchemy.url`` cuando el llamador la inyecta (tests con
Testcontainers) y, si no, de ``DIRECT_URL``/``DATABASE_URL``. El metadata es el
de los modelos SQLAlchemy de C-02, así ``alembic revision --autogenerate``
detecta cambios futuros.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from app.models import auth, catalog, tenancy  # noqa: F401  (registra las tablas)
from app.models.base import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _normalize(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return _normalize(configured)

    url = os.environ.get("DIRECT_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DIRECT_URL or DATABASE_URL must be set to run migrations")
    return _normalize(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
