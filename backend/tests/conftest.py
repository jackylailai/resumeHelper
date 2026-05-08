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

    # Inject FakeLLMClient (used by evaluator service via DI in US1)
    test_app.state.llm_client = fake_llm

    with TestClient(test_app, raise_server_exceptions=True) as c:
        yield c


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
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>\nstream\nBT /F1 12 Tf 100 700 Td"
        b" (Hello World) Tj ET\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f\n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
