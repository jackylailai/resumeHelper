"""Three-tier resume evaluation system — integration tests.

Tests the score-based routing:
- 85+: ready_to_submit
- 60-84: needs_tailoring (triggers background tailoring)
- <60:  skip
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.services.llm.fake import FakeLLMClient

_JD_HIGH = "Senior Python backend engineer with 5+ years FastAPI, PostgreSQL, cloud experience."
_JD_MID = "Python developer with REST API and SQL experience."
_JD_LOW = "Java Spring Boot developer with enterprise architecture experience."


def _run_tailor_worker_once(client: TestClient):
    from backend.app.services.job_queue import AI_JOB_KIND_TAILOR, AI_JOB_STATUS_SUCCEEDED
    from backend.app.workers.job_queue import run_job_queue_once

    result = run_job_queue_once(
        llm=client.app.state.llm_client,  # type: ignore[union-attr]
        session_factory=client.app.state.session_factory,  # type: ignore[union-attr]
        kind=AI_JOB_KIND_TAILOR,
    )
    assert result is not None
    assert result.status == AI_JOB_STATUS_SUCCEEDED
    return result


def _client_with_score(client: TestClient, app, score: int) -> None:
    """Set FakeLLMClient to return a fixed score."""
    app.state.llm_client = FakeLLMClient(default_score=score)


# ---------------------------------------------------------------------------
# High score (85+) → ready_to_submit
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_high_score_returns_ready_to_submit(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=90)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python, FastAPI, PostgreSQL"})
    r = client.post("/api/evaluate", json={"jd_text": _JD_HIGH})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "ready_to_submit"
    assert data["action"] == "none"
    assert data["score"] == 90


@pytest.mark.integration
def test_high_score_sets_can_submit_true(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=85)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD_HIGH})
    job_id = eval_resp.json()["data"]["job_analysis_id"]

    detail = client.get(f"/api/history/{job_id}").json()["data"]
    assert detail["can_submit"] is True
    assert detail["status"] == "ready_to_submit"


@pytest.mark.integration
def test_high_score_appears_in_submittable(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=88)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    client.post("/api/evaluate", json={"jd_text": _JD_HIGH})

    r = client.get("/api/submittable")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["count"] >= 1
    assert all(item["can_submit"] for item in data["data"])


# ---------------------------------------------------------------------------
# Mid score (60-84) → needs_tailoring
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_mid_score_returns_needs_tailoring(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=72)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python, REST APIs"})
    r = client.post("/api/evaluate", json={"jd_text": _JD_MID})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "needs_tailoring"
    assert data["action"] == "tailoring"
    assert data["score"] == 72
    assert data["tailoring_job_id"]
    assert data["tailoring_status"] == "queued"


@pytest.mark.integration
def test_mid_score_triggers_background_tailoring(client: TestClient):
    """After the durable worker runs, a tailored resume should exist in the DB."""
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=75)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python, REST APIs"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD_MID})
    data = eval_resp.json()["data"]
    job_id = data["job_analysis_id"]
    tailoring_job_id = data["tailoring_job_id"]

    assert tailoring_job_id
    detail = client.get(f"/api/history/{job_id}").json()["data"]
    assert detail["tailoring_job_id"] == tailoring_job_id
    assert detail["tailoring_status"] == "queued"
    assert detail["generated_resumes"] == []

    _run_tailor_worker_once(client)
    detail = client.get(f"/api/history/{job_id}").json()["data"]
    assert detail["tailoring_status"] == "succeeded"
    assert len(detail["generated_resumes"]) >= 1
    resume_text = detail["generated_resumes"][0]["resume_text"]
    assert len(resume_text) > 0


@pytest.mark.integration
def test_mid_score_can_submit_after_tailoring(client: TestClient):
    """After durable tailoring runs, can_submit should be True."""
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=80)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD_MID})
    job_id = eval_resp.json()["data"]["job_analysis_id"]

    _run_tailor_worker_once(client)
    detail = client.get(f"/api/history/{job_id}").json()["data"]
    assert detail["can_submit"] is True


@pytest.mark.integration
def test_mid_score_no_skip_reason(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=65)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD_MID})
    job_id = eval_resp.json()["data"]["job_analysis_id"]

    detail = client.get(f"/api/history/{job_id}").json()["data"]
    assert detail["skip_reason"] is None


# ---------------------------------------------------------------------------
# Low score (<60) → skip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_low_score_returns_skip(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=45)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    r = client.post("/api/evaluate", json={"jd_text": _JD_LOW})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "skip"
    assert data["action"] == "skip"
    assert data["score"] == 45


@pytest.mark.integration
def test_low_score_has_skip_reason(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=30)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD_LOW})
    job_id = eval_resp.json()["data"]["job_analysis_id"]

    detail = client.get(f"/api/history/{job_id}").json()["data"]
    assert detail["status"] == "skip"
    assert detail["skip_reason"] is not None
    assert len(detail["skip_reason"]) > 0


@pytest.mark.integration
def test_low_score_can_submit_is_false(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=20)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD_LOW})
    job_id = eval_resp.json()["data"]["job_analysis_id"]

    detail = client.get(f"/api/history/{job_id}").json()["data"]
    assert detail["can_submit"] is False


@pytest.mark.integration
def test_low_score_does_not_appear_in_submittable(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=10)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python"})
    client.post("/api/evaluate", json={"jd_text": _JD_LOW})

    r = client.get("/api/submittable")
    assert r.status_code == 200
    assert all(item["can_submit"] for item in r.json()["data"])


# ---------------------------------------------------------------------------
# History grouping
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_history_returns_grouped_by_status(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.post("/api/profile", json={"skills_text": "Python"})

    # Insert a high-score JD
    client.app.state.llm_client = FakeLLMClient(default_score=90)  # type: ignore[union-attr]
    client.post("/api/evaluate", json={"jd_text": _JD_HIGH})

    # Insert a low-score JD (different text to avoid cache)
    client.app.state.llm_client = FakeLLMClient(default_score=20)  # type: ignore[union-attr]
    client.post("/api/evaluate", json={"jd_text": _JD_LOW})

    r = client.get("/api/history")
    assert r.status_code == 200
    meta = r.json()["meta"]
    assert meta["total"] == 2
    assert len(meta["grouped"]["ready_to_submit"]) == 1
    assert len(meta["grouped"]["skip"]) == 1


# ---------------------------------------------------------------------------
# Submittable endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_submittable_empty_initially(client: TestClient):
    r = client.get("/api/submittable")
    assert r.status_code == 200
    assert r.json()["data"] == []
    assert r.json()["meta"]["count"] == 0


@pytest.mark.integration
def test_submittable_shows_pdf_url_from_callback(client: TestClient):
    from backend.app.services.llm.fake import FakeLLMClient

    client.app.state.llm_client = FakeLLMClient(default_score=90)  # type: ignore[union-attr]

    client.post("/api/profile", json={"skills_text": "Python"})
    eval_resp = client.post("/api/evaluate", json={"jd_text": _JD_HIGH})
    job_id = eval_resp.json()["data"]["job_analysis_id"]

    # Simulate external callback with pdf_url
    client.post(
        "/api/callback",
        json={
            "job_analysis_id": job_id,
            "resume_text": "# Tailored",
            "pdf_url": "file:///tmp/resume.pdf",
            "prompt_version": "v1",
        },
    )

    r = client.get("/api/submittable")
    matching = [item for item in r.json()["data"] if item["id"] == job_id]
    assert len(matching) == 1
    assert matching[0]["pdf_url"] == "file:///tmp/resume.pdf"
