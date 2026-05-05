"""T061: GET /api/resumes/{id}/versions returns reverse-chronological version list.

US2 integration test — RED until T071 is verified.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _upload(client: TestClient, pdf_bytes: bytes, jd: str, resume_id: str | None = None):
    data = {"job_description": jd}
    if resume_id is not None:
        data["resume_id"] = resume_id
    return client.post(
        "/api/resumes",
        data=data,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )


@pytest.mark.integration
def test_history_returns_versions_newest_first(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """GET /api/resumes/{id}/versions returns versions ordered newest→oldest."""
    r1 = _upload(client, minimal_pdf_bytes, sample_jd)
    assert r1.status_code in (200, 202)

    resume_id = client.get("/api/resumes").json()["data"][0]["id"]

    _upload(client, minimal_pdf_bytes, "Second JD content.", resume_id)

    resp = client.get(f"/api/resumes/{resume_id}/versions")
    assert resp.status_code == 200
    versions = resp.json()["data"]

    assert len(versions) == 2
    # Newest first — version_number descending
    assert versions[0]["version_number"] > versions[1]["version_number"]


@pytest.mark.integration
def test_history_version_has_required_fields(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """Each version entry has id, resume_id, version_number, file_format, uploaded_at."""
    _upload(client, minimal_pdf_bytes, sample_jd)

    resume_id = client.get("/api/resumes").json()["data"][0]["id"]

    resp = client.get(f"/api/resumes/{resume_id}/versions")
    assert resp.status_code == 200
    version = resp.json()["data"][0]

    for field in ("id", "resume_id", "version_number", "file_format", "file_size_bytes", "uploaded_at"):
        assert field in version, f"Missing field: {field}"
    assert version["resume_id"] == resume_id
    assert version["file_format"] == "pdf"
    assert isinstance(version["version_number"], int)


@pytest.mark.integration
def test_history_404_for_unknown_resume(client: TestClient):
    """GET /api/resumes/{id}/versions returns 404 for a non-existent resume."""
    resp = client.get("/api/resumes/00000000-0000-0000-0000-000000000000/versions")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.integration
def test_history_envelope_structure(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """Response follows {data, error, meta} envelope."""
    _upload(client, minimal_pdf_bytes, sample_jd)
    resume_id = client.get("/api/resumes").json()["data"][0]["id"]

    resp = client.get(f"/api/resumes/{resume_id}/versions")
    body = resp.json()
    assert "data" in body
    assert "error" in body
    assert "meta" in body
    assert body["error"] is None
    assert isinstance(body["data"], list)
