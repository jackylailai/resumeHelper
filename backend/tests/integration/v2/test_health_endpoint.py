from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models.job_listing import JobListing


def test_health_reports_readiness_and_counts(client: TestClient, db_session: Session):
    db_session.add(
        JobListing(
            source="104",
            source_id="health-1",
            title="Backend Engineer",
            company="Acme",
            location="Taipei",
            url="https://example.com/jobs/health-1",
            description="Build APIs.",
            raw_json={},
        )
    )
    db_session.commit()

    r = client.post(
        "/api/profiles",
        json={"name": "Backend", "skills_text": "Python, FastAPI, PostgreSQL"},
    )
    assert r.status_code == 200

    r = client.get("/api/health")

    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "ok"
    assert body["data"]["checks"]["api"]["status"] == "ok"
    assert body["data"]["checks"]["db"]["status"] == "ok"
    assert body["data"]["checks"]["llm"]["backend"] == "fake"
    assert body["data"]["counts"]["profiles"] == 1
    assert body["data"]["counts"]["job_listings"] == 1
    assert body["data"]["can_evaluate"] is True


def test_health_points_to_profile_setup_when_empty(client: TestClient):
    r = client.get("/api/health")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["counts"]["profiles"] == 0
    assert data["counts"]["job_listings"] == 0
    assert data["can_evaluate"] is False
    assert any(action["kind"] == "profile" for action in data["next_actions"])
    assert any(action["kind"] == "job_listings" for action in data["next_actions"])


def test_health_reports_llm_configuration_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    try:
        r = client.get("/api/health")
    finally:
        get_settings.cache_clear()

    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "degraded"
    assert body["data"]["checks"]["llm"]["status"] == "error"
    assert "ANTHROPIC_API_KEY" in body["data"]["checks"]["llm"]["message"]
    assert body["data"]["can_evaluate"] is False
    assert body["meta"]["request_id"]
    assert r.headers["X-Request-ID"] == body["meta"]["request_id"]
