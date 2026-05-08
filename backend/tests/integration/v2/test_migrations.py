from __future__ import annotations

import pytest


@pytest.mark.integration
def test_alembic_upgrade_head_smoke(monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from testcontainers.postgres import PostgresContainer

    from backend.app.config import get_settings

    with PostgresContainer("postgres:16-alpine") as pg:
        database_url = pg.get_connection_url().replace("psycopg2", "psycopg2")
        monkeypatch.setenv("DATABASE_URL", database_url)
        get_settings.cache_clear()
        try:
            config = Config("backend/alembic.ini")
            command.upgrade(config, "head")

            engine = create_engine(database_url)
            try:
                with engine.connect() as conn:
                    version = conn.execute(text("SELECT version_num FROM alembic_version"))
                    assert version.scalar_one()
            finally:
                engine.dispose()
        finally:
            get_settings.cache_clear()
