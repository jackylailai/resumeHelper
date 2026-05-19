from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models.job_analysis import STATUS_NEEDS_TAILORING, STATUS_SKIP, JobAnalysis
from backend.app.models.job_listing import JobListing
from backend.app.services.ai_guardrails import (
    EVALUATE_LISTINGS_WORKFLOW,
    BatchEstimate,
    check_batch_guardrails,
    enforce_batch_guardrails,
    estimate_evaluation_batch,
    estimate_tailoring_batch,
)
from backend.app.services.evaluator_v2 import evaluate_jd, get_default_profile, get_profile
from backend.app.services.llm import LLMClient, LLMInvalidOutputError, LLMUnavailableError
from backend.app.services.llm.prompt_registry import (
    STEP_EVALUATE,
    prompt_version_for_step,
)


@dataclass
class ListingEvaluationResult:
    listing_id: uuid.UUID
    job_analysis_id: uuid.UUID | None = None
    score: int | None = None
    status: str | None = None
    cached: bool = False
    error: str | None = None


@dataclass
class ListingEvaluationSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    blocked: int = 0
    results: list[ListingEvaluationResult] = field(default_factory=list)
    tailoring_job_ids: list[uuid.UUID] = field(default_factory=list)
    tailoring_blocked: int = 0
    estimate: BatchEstimate | None = None
    warnings: list[dict[str, object]] = field(default_factory=list)


TailoringCallback = Callable[[JobAnalysis, bool], None]


def evaluate_listing_ids(
    db: Session,
    *,
    listing_ids: list[uuid.UUID],
    llm: LLMClient,
    settings: Settings,
    profile_id: int | None = None,
    on_evaluated: TailoringCallback | None = None,
    workflow: str = EVALUATE_LISTINGS_WORKFLOW,
    max_items: int | None = None,
) -> ListingEvaluationSummary:
    summary = ListingEvaluationSummary(total=len(listing_ids))
    profile = (
        get_profile(db, profile_id)
        if profile_id is not None
        else get_default_profile(db)
    )
    if profile is None:
        raise LookupError("baseline_profile not set")
    resolved_profile_id = profile.id
    listings_by_id = {
        listing.id: listing
        for listing in db.query(JobListing)
        .filter(JobListing.id.in_(listing_ids))
        .all()
    }
    guard_texts = [
        listing.description.strip()
        for listing_id in listing_ids
        if (listing := listings_by_id.get(listing_id)) is not None
        and listing.description.strip()
        and (
            settings.max_jd_chars <= 0
            or len(listing.description.strip()) <= settings.max_jd_chars
        )
    ]
    summary.estimate = estimate_evaluation_batch(
        settings,
        workflow=workflow,
        profile_text=profile.skills_text,
        jd_texts=guard_texts,
    )
    enforce_batch_guardrails(
        settings,
        workflow=workflow,
        estimate=summary.estimate,
        max_items=max_items
        if max_items is not None
        else settings.max_evaluate_listing_items,
    )
    tailoring_inputs: list[dict[str, object]] = []
    evaluated_jobs: list[tuple[JobAnalysis, bool]] = []

    for listing_id in listing_ids:
        result, job = _evaluate_one_listing(
            db,
            listing_id=listing_id,
            llm=llm,
            settings=settings,
            profile_id=resolved_profile_id,
        )
        summary.results.append(result)
        if result.error:
            summary.failed += 1
            if "no job description text" in result.error or "limit is" in result.error:
                summary.skipped += 1
            continue
        summary.succeeded += 1
        if job is not None and job.status == STATUS_NEEDS_TAILORING and not result.cached:
            summary.tailoring_job_ids.append(job.id)
            tailoring_inputs.append(
                {
                    "jd_text": job.jd_full_text,
                    "gaps": job.gaps or [],
                }
            )
        if job is not None:
            evaluated_jobs.append((job, result.cached))

    _apply_tailoring_guardrails(summary, settings, profile.skills_text, tailoring_inputs)
    if on_evaluated is not None:
        allowed_tailoring_ids = set(summary.tailoring_job_ids)
        for job, cached in evaluated_jobs:
            if (
                job.status == STATUS_NEEDS_TAILORING
                and not cached
                and job.id not in allowed_tailoring_ids
            ):
                continue
            on_evaluated(job, cached)
    return summary


