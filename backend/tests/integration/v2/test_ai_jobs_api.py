from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.ai_job import AIJob
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import JobAnalysis
from backend.app.services.job_queue import claim_next_job, mark_job_failed
from backend.app.workers.tailor import TAILORING_STATUS_FAILED, run_tailoring


def _create_ai_job(db: Session, *, status: str = "queued") -> AIJob:
    analysis = JobAnalysis(
        jd_hash=f"job-api-{uuid.uuid4()}",
        jd_full_text="Backend platform role with durable background work.",
        threshold_met=False,
    )
    db.add(analysis)
    db.flush()
    job = AIJob(
        kind="tailor",
        status=status,
        priority=5,
        job_analysis_id=analysis.id,
        request_id="req-test",
        input_payload={"job_analysis_id": str(analysis.id)},
        progress_current=1,
        progress_total=3,
    )
    db.add(job)
    db.commit()
    return job


@pytest.mark.integration
def test_get_ai_job_returns_envelope(
    client: TestClient,
    db_session: Session,
) -> None:
    job = _create_ai_job(db_session)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["id"] == str(job.id)
    assert body["data"]["kind"] == "tailor"
    assert body["data"]["status"] == "queued"
    assert body["data"]["priority"] == 5
    assert body["data"]["request_id"] == "req-test"
    assert body["data"]["input_payload"] == {"job_analysis_id": str(job.job_analysis_id)}
    assert body["data"]["progress_current"] == 1
    assert body["data"]["progress_total"] == 3
    assert body["meta"]["request_id"]


@pytest.mark.integration
def test_cancel_ai_job_status_transitions(
    client: TestClient,
    db_session: Session,
) -> None:
    expected = {
        "queued": "cancelled",
        "retry_wait": "cancelled",
        "running": "cancel_requested",
        "cancel_requested": "cancel_requested",
        "cancelled": "cancelled",
        "succeeded": "succeeded",
        "failed": "failed",
    }
    jobs = {status: _create_ai_job(db_session, status=status) for status in expected}

    for initial_status, expected_status in expected.items():
        response = client.post(f"/api/jobs/{jobs[initial_status].id}/cancel")

        assert response.status_code == 200
        body = response.json()
        assert body["error"] is None
        assert body["data"]["status"] == expected_status
        if initial_status in {"queued", "retry_wait"}:
            assert body["data"]["finished_at"] is not None


@pytest.mark.integration
def test_cancel_requested_ai_job_is_not_claimable(db_session: Session) -> None:
    job = _create_ai_job(db_session, status="cancel_requested")

    claimed = claim_next_job(db_session, kind="tailor")

    assert claimed is None
    db_session.refresh(job)
    assert job.status == "cancel_requested"


@pytest.mark.integration
def test_running_cancel_signal_prevents_tailoring_persist(
    client: TestClient,
    db_session: Session,
) -> None:
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    response = client.post(
        "/api/evaluate",
        json={"jd_text": "Python API role. [[score=72]]"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    job_analysis_id = uuid.UUID(data["job_analysis_id"])
    ai_job_id = uuid.UUID(data["tailoring_job_id"])

    ai_job = db_session.get(AIJob, ai_job_id)
    assert ai_job is not None
    ai_job.status = "cancel_requested"
    db_session.commit()

    result = run_tailoring(
        job_analysis_id=job_analysis_id,
        llm=client.app.state.llm_client,  # type: ignore[union-attr]
        session_factory=client.app.state.session_factory,  # type: ignore[union-attr]
        cancel_requested=lambda: True,
    )
    assert result.status == TAILORING_STATUS_FAILED
    assert result.error_code == "job_cancelled"

    ref = mark_job_failed(
        db_session,
        job_id=ai_job_id,
        error_code=result.error_code or "job_cancelled",
        error_message=result.error_message or "tailoring job was cancelled",
    )
    assert ref is not None
    assert ref.status == "cancelled"

    db_session.expire_all()
    analysis = db_session.get(JobAnalysis, job_analysis_id)
    assert analysis is not None
    assert analysis.can_submit is False
    assert (
        db_session.query(GeneratedResume)
        .filter(GeneratedResume.job_analysis_id == job_analysis_id)
        .count()
        == 0
    )


@pytest.mark.integration
def test_ai_job_unknown_id_returns_404(client: TestClient) -> None:
    missing_id = uuid.uuid4()

    response = client.get(f"/api/jobs/{missing_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
