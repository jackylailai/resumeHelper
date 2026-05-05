"""T062: Identical content + JD → meta.cached=true; no new evaluation row.

US2 integration test — RED until cache logic and meta.cached flag are verified.
"""

from __future__ import annotations

import time

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


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> str:
    """Poll GET /api/jobs/{id} until terminal status; return final status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        status = resp.json()["data"]["status"]
        if status in ("succeeded", "failed"):
            return status
        time.sleep(0.2)
    return "timeout"


@pytest.mark.integration
def test_second_upload_same_content_and_jd_returns_cached(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """Uploading identical file + JD twice → second response has meta.cached=true."""
    r1 = _upload(client, minimal_pdf_bytes, sample_jd)
    assert r1.status_code in (200, 202)
    if r1.status_code == 202:
        status = _wait_for_job(client, r1.json()["data"]["id"])
        assert status == "succeeded", "First evaluation did not succeed"

    r2 = _upload(client, minimal_pdf_bytes, sample_jd)
    assert r2.status_code == 200
    assert r2.json()["meta"].get("cached") is True


@pytest.mark.integration
def test_cached_response_contains_score(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """Cache-hit response still includes score and explanation in data."""
    r1 = _upload(client, minimal_pdf_bytes, sample_jd)
    if r1.status_code == 202:
        _wait_for_job(client, r1.json()["data"]["id"])

    r2 = _upload(client, minimal_pdf_bytes, sample_jd)
    assert r2.status_code == 200
    data = r2.json()["data"]
    assert isinstance(data["score"], int)
    assert 0 <= data["score"] <= 100
    assert data["explanation"]


@pytest.mark.integration
def test_different_jd_not_cached(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """Same file but different JD must NOT return meta.cached (different cache_key)."""
    r1 = _upload(client, minimal_pdf_bytes, sample_jd)
    if r1.status_code == 202:
        _wait_for_job(client, r1.json()["data"]["id"])

    r2 = _upload(client, minimal_pdf_bytes, "Totally different job: nurse practitioner.")
    # May be 202 (new async eval) or 200 without cached flag
    if r2.status_code == 200:
        assert r2.json()["meta"].get("cached") is not True
    else:
        assert r2.status_code == 202


@pytest.mark.integration
def test_cache_hit_is_fast(client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes):
    """Cache hit must complete in under 1 second (SC-006)."""
    r1 = _upload(client, minimal_pdf_bytes, sample_jd)
    if r1.status_code == 202:
        _wait_for_job(client, r1.json()["data"]["id"])

    start = time.time()
    r2 = _upload(client, minimal_pdf_bytes, sample_jd)
    elapsed = time.time() - start

    assert r2.status_code == 200
    assert r2.json()["meta"].get("cached") is True
    assert elapsed < 1.0, f"Cache hit took {elapsed:.2f}s (> 1s SLA)"