def evaluate_pending_listings(
    db: Session,
    *,
    llm: LLMClient,
    settings: Settings,
    profile_id: int | None = None,
    limit: int = 100,
    source: str | None = None,
    on_evaluated: TailoringCallback | None = None,
    workflow: str = EVALUATE_LISTINGS_WORKFLOW,
    max_items: int | None = None,
) -> ListingEvaluationSummary:
    query = db.query(JobListing).filter(
        JobListing.job_analysis_id.is_(None),
        func.length(func.trim(JobListing.description)) > 0,
    )
    if source:
        query = query.filter(JobListing.source == source)
    listings = query.order_by(JobListing.scraped_at.desc()).limit(limit).all()
    return evaluate_listing_ids(
        db,
        listing_ids=[listing.id for listing in listings],
        llm=llm,
        settings=settings,
        profile_id=profile_id,
        on_evaluated=on_evaluated,
        workflow=workflow,
        max_items=max_items
        if max_items is not None
        else settings.max_evaluate_pending_items,
    )


def _apply_tailoring_guardrails(
    summary: ListingEvaluationSummary,
    settings: Settings,
    baseline_text: str,
    tailoring_inputs: list[dict[str, object]],
) -> None:
    if not summary.tailoring_job_ids:
        return
    max_jobs = settings.max_tailoring_jobs_per_batch
    if max_jobs > 0 and len(summary.tailoring_job_ids) > max_jobs:
        blocked = len(summary.tailoring_job_ids) - max_jobs
        summary.tailoring_blocked += blocked
        summary.blocked += blocked
        summary.tailoring_job_ids = summary.tailoring_job_ids[:max_jobs]
        tailoring_inputs = tailoring_inputs[:max_jobs]
        summary.warnings.append(
            {
                "code": "tailoring_job_limit_exceeded",
                "message": (
                    f"Only {max_jobs} tailoring jobs were queued; "
                    f"{blocked} were blocked by quota."
                ),
                "max_items": max_jobs,
            }
        )
    estimate = estimate_tailoring_batch(
        settings,
        baseline_text=baseline_text,
        jobs=tailoring_inputs,
    )
    result = check_batch_guardrails(
        settings,
        workflow="tailor",
        estimate=estimate,
        max_items=max_jobs,
    )
    if result.allowed:
        return
    blocked = len(summary.tailoring_job_ids)
    summary.tailoring_blocked += blocked
    summary.blocked += blocked
    summary.tailoring_job_ids = []
    summary.warnings.append(
        {
            "code": result.code,
            "message": result.message,
            "details": result.details,
        }
    )


def _evaluate_one_listing(
    db: Session,
    *,
    listing_id: uuid.UUID,
    llm: LLMClient,
    settings: Settings,
    profile_id: int,
) -> tuple[ListingEvaluationResult, JobAnalysis | None]:
    listing = db.get(JobListing, listing_id)
    if listing is None:
        return (
            ListingEvaluationResult(
                listing_id=listing_id,
                error=f"Job listing {listing_id} not found.",
            ),
            None,
        )

    jd_text = listing.description.strip()
    if not jd_text:
        return (
            ListingEvaluationResult(
                listing_id=listing_id,
                error="Job listing has no job description text.",
            ),
            None,
        )

    actual_chars = len(jd_text)
    if settings.max_jd_chars > 0 and actual_chars > settings.max_jd_chars:
        return (
            ListingEvaluationResult(
                listing_id=listing_id,
                error=(
                    f"Job description has {actual_chars} characters; "
                    f"limit is {settings.max_jd_chars}."
                ),
            ),
            None,
        )

    try:
        job, cached = evaluate_jd(
            db,
            jd_text,
            llm,
            prompt_version=prompt_version_for_step(
                STEP_EVALUATE,
                settings=settings,
            ),
            threshold=settings.resume_gen_threshold,
            profile_id=profile_id,
        )
    except LookupError as exc:
        return ListingEvaluationResult(listing_id=listing_id, error=str(exc)), None
    except LLMUnavailableError as exc:
        return (
            ListingEvaluationResult(
                listing_id=listing_id,
                error=f"llm_unavailable: {exc}",
            ),
            None,
        )
    except LLMInvalidOutputError as exc:
        return (
            ListingEvaluationResult(
                listing_id=listing_id,
                error=f"llm_invalid_output: {exc}",
            ),
            None,
        )

    listing.job_analysis_id = job.id
    db.commit()
    return (
        ListingEvaluationResult(
            listing_id=listing.id,
            job_analysis_id=job.id,
            score=job.score or 0,
            status=job.status or STATUS_SKIP,
            cached=cached,
        ),
        job,
    )
