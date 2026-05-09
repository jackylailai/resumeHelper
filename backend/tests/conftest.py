from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.llm.fake import FakeLLMClient


# ---------------------------------------------------------------------------
# Database fixture — testcontainers-postgres
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    from testcontainers.postgres import PostgresContainer  # type: ignore[import]

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg2")


@pytest.fixture(scope="session")
def db_engine(postgres_url: str):  # type: ignore[no-untyped-def]
    from backend.app.db import Base
    import backend.app.models  # ensure models are registered  # noqa: F401

    engine = create_engine(postgres_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):  # type: ignore[no-untyped-def]
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        yield session
        session.rollback()  # clean slate after each test
    finally:
        session.close()


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient(default_score=72)


@pytest.fixture
def client(db_engine, fake_llm, tmp_path: Path) -> Generator[TestClient, None, None]:
    # Override settings to point at test DB and temp storage
    os.environ["DATABASE_URL"] = str(db_engine.url)
    os.environ["STORAGE_DIR"] = str(tmp_path / "storage")
    os.environ["LLM_BACKEND"] = "fake"
    os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-tests"

    # Clear lru_cache so settings are re-read with test env
    from backend.app.config import get_settings
    get_settings.cache_clear()

    from backend.app.main import create_app
    from backend.app.db import get_db
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine)

    def override_db() -> Generator:
        s = Session()
        try:
            yield s
        finally:
            s.close()

    test_app = create_app()
    test_app.dependency_overrides[get_db] = override_db

    with TestClient(test_app, raise_server_exceptions=True) as c:
        # Set AFTER lifespan runs (lifespan overwrites app.state.llm_client)
        test_app.state.llm_client = fake_llm
        # Inject test session factory so background tasks use the test DB
        test_app.state.session_factory = Session
        yield c

    # Truncate all tables after each test so next test starts clean
    from sqlalchemy import text
    with db_engine.connect() as conn:
        conn.execute(text(
            "TRUNCATE TABLE applications, generated_resumes, job_listings, "
            "job_analyses, baseline_profile RESTART IDENTITY CASCADE"
        ))
        conn.commit()


# ---------------------------------------------------------------------------
# Sample file fixtures
# ---------------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).parent.parent.parent / "samples"


@pytest.fixture
def sample_jd() -> str:
    return (SAMPLES_DIR / "sample_jd.txt").read_text()


@pytest.fixture
def minimal_pdf_bytes() -> bytes:
    """Minimal valid single-page PDF containing the text 'Hello World'."""
    from backend.tests.unit.test_parsing import make_minimal_pdf
    return make_minimal_pdf("Hello World")
