"""Tests for multi-profile CRUD endpoints and profile-scoped evaluation."""
from __future__ import annotations
import io
import pytest
from fastapi.testclient import TestClient


def _make_minimal_pdf(text: str = "Python FastAPI PostgreSQL") -> bytes:
    from backend.tests.unit.test_parsing import make_minimal_pdf
    return make_minimal_pdf(text)


@pytest.mark.integration
def test_list_profiles_empty(client: TestClient):
    r = client.get("/api/profiles")
    assert r.status_code == 200
    assert r.json()["data"] == []


@pytest.mark.integration
def test_create_profile(client: TestClient):
    r = client.post("/api/profiles", json={"skills_text": "Python, Docker", "name": "Backend"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["skills_text"] == "Python, Docker"
    assert d["name"] == "Backend"
    assert d["id"] is not None


@pytest.mark.integration
def test_list_profiles_returns_all(client: TestClient):
    client.post("/api/profiles", json={"skills_text": "Java", "name": "Java CV"})
    client.post("/api/profiles", json={"skills_text": "Python", "name": "Python CV"})
    r = client.get("/api/profiles")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 2


@pytest.mark.integration
def test_get_single_profile(client: TestClient):
    created = client.post("/api/profiles", json={"skills_text": "Go", "name": "Go CV"}).json()["data"]
    r = client.get(f"/api/profiles/{created['id']}")
    assert r.status_code == 200
    assert r.json()["data"]["skills_text"] == "Go"


@pytest.mark.integration
def test_get_profile_404(client: TestClient):
    r = client.get("/api/profiles/9999")
    assert r.status_code == 404


@pytest.mark.integration
def test_update_profile(client: TestClient):
    created = client.post("/api/profiles", json={"skills_text": "Old text"}).json()["data"]
    r = client.put(f"/api/profiles/{created['id']}", json={"skills_text": "New text", "name": "Updated"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["skills_text"] == "New text"
    assert d["name"] == "Updated"


@pytest.mark.integration
def test_delete_profile(client: TestClient):
    created = client.post("/api/profiles", json={"skills_text": "To be deleted"}).json()["data"]
    r = client.delete(f"/api/profiles/{created['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/profiles/{created['id']}").status_code == 404


@pytest.mark.integration
def test_upload_profile_pdf(client: TestClient):
    pdf_bytes = _make_minimal_pdf("Python FastAPI Docker Kubernetes")
    r = client.post(
        "/api/profiles/upload",
        files={"file": ("resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"name": "PDF Profile"},
    )
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["name"] == "PDF Profile"
    assert len(d["skills_text"]) > 0


@pytest.mark.integration
def test_evaluate_with_explicit_profile_id(client: TestClient):
    p1 = client.post("/api/profiles", json={"skills_text": "Python FastAPI"}).json()["data"]
    p2 = client.post("/api/profiles", json={"skills_text": "Java Spring"}).json()["data"]
    jd = "Looking for a Python backend engineer."
    r = client.post("/api/evaluate", json={"jd_text": jd, "profile_id": p1["id"]})
    assert r.status_code == 200
    assert 0 <= r.json()["data"]["score"] <= 100


@pytest.mark.integration
def test_evaluate_defaults_to_latest_profile(client: TestClient):
    client.post("/api/profiles", json={"skills_text": "Python FastAPI"})
    r = client.post("/api/evaluate", json={"jd_text": "Python backend role."})
    assert r.status_code == 200


@pytest.mark.integration
def test_evaluate_different_profiles_are_cached_separately(client: TestClient):
    p1 = client.post("/api/profiles", json={"skills_text": "Python"}).json()["data"]
    p2 = client.post("/api/profiles", json={"skills_text": "Java"}).json()["data"]
    jd = "Backend engineer with strong programming skills."
    r1 = client.post("/api/evaluate", json={"jd_text": jd, "profile_id": p1["id"]})
    r2 = client.post("/api/evaluate", json={"jd_text": jd, "profile_id": p2["id"]})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Same JD, different profiles → NOT a cache hit for r2
    assert r2.json()["meta"].get("cached") is not True


@pytest.mark.integration
def test_evaluate_same_profile_and_jd_is_cached(client: TestClient):
    p = client.post("/api/profiles", json={"skills_text": "Python"}).json()["data"]
    jd = "Looking for Python developer."
    client.post("/api/evaluate", json={"jd_text": jd, "profile_id": p["id"]})
    r2 = client.post("/api/evaluate", json={"jd_text": jd, "profile_id": p["id"]})
    assert r2.json()["meta"].get("cached") is True


@pytest.mark.integration
def test_legacy_post_profile_still_works(client: TestClient):
    r = client.post("/api/profile", json={"skills_text": "Legacy text"})
    assert r.status_code == 200
    assert r.json()["data"]["skills_text"] == "Legacy text"


@pytest.mark.integration
def test_legacy_get_profile_returns_latest(client: TestClient):
    client.post("/api/profiles", json={"skills_text": "First"})
    client.post("/api/profiles", json={"skills_text": "Second"})
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["data"]["skills_text"] == "Second"
