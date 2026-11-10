"""Engine de la aplicación conectado como ``odontologia_app`` (design D11).

La app **no** se conecta como el superusuario del contenedor: un superusuario
ignora RLS incluso con ``FORCE`` y el aislamiento sería ficticio. Cada conexión
abre sesión con ``SET ROLE odontologia_app``; el superusuario queda reservado
para Alembic y para los tests de mutación.

``Session`` es síncrona (los helpers de C-02 y los tests ya lo son); FastAPI
ejecuta endpoints y dependencias sync en el threadpool. La variante async queda
como deuda explícita del design.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings

APP_ROLE = "odontologia_app"


def create_db_engine(settings: Settings) -> Engine:
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

    @event.listens_for(engine, "connect")
    def _set_app_role(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET ROLE {APP_ROLE}")
        finally:
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Fábrica de sesiones ligada al engine de la app (sin estado global)."""
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def get_db(request: Request) -> Iterator[Session]:
    """Dependencia de FastAPI: ``Session`` por request con cierre garantizado."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()
