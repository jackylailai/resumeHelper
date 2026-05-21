"""POST /api/callback stores generated resumes from external pipelines."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

_JD = "Backend engineer with Python skills needed."


@pytest.mark.integration
def test_callback_stores_generated_resume(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD})
    job_id = eval_resp.json()["data"]["job_analysis_id"]

    r = client.post(
        "/api/callback",
        json={
            "job_analysis_id": job_id,
            "resume_text": "# Tailored Resume\n\n## Skills\nPython, FastAPI",
            "prompt_version": "v1",
        },
    )
    assert r.status_code == 200
    assert r.json()["error"] is None


@pytest.mark.integration
def test_callback_appears_in_history_detail(client: TestClient):
    client.post("/api/profile", json={"skills_text": "Python"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD})
    job_id = eval_resp.json()["data"]["job_analysis_id"]

    client.post(
        "/api/callback",
        json={
            "job_analysis_id": job_id,
            "resume_text": "# My Resume",
            "prompt_version": "v1",
        },
    )

    item_id = client.get("/api/history").json()["data"][0]["id"]
    detail = client.get(f"/api/history/{item_id}").json()["data"]
    # At least 1 resume: the explicit callback. Background tailoring may also have fired.
    assert len(detail["generated_resumes"]) >= 1
    resume_texts = [r["resume_text"] for r in detail["generated_resumes"]]
    assert "# My Resume" in resume_texts


@pytest.mark.integration
def test_callback_unknown_job_returns_404(client: TestClient):
    r = client.post(
        "/api/callback",
        json={
            "job_analysis_id": "00000000-0000-0000-0000-000000000000",
            "resume_text": "text",
            "prompt_version": "v1",
        },
    )
    assert r.status_code == 404
