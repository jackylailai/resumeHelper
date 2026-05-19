from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.db import get_db


def _isolated_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    database_url: str = "postgresql://postgres:postgres@localhost:5432/rate_limit_unused",
    rate_limit_enabled: bool = True,
    extra_env: dict[str, str] | None = None,
) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-tests")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", str(rate_limit_enabled).lower())
    for key, value in (extra_env or {}).items():
        monkeypatch.setenv(key, value)

    from backend.app.config import get_settings
    from backend.app.main import create_app

    get_settings.cache_clear()
    return TestClient(create_app())


@pytest.mark.integration
def test_evaluate_rate_limit_allows_configured_window_then_returns_429(
    client: TestClient,
) -> None:
    client.post("/api/profile", json={"skills_text": "Python, FastAPI, PostgreSQL"})

    for index in range(10):
        response = client.post(
            "/api/evaluate",
            json={"jd_text": f"Backend API role {index}. [[score=95]]"},
        )
        assert response.status_code == 200

    limited = client.post(
        "/api/evaluate",
        json={"jd_text": "Backend API role over limit. [[score=95]]"},
    )

    assert limited.status_code == 429
    assert limited.headers["Retry-After"].isdigit()
    body = limited.json()
    assert body["data"] is None
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["details"]["limit"] == 10
    assert body["error"]["details"]["window_seconds"] == 60
    assert body["error"]["details"]["retry_after_seconds"] >= 1
    assert body["meta"]["retry_after_seconds"] >= 1


def test_bulk_evaluate_rate_limit_is_route_specific(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with _isolated_client(monkeypatch, tmp_path) as client:
        assert client.post("/api/evaluate/bulk", json={}).status_code == 422
        assert client.post("/api/evaluate/bulk", json={}).status_code == 422

        limited = client.post("/api/evaluate/bulk", json={})

    assert limited.status_code == 429
    assert limited.json()["error"]["details"]["limit"] == 2


def test_rate_limit_can_be_disabled_with_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with _isolated_client(monkeypatch, tmp_path, rate_limit_enabled=False) as client:
        responses = [client.post("/api/evaluate/bulk", json={}) for _ in range(4)]

    assert [response.status_code for response in responses] == [422, 422, 422, 422]


def test_endpoint_limit_can_be_overridden_with_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with _isolated_client(
        monkeypatch,
        tmp_path,
        extra_env={"RATE_LIMIT_EVALUATE_BULK_PER_MINUTE": "1"},
    ) as client:
        assert client.post("/api/evaluate/bulk", json={}).status_code == 422
        limited = client.post("/api/evaluate/bulk", json={})

    assert limited.status_code == 429
    assert limited.json()["error"]["details"]["limit"] == 1


@pytest.mark.integration
def test_scrape_run_rate_limit_uses_separate_bucket(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    monkeypatch.setattr(
        "backend.app.api.scrape.run_scrape_background",
        lambda _run_ids, _session_factory: None,
    )

    for index in range(3):
        response = client.post(
            "/api/scrape/run",
            json={"source": "104", "keyword": f"backend-{index}", "limit": 1},
        )
        assert response.status_code == 202

    limited = client.post(
        "/api/scrape/run",
        json={"source": "104", "keyword": "backend-over-limit", "limit": 1},
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["details"]["limit"] == 3


@pytest.mark.integration
def test_callback_rate_limit_is_protected(
    db_engine,
    fake_llm,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(db_engine.url))
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-tests")

    from backend.app.config import get_settings
    from backend.app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    Session = sessionmaker(bind=db_engine)

    def override_db() -> Generator:
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        app.state.llm_client = fake_llm
        app.state.session_factory = Session
        for _ in range(10):
            response = client.post(
                "/api/callback",
                json={
                    "job_analysis_id": "00000000-0000-0000-0000-000000000000",
                    "resume_text": "test",
                },
            )
            assert response.status_code == 404

        limited = client.post(
            "/api/callback",
            json={
                "job_analysis_id": "00000000-0000-0000-0000-000000000000",
                "resume_text": "test",
            },
        )

    assert limited.status_code == 429
    assert limited.json()["error"]["details"]["limit"] == 10
