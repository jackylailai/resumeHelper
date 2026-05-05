"""P1-T04: POST /api/evaluate — TDD RED."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

_JD = "Looking for a Python backend engineer with FastAPI and PostgreSQL experience."


@pytest.mark.integration
def test_evaluate_returns_score(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, FastAPI, PostgreSQL"})
    r = client.post("/api/evaluate", json={"jd_text": _JD})
    assert r.status_code == 200
    data = r.json()["data"]
    assert 0 <= data["score"] <= 100
    assert data["explanation"]
    assert isinstance(data["strengths"], list)
    assert isinstance(data["gaps"], list)


@pytest.mark.integration
def test_evaluate_same_jd_twice_uses_cache(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    r1 = client.post("/api/evaluate", json={"jd_text": _JD})
    r2 = client.post("/api/evaluate", json={"jd_text": _JD})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["meta"].get("cached") is True


@pytest.mark.integration
def test_evaluate_without_profile_returns_404(client: TestClient):
    r = client.post("/api/evaluate", json={"jd_text": _JD})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


@pytest.mark.integration
def test_evaluate_missing_jd_returns_422(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python"})
    r = client.post("/api/evaluate", json={})
    assert r.status_code == 422


@pytest.mark.integration
def test_evaluate_stores_job_analysis(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    client.post("/api/evaluate", json={"jd_text": _JD})
    history = client.get("/api/history").json()["data"]
    assert len(history) >= 1
    assert history[0]["score"] is not None
