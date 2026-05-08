"""Integration tests: upload rejection scenarios (FR-001, FR-002, FR-010).

TDD state: RED until T043 (POST /api/resumes validation) is implemented.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_unsupported_format_returns_415(client: TestClient, sample_jd: str):
    """Non-PDF/DOCX file → 415 with error code unsupported_format (FR-001)."""
    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.txt", b"plain text resume", "text/plain")},
    )
    assert response.status_code == 415
    body = response.json()
    assert body["error"]["code"] == "unsupported_format"


@pytest.mark.integration
def test_oversized_file_returns_413(client: TestClient, sample_jd: str):
    """File > 10 MB → 413 with error code file_too_large (FR-002)."""
    big_file = b"%PDF-" + b"x" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("big.pdf", big_file, "application/pdf")},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "file_too_large"


@pytest.mark.integration
def test_no_extractable_text_returns_422(client: TestClient, sample_jd: str):
    """PDF with no parseable text → 422 with error code no_extractable_text (FR-010)."""
    empty_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("scanned.pdf", empty_pdf, "application/pdf")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "no_extractable_text"


@pytest.mark.integration
def test_missing_job_description_returns_422(client: TestClient, minimal_pdf_bytes: bytes):
    """Upload without job_description → 422 validation error."""
    response = client.post(
        "/api/resumes",
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_failed"
    assert body["meta"]["request_id"]
    assert response.headers["X-Request-ID"] == body["meta"]["request_id"]


@pytest.mark.integration
def test_magic_byte_mismatch_returns_415(client: TestClient, sample_jd: str):
    """File with .pdf extension but wrong magic bytes → 415."""
    fake_pdf = b"NOTPDF" + b"\x00" * 100
    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", fake_pdf, "application/pdf")},
    )
    assert response.status_code == 415
