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
    assert d["is_default"] is False
    assert d["created_at"] is not None
    assert d["updated_at"] is not None
    assert d["pdf_path"] is None


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
def test_set_default_profile(client: TestClient):
    p1 = client.post("/api/profiles", json={"skills_text": "Python", "name": "P1"}).json()["data"]
    p2 = client.post("/api/profiles", json={"skills_text": "Java", "name": "P2"}).json()["data"]
    assert p1["is_default"] is False
    assert p2["is_default"] is False

    r = client.put(f"/api/profiles/{p2['id']}", json={"is_default": True})
    assert r.status_code == 200
    profiles = client.get("/api/profiles").json()["data"]
    defaults = [profile for profile in profiles if profile["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == p2["id"]


@pytest.mark.integration
def test_delete_profile(client: TestClient):
    created = client.post("/api/profiles", json={"skills_text": "To be deleted"}).json()["data"]
    r = client.delete(f"/api/profiles/{created['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/profiles/{created['id']}").status_code == 404


@pytest.mark.integration
def test_profile_delete_impact_counts_related_history(client: TestClient):
    profile = client.post("/api/profiles", json={"skills_text": "Python"}).json()["data"]
    evaluate = client.post(
        "/api/evaluate",
        json={"jd_text": "Python backend role [[score=86]]", "profile_id": profile["id"]},
    )
    assert evaluate.status_code == 200

    r = client.get(f"/api/profiles/{profile['id']}/delete-impact")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["job_analyses_count"] == 1
    assert d["generated_resumes_count"] == 0


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
def test_preview_profile_pdf_does_not_create_profile(client: TestClient):
    pdf_bytes = _make_minimal_pdf("Preview Python FastAPI")
    r = client.post(
        "/api/profiles/upload/preview",
        files={"file": ("resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["filename"] == "resume.pdf"
    assert "Preview" in d["skills_text"]
    assert client.get("/api/profiles").json()["data"] == []


@pytest.mark.integration
def test_upload_profile_pdf_allows_reviewed_text_override(client: TestClient):
    pdf_bytes = _make_minimal_pdf("Extracted text")
    r = client.post(
        "/api/profiles/upload",
        files={"file": ("resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"name": "Reviewed", "skills_text": "Reviewed skills", "is_default": "true"},
    )
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["skills_text"] == "Reviewed skills"
    assert d["is_default"] is True
    assert d["pdf_path"]


@pytest.mark.integration
def test_upload_profile_pdf_persists_file(client: TestClient):
    """The uploaded PDF bytes should be written to disk and the resulting
    path should be saved on baseline_profile.pdf_path."""
    from pathlib import Path

    pdf_bytes = _make_minimal_pdf("Persisted resume content")
    r = client.post(
        "/api/profiles/upload",
        files={"file": ("resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"name": "Persisted"},
    )
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["pdf_path"], "pdf_path should be set after upload"

    saved = Path(d["pdf_path"])
    assert saved.exists(), f"PDF should exist on disk at {saved}"
    assert saved.read_bytes() == pdf_bytes
    assert str(d["id"]) in str(saved), "path should be scoped to the profile id"


@pytest.mark.integration
def test_upload_profile_pdf_rejects_oversized_file(client: TestClient, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "8")
    from backend.app.config import get_settings
    get_settings.cache_clear()
    try:
        r = client.post(
            "/api/profiles/upload",
            files={"file": ("resume.pdf", io.BytesIO(b"%PDF-oversized"), "application/pdf")},
            data={"name": "Too Large"},
        )
    finally:
        get_settings.cache_clear()

    assert r.status_code == 413
    body = r.json()
    assert body["error"]["code"] == "payload_too_large"
    assert body["error"]["details"]["max_bytes"] == 8


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
def test_evaluate_defaults_to_marked_default_profile(client: TestClient):
    p1 = client.post("/api/profiles", json={"skills_text": "Short"}).json()["data"]
    long_text = "Long default profile skills text"
    p2 = client.post("/api/profiles", json={"skills_text": long_text}).json()["data"]
    client.put(f"/api/profiles/{p1['id']}", json={"is_default": True})

    r = client.post("/api/evaluate", json={"jd_text": "Backend role [[score=90]]"})
    assert r.status_code == 200
    assert f"Resume text length: {len('Short')} chars" in r.json()["data"]["explanation"]

    explicit = client.post(
        "/api/evaluate",
        json={"jd_text": "Another backend role [[score=90]]", "profile_id": p2["id"]},
    )
    assert explicit.status_code == 200
    assert f"Resume text length: {len(long_text)} chars" in explicit.json()["data"]["explanation"]


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
def test_legacy_get_profile_returns_latest_without_explicit_default(client: TestClient):
    client.post("/api/profiles", json={"skills_text": "First"})
    client.post("/api/profiles", json={"skills_text": "Second"})
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["data"]["skills_text"] == "Second"


@pytest.mark.integration
def test_legacy_get_profile_returns_explicit_default(client: TestClient):
    p1 = client.post("/api/profiles", json={"skills_text": "First"}).json()["data"]
    client.post("/api/profiles", json={"skills_text": "Second"})
    client.put(f"/api/profiles/{p1['id']}", json={"is_default": True})
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["data"]["skills_text"] == "First"


@pytest.mark.integration
def test_pdf_download_rejects_path_outside_storage(
    client: TestClient,
    db_engine,  # type: ignore[no-untyped-def]
    tmp_path,  # type: ignore[no-untyped-def]
):
    """Regression for #140 — if pdf_path ever points outside storage_dir
    (poisoned import, SQL injection, future bulk-edit feature), the download
    endpoint must refuse to serve the file rather than follow the path."""
    from sqlalchemy.orm import sessionmaker

    from backend.app.models.baseline_profile import BaselineProfile

    pdf_bytes = _make_minimal_pdf("Path traversal test")
    r = client.post(
        "/api/profiles/upload",
        files={"file": ("resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"name": "Traversal"},
    )
    profile_id = r.json()["data"]["id"]

    # Create a file outside storage_dir and point pdf_path at it.
    outside = tmp_path / "escape.pdf"
    outside.write_bytes(b"%PDF-attacker")

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        profile = db.get(BaselineProfile, profile_id)
        assert profile is not None
        profile.pdf_path = str(outside)
        db.commit()

    download = client.get(f"/api/profiles/{profile_id}/pdf")
    assert download.status_code == 404
    assert download.json()["error"]["code"] == "not_found"


@pytest.mark.integration
def test_debug_endpoint_does_not_leak_credential_presence(
    client: TestClient,
    monkeypatch,
):
    """Regression for #140 — the dev debug endpoint must not confirm
    whether OAuth token / API key env vars are set."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "secret-value")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-value")

    r = client.get("/api/debug/claude-cli-ping")
    assert r.status_code == 200
    payload = r.json()["data"]
    assert "oauth_token_set" not in payload
    assert "anthropic_api_key_set" not in payload
