from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.services.job_queue import (
    AI_JOB_KIND_EVALUATE,
    AI_JOB_KIND_TAILOR,
    AI_JOB_STATUS_SUCCEEDED,
)
from backend.app.services.llm.fake import FakeLLMClient
from backend.app.workers.job_queue import run_job_queue_once

_JD = "Python API role with FastAPI, PostgreSQL, and background job orchestration."


def _create_profile(client: TestClient) -> int:
    response = client.post(
        "/api/profile",
        json={"skills_text": "Python, FastAPI, PostgreSQL", "is_default": True},
    )
    assert response.status_code == 200
    return int(response.json()["data"]["id"])


@pytest.mark.integration
def test_create_async_evaluate_job_returns_accepted(client: TestClient) -> None:
    profile_id = _create_profile(client)

    response = client.post("/api/evaluate/jobs", json={"jd_text": _JD})

    assert response.status_code == 202
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["created"] is True
    job = body["data"]
    assert job["kind"] == "evaluate"
    assert job["status"] == "queued"
    assert job["profile_id"] == profile_id
    assert job["progress_current"] == 0
    assert job["progress_total"] == 1
    assert job["input_payload"]["jd_text"] == _JD
    assert job["input_payload"]["profile_id"] == profile_id
    assert job["input_payload"]["prompt_version"]
    assert job["input_payload"]["tailor_prompt_version"]

    fetched = client.get(f"/api/jobs/{job['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == job["id"]


@pytest.mark.integration
def test_async_evaluate_job_reuses_existing_active_job(client: TestClient) -> None:
    _create_profile(client)
    body = {"jd_text": _JD}

    first = client.post("/api/evaluate/jobs", json=body)
    second = client.post("/api/evaluate/jobs", json=body)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert second.json()["meta"]["created"] is False


@pytest.mark.integration
def test_async_evaluate_worker_succeeds_and_queues_tailoring(client: TestClient) -> None:
    client.app.state.llm_client = FakeLLMClient(default_score=72)  # type: ignore[union-attr]
    _create_profile(client)
    queued = client.post("/api/evaluate/jobs", json={"jd_text": _JD})
    assert queued.status_code == 202
    ai_job_id = queued.json()["data"]["id"]

    worker_result = run_job_queue_once(
        llm=client.app.state.llm_client,  # type: ignore[union-attr]
        session_factory=client.app.state.session_factory,  # type: ignore[union-attr]
        kind=AI_JOB_KIND_EVALUATE,
    )

    assert worker_result is not None
    assert worker_result.status == AI_JOB_STATUS_SUCCEEDED
    assert worker_result.result is not None
    assert worker_result.result["cached"] is False
    evaluation = worker_result.result["evaluation"]
    assert evaluation["score"] == 72
    assert evaluation["status"] == "needs_tailoring"
    assert evaluation["action"] == "tailoring"
    assert evaluation["tailoring_job_id"]
    assert evaluation["tailoring_status"] == "queued"

    fetched = client.get(f"/api/jobs/{ai_job_id}")
    assert fetched.status_code == 200
    job = fetched.json()["data"]
    assert job["status"] == "succeeded"
    assert job["progress_current"] == 1
    assert job["job_analysis_id"] == worker_result.result["job_analysis_id"]
    assert job["result_payload"]["evaluation"]["score"] == 72
    assert job["result_payload"]["tailoring_job_id"] == evaluation["tailoring_job_id"]

    tailoring_result = run_job_queue_once(
        llm=client.app.state.llm_client,  # type: ignore[union-attr]
        session_factory=client.app.state.session_factory,  # type: ignore[union-attr]
        kind=AI_JOB_KIND_TAILOR,
    )
    assert tailoring_result is not None
    assert tailoring_result.status == AI_JOB_STATUS_SUCCEEDED


@pytest.mark.integration
def test_evaluate_async_query_alias_returns_job(client: TestClient) -> None:
    _create_profile(client)

    response = client.post("/api/evaluate?async=true", json={"jd_text": _JD})

    assert response.status_code == 202
    assert response.json()["data"]["kind"] == "evaluate"
    assert response.json()["data"]["status"] == "queued"
