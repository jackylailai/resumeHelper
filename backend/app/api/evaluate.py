from __future__ import annotations
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import JobAnalysis
from backend.app.schemas.evaluate import (
    CallbackIn,
    EvaluateIn,
    EvaluateOut,
    GeneratedResumeOut,
    HistoryDetailOut,
    HistoryItemOut,
)
from backend.app.services.evaluator_v2 import evaluate_jd
from backend.app.services.llm import LLMClient

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_llm(request: Request) -> LLMClient:
    return request.app.state.llm_client  # type: ignore[no-any-return]


@router.post("/evaluate")
def evaluate(
    body: EvaluateIn,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    settings = get_settings()
    llm = _get_llm(request)
    try:
        job, cached = evaluate_jd(
            db, body.jd_text, llm,
            prompt_version=settings.llm_prompt_version,
            threshold=settings.resume_gen_threshold,
        )
    except LookupError as exc:
        return error("not_found", str(exc), status_code=404)

    out = EvaluateOut(
        job_analysis_id=job.id,
        score=job.score or 0,
        explanation=job.explanation or "",
        strengths=job.strengths or [],
        gaps=job.gaps or [],
        threshold_met=job.threshold_met,
    )

    if job.threshold_met and not cached:
        _trigger_n8n(job, settings)

    return success(
        out.model_dump(mode="json"),
        cached=cached,
    )


def _trigger_n8n(job: JobAnalysis, settings) -> None:  # type: ignore[no-untyped-def]
    n8n_url = getattr(settings, "n8n_webhook_url", None)
    if not n8n_url:
        logger.warning("n8n_webhook_url not set, skipping generation trigger")
        return
    try:
        httpx.post(n8n_url, json={
            "job_analysis_id": str(job.id),
            "jd_full_text": job.jd_full_text,
        }, timeout=5)
    except Exception as exc:
        logger.warning("n8n_trigger_failed: %s", exc)


@router.post("/callback")
def n8n_callback(body: CallbackIn, db: Session = Depends(get_db)) -> JSONResponse:
    job = db.get(JobAnalysis, body.job_analysis_id)
    if job is None:
        return error("not_found", f"job_analysis {body.job_analysis_id} not found", status_code=404)

    resume = GeneratedResume(
        job_analysis_id=body.job_analysis_id,
        resume_text=body.resume_text,
        prompt_version=body.prompt_version,
    )
    db.add(resume)
    db.commit()
    return success({"id": str(resume.id)})


@router.get("/history")
def list_history(db: Session = Depends(get_db)) -> JSONResponse:
    jobs = db.query(JobAnalysis).order_by(JobAnalysis.created_at.desc()).limit(100).all()
    return success([HistoryItemOut.model_validate(j).model_dump(mode="json") for j in jobs])


@router.get("/history/{job_id}")
def get_history_item(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    job = db.get(JobAnalysis, job_id)
    if job is None:
        return error("not_found", f"job_analysis {job_id} not found", status_code=404)

    resumes = (
        db.query(GeneratedResume)
        .filter(GeneratedResume.job_analysis_id == job_id)
        .order_by(GeneratedResume.created_at.desc())
        .all()
    )
    data = HistoryDetailOut.model_validate(job).model_dump(mode="json")
    data["generated_resumes"] = [
        GeneratedResumeOut.model_validate(r).model_dump(mode="json") for r in resumes
    ]
    return success(data)
