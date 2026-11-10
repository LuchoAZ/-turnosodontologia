"""Plumbing de DB y Redis de la app (tasks 2.1/2.2, design D11).

La app se conecta como ``odontologia_app``; el superusuario del contenedor solo
corre Alembic y siembra. Un smoke de ``/health`` prueba que el lifespan levanta
engine y Redis sin tocar la base.
"""

from __future__ import annotations

from app.config import Settings
from app.db.engine import create_db_engine, create_session_factory
from app.db.redis import create_redis_client
from fastapi.testclient import TestClient
from sqlalchemy import text


def test_engine_connects_as_the_app_role(auth_settings: Settings) -> None:
    engine = create_db_engine(auth_settings)
    try:
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT current_user").scalar_one()
                == "odontologia_app"
            )
            assert (
                connection.exec_driver_sql("SELECT current_setting('is_superuser')").scalar_one()
                == "off"
            )
    finally:
        engine.dispose()


def test_app_engine_reads_zero_sessions_without_context(auth_settings: Settings) -> None:
    engine = create_db_engine(auth_settings)
    try:
        with engine.connect() as connection:
            total = connection.execute(text("SELECT count(*) FROM session")).scalar_one()
        assert total == 0
    finally:
        engine.dispose()


def test_redis_client_answers_ping(auth_settings: Settings) -> None:
    client = create_redis_client(auth_settings)
    try:
        assert client.ping() is True
    finally:
        client.close()


def test_session_factory_yields_a_working_session(auth_settings: Settings) -> None:
    engine = create_db_engine(auth_settings)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_health_smoke_uses_the_real_lifespan(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
