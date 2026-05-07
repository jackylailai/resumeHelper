from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.schemas.evaluation import JobOut

router = APIRouter()


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    from backend.app.models.evaluation_job import EvaluationJob

    job = db.get(EvaluationJob, job_id)
    if job is None:
        return error("not_found", f"Job {job_id} not found", status_code=404)

    return success(JobOut.model_validate(job).model_dump(mode="json"), status=job.status)
