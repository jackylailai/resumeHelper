from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.models.llm_audit_log import LLMAuditLog
from backend.app.services.llm import LLMInvalidOutputError


@pytest.mark.integration
def test_evaluate_and_tailor_write_success_audit_logs(
    client: TestClient,
    db_engine,  # type: ignore[no-untyped-def]
) -> None:
    client.post("/api/profile", json={"skills_text": "Python, FastAPI, PostgreSQL"})

    response = client.post(
        "/api/evaluate",
        json={"jd_text": "Backend platform role with APIs and observability."},
    )

    assert response.status_code == 200
    request_id = response.json()["meta"]["request_id"]
    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        rows = db.query(LLMAuditLog).all()

    assert {row.workflow_step for row in rows} == {"evaluate", "tailor"}
    by_step = {row.workflow_step: row for row in rows}
    evaluate_log = by_step["evaluate"]
    tailor_log = by_step["tailor"]
    assert evaluate_log.status == "succeeded"
    assert evaluate_log.backend == "fake"
    assert evaluate_log.model == "fake"
    assert evaluate_log.request_id == request_id
    assert evaluate_log.input_hash
    assert evaluate_log.output_hash
    assert evaluate_log.token_count_input == 100
    assert evaluate_log.token_count_output == 50
    assert evaluate_log.job_analysis_id is not None

    assert tailor_log.status == "succeeded"
    assert tailor_log.request_id == request_id
    assert tailor_log.input_hash
    assert tailor_log.output_hash
    assert tailor_log.token_count_input == 120
    assert tailor_log.token_count_output == 80
    assert tailor_log.job_analysis_id == evaluate_log.job_analysis_id
    assert tailor_log.generated_resume_id is not None


@pytest.mark.integration
def test_cached_evaluate_does_not_write_second_llm_audit_log(
    client: TestClient,
    db_engine,  # type: ignore[no-untyped-def]
) -> None:
    client.post("/api/profile", json={"skills_text": "Python, FastAPI"})
    body = {"jd_text": "Python API role. [[score=92]]"}

    first = client.post("/api/evaluate", json=body)
    second = client.post("/api/evaluate", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["meta"]["cached"] is True

    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        rows = db.query(LLMAuditLog).all()

    assert len(rows) == 1
    assert rows[0].workflow_step == "evaluate"
    assert rows[0].status == "succeeded"


@pytest.mark.integration
def test_failed_evaluate_writes_failed_audit_log(
    client: TestClient,
    db_engine,  # type: ignore[no-untyped-def]
) -> None:
    client.post("/api/profile", json={"skills_text": "Python"})

    class _InvalidOutputLLM:
        def evaluate(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise LLMInvalidOutputError("score out of range")

    client.app.state.llm_client = _InvalidOutputLLM()

    response = client.post("/api/evaluate", json={"jd_text": "Different JD"})

    assert response.status_code == 502
    Session = sessionmaker(bind=db_engine)
    with Session() as db:
        rows = db.query(LLMAuditLog).all()

    assert len(rows) == 1
    row = rows[0]
    assert row.workflow_step == "evaluate"
    assert row.status == "failed"
    assert row.error_code == "llm_invalid_output"
    assert row.error_message == "LLMInvalidOutputError"
    assert row.input_hash
    assert row.output_hash is None
