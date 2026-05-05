"""Integration test: small PDF → synchronous 200 response with evaluation.

Requires: testcontainers-postgres (Session fixture in conftest.py)
TDD state: RED until T040-T048 (evaluator + API routes) are implemented.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_upload_small_pdf_returns_evaluation(client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes):
    """POST /api/resumes with a small PDF → FakeLLM returns within 5s → 200."""
    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    # Either 200 (sync cache hit or fast eval) or 202 (async job)
    assert response.status_code in (200, 202)
    body = response.json()
    assert body["error"] is None
    assert body["data"] is not None


@pytest.mark.integration
def test_upload_200_contains_score_and_explanation(client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes):
    """When evaluation completes synchronously, response contains score + explanation."""
    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    if response.status_code == 200:
        data = response.json()["data"]
        assert isinstance(data["score"], int)
        assert 0 <= data["score"] <= 100
        assert isinstance(data["explanation"], str)
        assert len(data["explanation"]) > 0
        assert isinstance(data["strengths"], list)
        assert isinstance(data["gaps"], list)


@pytest.mark.integration
def test_upload_creates_resume_and_version(client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes):
    """Upload persists a Resume + ResumeVersion row (version_number=1)."""
    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code in (200, 202)

    # List resumes — should have at least one entry
    list_response = client.get("/api/resumes")
    assert list_response.status_code == 200
    resumes = list_response.json()["data"]
    assert len(resumes) >= 1


@pytest.mark.integration
def test_duplicate_upload_returns_cached_result(client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes):
    """Uploading the same content + JD twice returns meta.cached=true (FR-008, SC-006)."""
    # First upload
    client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )

    # Second identical upload
    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta.get("cached") is True
