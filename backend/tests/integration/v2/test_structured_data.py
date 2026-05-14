"""structured_data JSONB column on baseline_profile (#106)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_get_profile_includes_structured_data_field(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    r = client.get("/api/profiles")
    assert r.status_code == 200
    profiles = r.json()["data"]
    assert profiles
    # Field is present even when null (default for newly-created profile)
    assert "structured_data" in profiles[0]
    assert profiles[0]["structured_data"] is None


@pytest.mark.integration
def test_put_structured_data_round_trip(client: TestClient):
    create = client.post("/api/profile", json={"skills_text": "x"})
    profile_id = create.json()["data"]["id"]

    payload = {
        "personal": {"name": "Test User"},
        "work_experience": [
            {
                "employer": "TestCo",
                "title": "SWE",
                "start_date": "2023-01",
                "end_date": "2024-06",
            }
        ],
    }
    r = client.put(f"/api/profiles/{profile_id}/structured", json=payload)
    assert r.status_code == 200
    saved = r.json()["data"]
    assert saved["structured_data"] == payload

    # Re-fetch via GET to confirm persistence
    r2 = client.get(f"/api/profiles/{profile_id}")
    assert r2.json()["data"]["structured_data"] == payload


@pytest.mark.integration
def test_put_structured_data_clears_with_empty_object(client: TestClient):
    create = client.post("/api/profile", json={"skills_text": "x"})
    profile_id = create.json()["data"]["id"]
    client.put(f"/api/profiles/{profile_id}/structured", json={"x": 1})
    r = client.put(f"/api/profiles/{profile_id}/structured", json={})
    assert r.status_code == 200
    assert r.json()["data"]["structured_data"] is None


@pytest.mark.integration
def test_extract_structured_uses_llm(client: TestClient):
    """FakeLLMClient.extract_structured returns canned data — verifies wiring."""
    create = client.post(
        "/api/profile",
        json={"skills_text": "Python, FastAPI, PostgreSQL since 2020"},
    )
    profile_id = create.json()["data"]["id"]

    r = client.post(f"/api/profiles/{profile_id}/structured/extract")
    assert r.status_code == 200, r.text
    saved = r.json()["data"]["structured_data"]
    # Fake client produces predictable shape
    assert saved is not None
    assert saved["personal"]["name"] == "Fake Candidate"
    assert "work_experience" in saved
    assert saved["skills"]["languages"] == ["Python"]


@pytest.mark.integration
def test_extract_structured_invalid_llm_output_returns_502(client: TestClient):
    create = client.post("/api/profile", json={"skills_text": "Python"})
    profile_id = create.json()["data"]["id"]

    class _InvalidExtractLLM:
        def extract_structured(self, _source_text: str) -> dict:
            return {"unknown": "field"}

    client.app.state.llm_client = _InvalidExtractLLM()

    r = client.post(f"/api/profiles/{profile_id}/structured/extract")

    assert r.status_code == 502
    assert r.json()["error"]["code"] == "llm_invalid_output"


@pytest.mark.integration
def test_put_structured_data_unknown_profile_404(client: TestClient):
    r = client.put("/api/profiles/99999/structured", json={"x": 1})
    assert r.status_code == 404


@pytest.mark.integration
def test_extract_structured_unknown_profile_404(client: TestClient):
    r = client.post("/api/profiles/99999/structured/extract")
    assert r.status_code == 404
