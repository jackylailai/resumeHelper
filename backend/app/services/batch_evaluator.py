from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models.job_analysis import STATUS_NEEDS_TAILORING, STATUS_SKIP, JobAnalysis
from backend.app.models.job_listing import JobListing
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
    results: list[ListingEvaluationResult] = field(default_factory=list)
    tailoring_job_ids: list[uuid.UUID] = field(default_factory=list)


TailoringCallback = Callable[[JobAnalysis, bool], None]


def evaluate_listing_ids(
    db: Session,
    *,
    listing_ids: list[uuid.UUID],
    llm: LLMClient,
    settings: Settings,
    profile_id: int | None = None,
    on_evaluated: TailoringCallback | None = None,
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
            continue
        summary.succeeded += 1
        if job is not None and job.status == STATUS_NEEDS_TAILORING and not result.cached:
            summary.tailoring_job_ids.append(job.id)
        if job is not None and on_evaluated is not None:
            on_evaluated(job, result.cached)

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
