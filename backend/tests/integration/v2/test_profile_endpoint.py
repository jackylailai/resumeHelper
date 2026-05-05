"""P1-T04: POST /api/profile and GET /api/profile — TDD RED."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_set_profile_returns_200(client: TestClient):
    r = client.post("/api/profile", json={"skills_text": "Python, FastAPI, Docker"})
    assert r.status_code == 200
    assert r.json()["error"] is None
    assert r.json()["data"]["skills_text"] == "Python, FastAPI, Docker"


@pytest.mark.integration
def test_get_profile_returns_latest(client: TestClient):
    client.post("/api/profile", json={"skills_text": "First version"})
    client.post("/api/profile", json={"skills_text": "Updated skills"})
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["data"]["skills_text"] == "Updated skills"


@pytest.mark.integration
def test_get_profile_404_when_empty(client: TestClient):
    r = client.get("/api/profile")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


@pytest.mark.integration
def test_profile_missing_skills_text_returns_422(client: TestClient):
    r = client.post("/api/profile", json={})
    assert r.status_code == 422
