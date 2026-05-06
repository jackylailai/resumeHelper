from __future__ import annotations
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import (
    JobAnalysis,
    STATUS_READY_TO_SUBMIT,
    STATUS_NEEDS_TAILORING,
    STATUS_SKIP,
)
from backend.app.schemas.evaluate import (
    BulkEvaluateIn,
    BulkEvaluateOut,
    BulkEvaluateResult,
    CallbackIn,
    EvaluateIn,
    EvaluateOut,
    GeneratedResumeOut,
    HistoryDetailOut,
    HistoryItemOut,
    SubmittableResumeOut,
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
    background_tasks: BackgroundTasks,
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

    # Determine three-tier action message
    status = job.status or STATUS_SKIP
    if status == STATUS_READY_TO_SUBMIT:
        message = f"Score {job.score}: Excellent match. Resume is ready to submit."
        action = "none"
    elif status == STATUS_NEEDS_TAILORING:
        message = f"Score {job.score}: Good match. Tailoring resume in background."
        action = "tailoring"
    else:
        message = f"Score {job.score}: Low match. Skipping this job. {job.skip_reason or ''}"
        action = "skip"

    # For needs_tailoring, trigger background tailoring (only on fresh evaluations)
    if status == STATUS_NEEDS_TAILORING and not cached:
        from backend.app.workers.tailor import run_tailoring
        # Use test-injected session factory if present, else default
        session_factory = getattr(request.app.state, "session_factory", None)
        background_tasks.add_task(
            run_tailoring,
            job_analysis_id=job.id,
            llm=llm,
            prompt_version=settings.llm_prompt_version,
            session_factory=session_factory,
        )
        logger.info("tailor_task_queued job_id=%s score=%s", job.id, job.score)

    out = EvaluateOut(
        job_analysis_id=job.id,
        score=job.score or 0,
        explanation=job.explanation or "",
        strengths=job.strengths or [],
        gaps=job.gaps or [],
        threshold_met=job.threshold_met,
        status=status,
        message=message,
        action=action,
    )

    return success(
        out.model_dump(mode="json"),
        cached=cached,
    )


@router.post("/evaluate/bulk")
def bulk_evaluate(
    body: BulkEvaluateIn,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Evaluate multiple JDs in one request. Deduplicates by content hash."""
    settings = get_settings()
    llm = _get_llm(request)
    results: list[BulkEvaluateResult] = []
    new_count = 0
    cached_count = 0

    for jd_text in body.jd_texts:
        try:
            job, cached = evaluate_jd(
                db, jd_text, llm,
                prompt_version=settings.llm_prompt_version,
                threshold=settings.resume_gen_threshold,
            )
        except LookupError as exc:
            return error("not_found", str(exc), status_code=404)

        if cached:
            cached_count += 1
        else:
            new_count += 1
            if job.status == STATUS_NEEDS_TAILORING:
                from backend.app.workers.tailor import run_tailoring
                session_factory = getattr(request.app.state, "session_factory", None)
                background_tasks.add_task(
                    run_tailoring,
                    job_analysis_id=job.id,
                    llm=llm,
                    prompt_version=settings.llm_prompt_version,
                    session_factory=session_factory,
                )

        results.append(BulkEvaluateResult(
            job_analysis_id=job.id,
            jd_snippet=job.jd_snippet,
            score=job.score or 0,
            status=job.status or STATUS_SKIP,
            cached=cached,
        ))

    out = BulkEvaluateOut(
        total=len(results),
        new=new_count,
        cached=cached_count,
        results=results,
    )
    return success(out.model_dump(mode="json"))


@router.post("/callback")
def n8n_callback(body: CallbackIn, db: Session = Depends(get_db)) -> JSONResponse:
    """Callback endpoint — accepts external tailoring results (e.g. from n8n or other pipeline)."""
    job = db.get(JobAnalysis, body.job_analysis_id)
    if job is None:
        return error("not_found", f"job_analysis {body.job_analysis_id} not found", status_code=404)

    resume = GeneratedResume(
        job_analysis_id=body.job_analysis_id,
        resume_text=body.resume_text,
        pdf_url=body.pdf_url,
        prompt_version=body.prompt_version,
    )
    db.add(resume)

    # Mark as submittable when a resume is delivered via callback
    job.can_submit = True
    db.commit()

    return success({"id": str(resume.id)})


@router.get("/history")
def list_history(db: Session = Depends(get_db)) -> JSONResponse:
    """Return all job analyses, optionally grouped by status."""
    jobs = db.query(JobAnalysis).order_by(JobAnalysis.created_at.desc()).limit(100).all()
    items = [HistoryItemOut.model_validate(j).model_dump(mode="json") for j in jobs]

    # Group by status for convenience
    grouped: dict[str, list] = {
        STATUS_READY_TO_SUBMIT: [],
        STATUS_NEEDS_TAILORING: [],
        STATUS_SKIP: [],
    }
    for item in items:
        s = item.get("status") or STATUS_SKIP
        if s in grouped:
            grouped[s].append(item)
        else:
            grouped[STATUS_SKIP].append(item)

    submittable_count = sum(1 for j in jobs if j.can_submit)

    return success(
        items,
        grouped=grouped,
        total=len(items),
        submittable_count=submittable_count,
    )


@router.get("/submittable")
def list_submittable(db: Session = Depends(get_db)) -> JSONResponse:
    """Return all job analyses where can_submit=True, with their latest generated resume."""
    jobs = (
        db.query(JobAnalysis)
        .filter(JobAnalysis.can_submit.is_(True))
        .order_by(JobAnalysis.created_at.desc())
        .all()
    )

    resumes = []
    for job in jobs:
        item = SubmittableResumeOut.model_validate(job).model_dump(mode="json")
        # Attach the most recent generated resume if any
        latest_resume = (
            db.query(GeneratedResume)
            .filter(GeneratedResume.job_analysis_id == job.id)
            .order_by(GeneratedResume.created_at.desc())
            .first()
        )
        if latest_resume:
            item["pdf_url"] = latest_resume.pdf_url
            item["resume_id"] = str(latest_resume.id)
        else:
            item["pdf_url"] = None
            item["resume_id"] = None
        resumes.append(item)

    return success(resumes, count=len(resumes))


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
