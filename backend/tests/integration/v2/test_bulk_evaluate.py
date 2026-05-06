"""Tests for POST /api/evaluate/bulk."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

_JD_A = "Looking for a Python backend engineer with FastAPI and PostgreSQL."
_JD_B = "Seeking a senior DevOps engineer with Kubernetes and Terraform."
_JD_C = "Frontend role: React, TypeScript, CSS. No backend required."

_PROFILE = "Python, FastAPI, PostgreSQL, Docker, 5 years backend experience"


@pytest.mark.integration
def test_bulk_evaluate_returns_results(client: TestClient):
    client.post("/api/profile", json={"skills_text": _PROFILE})
    r = client.post("/api/evaluate/bulk", json={"jd_texts": [_JD_A, _JD_B]})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 2
    assert data["new"] + data["cached"] == 2
    assert len(data["results"]) == 2
    for result in data["results"]:
        assert 0 <= result["score"] <= 100
        assert result["status"] in ("ready_to_submit", "needs_tailoring", "skip")
        assert isinstance(result["cached"], bool)
        assert result["job_analysis_id"]


@pytest.mark.integration
def test_bulk_evaluate_deduplicates_same_jd_in_batch(client: TestClient):
    client.post("/api/profile", json={"skills_text": _PROFILE})
    # Submit same JD twice in one bulk request
    r = client.post("/api/evaluate/bulk", json={"jd_texts": [_JD_A, _JD_A]})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 2
    assert data["new"] == 1
    assert data["cached"] == 1
    # Both results point to the same job_analysis_id
    ids = [res["job_analysis_id"] for res in data["results"]]
    assert ids[0] == ids[1]


@pytest.mark.integration
def test_bulk_evaluate_caches_previously_evaluated_jd(client: TestClient):
    client.post("/api/profile", json={"skills_text": _PROFILE})
    # First: single evaluate
    client.post("/api/evaluate", json={"jd_text": _JD_A})
    # Then: bulk includes same JD
    r = client.post("/api/evaluate/bulk", json={"jd_texts": [_JD_A, _JD_B]})
    assert r.status_code == 200
    data = r.json()["data"]
    cached_results = [res for res in data["results"] if res["cached"]]
    assert len(cached_results) == 1
    assert cached_results[0]["score"] is not None


@pytest.mark.integration
def test_bulk_evaluate_without_profile_returns_404(client: TestClient):
    r = client.post("/api/evaluate/bulk", json={"jd_texts": [_JD_A]})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


@pytest.mark.integration
def test_bulk_evaluate_empty_list_returns_422(client: TestClient):
    client.post("/api/profile", json={"skills_text": _PROFILE})
    r = client.post("/api/evaluate/bulk", json={"jd_texts": []})
    assert r.status_code == 422


@pytest.mark.integration
def test_bulk_evaluate_stores_all_in_history(client: TestClient):
    client.post("/api/profile", json={"skills_text": _PROFILE})
    client.post("/api/evaluate/bulk", json={"jd_texts": [_JD_A, _JD_B, _JD_C]})
    history = client.get("/api/history").json()["data"]
    assert len(history) >= 3
