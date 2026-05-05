from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.schemas.evaluation import EvaluationOut

router = APIRouter()


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    from backend.app.models.resume_evaluation import ResumeEvaluation

    ev = db.get(ResumeEvaluation, evaluation_id)
    if ev is None:
        return error("not_found", f"Evaluation {evaluation_id} not found", status_code=404)

    return success(EvaluationOut.model_validate(ev).model_dump(mode="json"))
