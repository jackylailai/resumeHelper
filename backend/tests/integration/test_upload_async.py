"""Integration test: slow evaluation → 202 job_id → poll to succeeded.

TDD state: RED until T042-T045 (worker + jobs endpoint) are implemented.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.app.services.llm.fake import FakeLLMClient
from backend.app.services.llm import EvaluationResult


@pytest.mark.integration
def test_slow_upload_returns_202_with_job_id(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes, fake_llm: FakeLLMClient
):
    """When FakeLLM is configured with a delay, upload returns 202 + job_id."""
    fake_llm._delay = 6.0  # simulate >5s evaluation

    response = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 202
    data = response.json()["data"]
    assert "id" in data
    assert data["status"] == "pending"

    fake_llm._delay = 0.0  # reset


@pytest.mark.integration
def test_job_poll_transitions_to_succeeded(
    client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes
):
    """After 202, polling GET /api/jobs/{job_id} eventually returns succeeded."""
    upload = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    if upload.status_code == 200:
        pytest.skip("Evaluation completed synchronously — async test not applicable")

    job_id = upload.json()["data"]["id"]

    # Poll up to 10 seconds
    deadline = time.time() + 10
    while time.time() < deadline:
        poll = client.get(f"/api/jobs/{job_id}")
        assert poll.status_code == 200
        status = poll.json()["data"]["status"]
        if status == "succeeded":
            eval_id = poll.json()["data"]["evaluation_id"]
            assert eval_id is not None
            return
        if status == "failed":
            pytest.fail(f"Job failed: {poll.json()['data'].get('failure_reason')}")
        time.sleep(0.5)

    pytest.fail("Job did not complete within 10 seconds")


@pytest.mark.integration
def test_succeeded_job_links_evaluation(client: TestClient, sample_jd: str, minimal_pdf_bytes: bytes):
    """Succeeded job's evaluation_id resolves via GET /api/evaluations/{id}."""
    upload = client.post(
        "/api/resumes",
        data={"job_description": sample_jd},
        files={"file": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
    )

    if upload.status_code == 200:
        eval_data = upload.json()["data"]
    else:
        job_id = upload.json()["data"]["id"]
        deadline = time.time() + 10
        eval_id = None
        while time.time() < deadline:
            poll = client.get(f"/api/jobs/{job_id}")
            if poll.json()["data"]["status"] == "succeeded":
                eval_id = poll.json()["data"]["evaluation_id"]
                break
            time.sleep(0.5)
        assert eval_id, "Job never succeeded"
        eval_resp = client.get(f"/api/evaluations/{eval_id}")
        assert eval_resp.status_code == 200
        eval_data = eval_resp.json()["data"]

    assert 0 <= eval_data["score"] <= 100
    assert eval_data["explanation"]
