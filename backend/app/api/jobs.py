from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.models.ai_job import AI_JOB_TERMINAL_STATUSES, AIJob
from backend.app.schemas.jobs import AIJobOut

router = APIRouter()

_TERMINAL_STATUSES = set(AI_JOB_TERMINAL_STATUSES)


def _job_out(job: AIJob) -> dict:
    return AIJobOut.model_validate(job).model_dump(mode="json")


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    job = db.get(AIJob, job_id)
    if job is None:
        return error("not_found", f"AI job {job_id} not found", status_code=404)
    return success(_job_out(job))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    job = db.get(AIJob, job_id)
    if job is None:
        return error("not_found", f"AI job {job_id} not found", status_code=404)

    if job.status in {"queued", "retry_wait"}:
        now = datetime.now(UTC)
        job.status = "cancelled"
        job.finished_at = now
        job.updated_at = now
    elif job.status == "running":
        job.updated_at = datetime.now(UTC)
        job.status = "cancel_requested"
    elif job.status not in _TERMINAL_STATUSES:
        # cancel_requested is already the durable signal workers should observe.
        pass
    else:
        return success(_job_out(job))

    db.commit()
    db.refresh(job)
    return success(_job_out(job))
