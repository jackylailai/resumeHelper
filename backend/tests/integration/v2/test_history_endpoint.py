"""P1-T04: GET /api/history and GET /api/history/{id} — TDD RED."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

_JD = "Seeking a backend engineer with Python and REST API experience."


@pytest.mark.integration
def test_history_list_empty_initially(client: TestClient):
    r = client.get("/api/history")
    assert r.status_code == 200
    assert r.json()["data"] == []


@pytest.mark.integration
def test_history_list_shows_past_analyses(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, REST APIs"})
    client.post("/api/evaluate", json={"jd_text": _JD})
    r = client.get("/api/history")
    assert r.status_code == 200
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["score"] is not None
    assert items[0]["jd_snippet"]


@pytest.mark.integration
def test_history_detail_returns_full_data(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python"})
    client.post("/api/evaluate", json={"jd_text": _JD})
    item_id = client.get("/api/history").json()["data"][0]["id"]

    r = client.get(f"/api/history/{item_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["jd_full_text"] == _JD
    assert data["score"] is not None
    assert isinstance(data["generated_resumes"], list)


@pytest.mark.integration
def test_history_detail_404_unknown_id(client: TestClient):
    r = client.get("/api/history/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
