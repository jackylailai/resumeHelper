"""T060: Second upload with resume_id creates version_number=2.

US2 integration test — RED until T070-T071 are fully verified.
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
def test_second_upload_creates_version_two(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """Upload v1 (no resume_id) then v2 (with resume_id) → version_number increments to 2."""
    r1 = _upload(client, minimal_pdf_bytes, sample_jd)
    assert r1.status_code in (200, 202)

    resumes = client.get("/api/resumes").json()["data"]
    assert len(resumes) >= 1
    resume_id = resumes[0]["id"]

    r2 = _upload(client, minimal_pdf_bytes, "Different JD: looking for a backend engineer.", resume_id)
    assert r2.status_code in (200, 202)

    versions_resp = client.get(f"/api/resumes/{resume_id}/versions")
    assert versions_resp.status_code == 200
    versions = versions_resp.json()["data"]

    assert len(versions) == 2
    numbers = sorted(v["version_number"] for v in versions)
    assert numbers == [1, 2]


@pytest.mark.integration
def test_previous_version_still_retrievable(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """After v2 upload, version_number=1 is still present in history."""
    r1 = _upload(client, minimal_pdf_bytes, sample_jd)
    assert r1.status_code in (200, 202)

    resume_id = client.get("/api/resumes").json()["data"][0]["id"]

    _upload(client, minimal_pdf_bytes, "Second JD text.", resume_id)

    versions = client.get(f"/api/resumes/{resume_id}/versions").json()["data"]
    version_numbers = [v["version_number"] for v in versions]
    assert 1 in version_numbers
    assert 2 in version_numbers


@pytest.mark.integration
def test_unknown_resume_id_returns_404(client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes):
    """Sending a non-existent resume_id returns 404 (not 500)."""
    r = _upload(
        client,
        minimal_pdf_bytes,
        sample_jd,
        resume_id="00000000-0000-0000-0000-000000000000",
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
