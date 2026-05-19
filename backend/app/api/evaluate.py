# ruff: noqa: I001
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

import backend.app.schemas.evaluate as schemas
from backend.app.api.envelope import error, success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.baseline_profile import BaselineProfile
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import (
    JobAnalysis,
    STATUS_NEEDS_TAILORING,
    STATUS_READY_TO_SUBMIT,
    STATUS_SKIP,
)
from backend.app.services.batch_evaluator import (
    evaluate_listing_ids,
    evaluate_pending_listings,
)
from backend.app.services.ai_guardrails import (
    EVALUATE_WORKFLOW,
    EVALUATE_LISTINGS_WORKFLOW,
    QuotaExceededError,
    enforce_batch_guardrails,
    estimate_evaluation_batch,
)
from backend.app.services.evaluator_v2 import (
    evaluate_jd,
    get_default_profile as get_baseline,
)
from backend.app.services.llm import (
    LLMClient,
    LLMInvalidOutputError,
    LLMUnavailableError,
)
from backend.app.services.pdf import (
    generated_resume_pdf_path,
    write_generated_resume_pdf,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_llm(request: Request) -> LLMClient:
    return request.app.state.llm_client  # type: ignore[no-any-return]


def _jd_length_error(
    jd_text: str,
    max_chars: int,
    *,
    index: int | None = None,
    listing_id: uuid.UUID | None = None,
) -> JSONResponse | None:
    actual_chars = len(jd_text)
    if max_chars <= 0 or actual_chars <= max_chars:
        return None

    details: dict[str, int | str] = {
        "actual_chars": actual_chars,
        "max_chars": max_chars,
    }
    if index is not None:
        details["index"] = index
    if listing_id is not None:
        details["listing_id"] = str(listing_id)

    return error(
        "jd_too_long",
        f"Job description exceeds the {max_chars} character limit.",
        status_code=400,
        details=details,
    )


def _queue_tailoring_if_needed(
    job: JobAnalysis,
    cached: bool,
    background_tasks: BackgroundTasks,
    request: Request,
    llm: LLMClient,
    prompt_version: str,
) -> None:
    if cached or job.status != STATUS_NEEDS_TAILORING:
        return

    # Lazy import avoids circular dependency: tailor -> db -> main -> evaluate -> tailor
    from backend.app.workers.tailor import run_tailoring

    session_factory = getattr(request.app.state, "session_factory", None)
    background_tasks.add_task(
        run_tailoring,
        job_analysis_id=job.id,
        llm=llm,
        prompt_version=prompt_version,
        session_factory=session_factory,
        request_id=getattr(request.state, "request_id", None),
    )
    logger.info("tailor_task_queued job_id=%s score=%s", job.id, job.score)


def _quota_error(exc: QuotaExceededError) -> JSONResponse:
    result = exc.result
    return error(
        result.code or "ai_quota_blocked",
        result.message or "AI quota guard blocked this request.",
        status_code=429,
        details=result.details,
    )


@router.post("/evaluate")
def evaluate(
    body: schemas.EvaluateIn,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    settings = get_settings()
    length_error = _jd_length_error(body.jd_text, settings.max_jd_chars)
    if length_error is not None:
        return length_error

    llm = _get_llm(request)
    try:
        job, cached = evaluate_jd(
            db, body.jd_text, llm,
            prompt_version=settings.llm_prompt_version,
            threshold=settings.resume_gen_threshold,
            profile_id=body.profile_id,
        )
    except LookupError as exc:
        return error("not_found", str(exc), status_code=404)
    except LLMUnavailableError as exc:
        return error("llm_unavailable", str(exc), status_code=503)
    except LLMInvalidOutputError as exc:
        return error("llm_invalid_output", str(exc), status_code=502)

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
        # Lazy import avoids circular dependency: tailor → db → main → evaluate → tailor
        from backend.app.workers.tailor import run_tailoring
        # Use test-injected session factory if present, else default
        session_factory = getattr(request.app.state, "session_factory", None)
        background_tasks.add_task(
            run_tailoring,
            job_analysis_id=job.id,
            llm=llm,
            prompt_version=settings.llm_prompt_version,
            session_factory=session_factory,
            request_id=getattr(request.state, "request_id", None),
        )
        logger.info("tailor_task_queued job_id=%s score=%s", job.id, job.score)

    out = schemas.EvaluateOut(
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
    body: schemas.BulkEvaluateIn,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Evaluate multiple JDs in one request. Deduplicates by content hash."""
    # Check baseline exists before touching any JD — avoids partial DB writes on missing profile
    baseline = get_baseline(db)
    if baseline is None:
        return error("not_found", "baseline_profile not set", status_code=404)

    settings = get_settings()
    llm = _get_llm(request)
    results: list[schemas.BulkEvaluateResult] = []
    new_count = 0
    cached_count = 0

    for index, jd_text in enumerate(body.jd_texts):
        length_error = _jd_length_error(jd_text, settings.max_jd_chars, index=index)
        if length_error is not None:
            return length_error
    estimate = estimate_evaluation_batch(
        settings,
        workflow=EVALUATE_WORKFLOW,
        profile_text=baseline.skills_text,
        jd_texts=body.jd_texts,
    )
    try:
        enforce_batch_guardrails(
            settings,
            workflow=EVALUATE_WORKFLOW,
            estimate=estimate,
            max_items=settings.max_bulk_evaluate_items,
        )
    except QuotaExceededError as exc:
        return _quota_error(exc)

    for jd_text in body.jd_texts:
        try:
            job, cached = evaluate_jd(
                db, jd_text, llm,
                prompt_version=settings.llm_prompt_version,
                threshold=settings.resume_gen_threshold,
            )
        except LLMUnavailableError as exc:
            return error("llm_unavailable", str(exc), status_code=503)
        except LLMInvalidOutputError as exc:
            return error("llm_invalid_output", str(exc), status_code=502)

        if cached:
            cached_count += 1
        else:
            new_count += 1
            if job.status == STATUS_NEEDS_TAILORING:
                # Lazy import avoids circular dependency: tailor → db → main → evaluate → tailor
                from backend.app.workers.tailor import run_tailoring
                session_factory = getattr(request.app.state, "session_factory", None)
                background_tasks.add_task(
                    run_tailoring,
                    job_analysis_id=job.id,
                    llm=llm,
                    prompt_version=settings.llm_prompt_version,
                    session_factory=session_factory,
                    request_id=getattr(request.state, "request_id", None),
                )

        results.append(schemas.BulkEvaluateResult(
            job_analysis_id=job.id,
            jd_snippet=job.jd_snippet,
            score=job.score or 0,
            status=job.status or STATUS_SKIP,
            cached=cached,
        ))

    out = schemas.BulkEvaluateOut(
        total=len(results),
        new=new_count,
        cached=cached_count,
        estimated_input_tokens=estimate.estimated_input_tokens,
        estimated_output_tokens=estimate.estimated_output_tokens,
        estimated_total_tokens=estimate.estimated_total_tokens,
        estimated_cost_usd=estimate.estimated_cost_usd,
        results=results,
    )
    return success(out.model_dump(mode="json"))


@router.post("/evaluate/by-listings")
def evaluate_by_listings(
    body: schemas.EvaluateByListingsIn,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Evaluate stored scraper JDs by listing id and link results back to the rows."""
    settings = get_settings()
    llm = _get_llm(request)
    try:
        summary = evaluate_listing_ids(
            db,
            listing_ids=body.job_listing_ids,
            llm=llm,
            settings=settings,
            profile_id=body.profile_id,
            workflow=EVALUATE_LISTINGS_WORKFLOW,
            max_items=settings.max_evaluate_listing_items,
            on_evaluated=lambda job, cached: _queue_tailoring_if_needed(
                job,
                cached,
                background_tasks,
                request,
                llm,
                settings.llm_prompt_version,
            ),
        )
    except LookupError as exc:
        return error("not_found", str(exc), status_code=404)
    except QuotaExceededError as exc:
        return _quota_error(exc)

    out = schemas.EvaluateByListingsOut(
        total=summary.total,
        succeeded=summary.succeeded,
        failed=summary.failed,
        skipped=summary.skipped,
        blocked=summary.blocked,
        tailoring_blocked=summary.tailoring_blocked,
        estimated_input_tokens=summary.estimate.estimated_input_tokens
        if summary.estimate
        else None,
        estimated_output_tokens=summary.estimate.estimated_output_tokens
        if summary.estimate
        else None,
        estimated_total_tokens=summary.estimate.estimated_total_tokens
        if summary.estimate
        else None,
        estimated_cost_usd=summary.estimate.estimated_cost_usd
        if summary.estimate
        else None,
        warnings=summary.warnings,
        results=[
            schemas.EvaluateByListingsResult(
                listing_id=result.listing_id,
                job_analysis_id=result.job_analysis_id,
                score=result.score,
                status=result.status,  # type: ignore[arg-type]
                cached=result.cached,
                error=result.error,
            )
            for result in summary.results
        ],
    )
    return success(out.model_dump(mode="json"))


@router.post("/evaluate/pending-listings")
def evaluate_pending_scraped_listings(
    body: schemas.EvaluatePendingListingsIn,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    settings = get_settings()
    llm = _get_llm(request)
    try:
        summary = evaluate_pending_listings(
            db,
            llm=llm,
            settings=settings,
            profile_id=body.profile_id,
            source=body.source,
            limit=body.limit,
            workflow=EVALUATE_LISTINGS_WORKFLOW,
            max_items=settings.max_evaluate_pending_items,
            on_evaluated=lambda job, cached: _queue_tailoring_if_needed(
                job,
                cached,
                background_tasks,
                request,
                llm,
                settings.llm_prompt_version,
            ),
        )
    except LookupError as exc:
        return error("not_found", str(exc), status_code=404)
    except QuotaExceededError as exc:
        return _quota_error(exc)

    out = schemas.EvaluateByListingsOut(
        total=summary.total,
        succeeded=summary.succeeded,
        failed=summary.failed,
        skipped=summary.skipped,
        blocked=summary.blocked,
        tailoring_blocked=summary.tailoring_blocked,
        estimated_input_tokens=summary.estimate.estimated_input_tokens
        if summary.estimate
        else None,
        estimated_output_tokens=summary.estimate.estimated_output_tokens
        if summary.estimate
        else None,
        estimated_total_tokens=summary.estimate.estimated_total_tokens
        if summary.estimate
        else None,
        estimated_cost_usd=summary.estimate.estimated_cost_usd
        if summary.estimate
        else None,
        warnings=summary.warnings,
        results=[
            schemas.EvaluateByListingsResult(
                listing_id=result.listing_id,
                job_analysis_id=result.job_analysis_id,
                score=result.score,
                status=result.status,  # type: ignore[arg-type]
                cached=result.cached,
                error=result.error,
            )
            for result in summary.results
        ],
    )
    return success(out.model_dump(mode="json"))


@router.post("/callback")
def n8n_callback(body: schemas.CallbackIn, db: Session = Depends(get_db)) -> JSONResponse:
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
    db.flush()
    if not body.pdf_url:
        write_generated_resume_pdf(
            get_settings().storage_dir,
            resume.id,
            resume.resume_text,
        )
        resume.pdf_url = f"/api/generated-resumes/{resume.id}/pdf"

    # Mark as submittable when a resume is delivered via callback
    job.can_submit = True
    db.commit()

    return success({"id": str(resume.id)})


@router.get("/history")
def list_history(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> JSONResponse:
    """Return job analyses in reverse-chronological order, grouped by status."""
    jobs = db.query(JobAnalysis).order_by(JobAnalysis.created_at.desc()).limit(limit).all()
    items = [schemas.HistoryItemOut.model_validate(j).model_dump(mode="json") for j in jobs]

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
        limit=limit,
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
    if not jobs:
        return success([], count=0)

    # Fetch the latest generated resume per job in one query (DISTINCT ON)
    job_ids = [j.id for j in jobs]
    latest_resumes = (
        db.query(GeneratedResume)
        .filter(GeneratedResume.job_analysis_id.in_(job_ids))
        .order_by(
            GeneratedResume.job_analysis_id,
            GeneratedResume.created_at.desc(),
        )
        .distinct(GeneratedResume.job_analysis_id)
        .all()
    )
    resume_by_job = {r.job_analysis_id: r for r in latest_resumes}

    result = []
    for job in jobs:
        item = schemas.SubmittableResumeOut.model_validate(job).model_dump(mode="json")
        latest = resume_by_job.get(job.id)
        if latest:
            item["pdf_url"] = latest.pdf_url
            item["resume_id"] = str(latest.id)
            item["pdf_kind"] = "tailored"
        elif job.profile_id:
            # ready_to_submit cases don't run tailoring — fall back to the
            # baseline profile PDF so the UI always has something to download.
            item["pdf_url"] = f"/api/profiles/{job.profile_id}/pdf"
            item["resume_id"] = None
            item["pdf_kind"] = "baseline"
        else:
            item["pdf_url"] = None
            item["resume_id"] = None
            item["pdf_kind"] = None
        result.append(item)

    return success(result, count=len(result))


@router.get("/generated-resumes/{resume_id}/pdf", response_model=None)
def download_generated_resume_pdf(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse | JSONResponse:
    resume = db.get(GeneratedResume, resume_id)
    if resume is None:
        return error("not_found", f"generated_resume {resume_id} not found", status_code=404)

    settings = get_settings()
    path = generated_resume_pdf_path(settings.storage_dir, resume.id)
    if not path.exists():
        write_generated_resume_pdf(settings.storage_dir, resume.id, resume.resume_text)

    expected_url = f"/api/generated-resumes/{resume.id}/pdf"
    if resume.pdf_url != expected_url:
        resume.pdf_url = expected_url
    resume.exported_at = datetime.now(UTC)
    db.commit()

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"resume-{resume.id}.pdf",
    )


@router.post("/generated-resumes/{resume_id}/revisions")
def create_generated_resume_revision(
    resume_id: uuid.UUID,
    body: schemas.ResumeRevisionIn,
    db: Session = Depends(get_db),
) -> JSONResponse:
    source = db.get(GeneratedResume, resume_id)
    if source is None:
        return error("not_found", f"generated_resume {resume_id} not found", status_code=404)

    resume_text = body.resume_text.strip()
    if not resume_text:
        return error("invalid_resume_text", "resume_text must not be blank", status_code=422)

    revision = GeneratedResume(
        job_analysis_id=source.job_analysis_id,
        resume_text=resume_text,
        pdf_url=None,
        prompt_version="user-edited",
        revision_source="user_edited",
    )
    db.add(revision)
    db.flush()
    write_generated_resume_pdf(
        get_settings().storage_dir,
        revision.id,
        revision.resume_text,
    )
    revision.pdf_url = f"/api/generated-resumes/{revision.id}/pdf"

    job = db.get(JobAnalysis, source.job_analysis_id)
    if job is not None:
        job.can_submit = True

    db.commit()
    db.refresh(revision)
    return success(schemas.GeneratedResumeOut.model_validate(revision).model_dump(mode="json"))


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
    data = schemas.HistoryDetailOut.model_validate(job).model_dump(mode="json")
    if job.profile_id:
        profile = db.get(BaselineProfile, job.profile_id)
        data["baseline_profile_text"] = profile.skills_text if profile else None
    serialized_resumes = []
    for resume in resumes:
        item = schemas.GeneratedResumeOut.model_validate(resume).model_dump(mode="json")
        # Hydrate beautification URLs (the model itself only has DB fields).
        for b_idx, beautification in enumerate(resume.beautifications):
            item["beautifications"][b_idx]["html_url"] = (
                f"/api/beautifications/{beautification.id}/html"
            )
            item["beautifications"][b_idx]["pdf_url"] = (
                f"/api/beautifications/{beautification.id}/pdf"
            )
        serialized_resumes.append(item)
    data["generated_resumes"] = serialized_resumes
    return success(data)
