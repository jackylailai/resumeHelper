from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import success
from backend.app.config import get_settings
from backend.app.db import get_db
from backend.app.models.application import Application
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import (
    STATUS_NEEDS_TAILORING,
    STATUS_READY_TO_SUBMIT,
    JobAnalysis,
)
from backend.app.models.job_listing import JobListing
from backend.app.schemas.opportunity import JobOpportunityOut

router = APIRouter()


@router.get("/job-opportunities")
def list_job_opportunities(
    include_tracked: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> JSONResponse:
    settings = get_settings()
    candidates = (
        db.query(JobListing, JobAnalysis)
        .join(JobAnalysis, JobListing.job_analysis_id == JobAnalysis.id)
        .filter(JobListing.url.isnot(None))
        .order_by(JobAnalysis.score.desc().nullslast(), JobAnalysis.created_at.desc())
        .limit(limit * 4)
        .all()
    )

    analysis_ids = [analysis.id for _listing, analysis in candidates]
    latest_resumes = _latest_resumes_by_analysis(db, analysis_ids)
    applications = _applications_by_job(
        db,
        [listing.id for listing, _analysis in candidates],
        analysis_ids,
    )

    opportunities: list[JobOpportunityOut] = []
    for listing, analysis in candidates:
        resume = latest_resumes.get(analysis.id)
        application = (
            applications.get((listing.id, analysis.id))
            or applications.get((listing.id, None))
            or applications.get((None, analysis.id))
        )
        tracked = application is not None
        if tracked and not include_tracked:
            continue
        if not _is_suitable(analysis, resume, settings.resume_gen_threshold):
            continue

        opportunities.append(
            JobOpportunityOut(
                job_listing_id=listing.id,
                job_analysis_id=analysis.id,
                generated_resume_id=resume.id if resume else None,
                application_id=application.id if application else None,
                company=listing.company,
                title=listing.title,
                source=listing.source,
                source_url=listing.url,
                frontend_url=f"/jobs.html?listing_id={listing.id}",
                score=analysis.score,
                status=analysis.status,
                scraped_at=listing.scraped_at,
                analyzed_at=analysis.created_at,
                has_generated_resume=resume is not None,
                pdf_url=resume.pdf_url if resume else None,
                tracked=tracked,
            )
        )
        if len(opportunities) >= limit:
            break

    return success(
        [item.model_dump(mode="json") for item in opportunities],
        count=len(opportunities),
        include_tracked=include_tracked,
        limit=limit,
    )


def _is_suitable(
    analysis: JobAnalysis,
    resume: GeneratedResume | None,
    threshold: int,
) -> bool:
    if analysis.status == STATUS_READY_TO_SUBMIT:
        return True
    if analysis.score is not None and analysis.score >= threshold:
        return True
    return analysis.status == STATUS_NEEDS_TAILORING and resume is not None


def _latest_resumes_by_analysis(
    db: Session,
    analysis_ids: list[uuid.UUID],
) -> dict[uuid.UUID, GeneratedResume]:
    if not analysis_ids:
        return {}
    latest = (
        db.query(GeneratedResume)
        .filter(GeneratedResume.job_analysis_id.in_(analysis_ids))
        .order_by(
            GeneratedResume.job_analysis_id,
            GeneratedResume.created_at.desc(),
        )
        .distinct(GeneratedResume.job_analysis_id)
        .all()
    )
    return {resume.job_analysis_id: resume for resume in latest}


def _applications_by_job(
    db: Session,
    listing_ids: list[uuid.UUID],
    analysis_ids: list[uuid.UUID],
) -> dict[tuple[uuid.UUID | None, uuid.UUID | None], Application]:
    if not listing_ids and not analysis_ids:
        return {}
    apps = (
        db.query(Application)
        .filter(
            (Application.job_listing_id.in_(listing_ids))
            | (Application.job_analysis_id.in_(analysis_ids))
        )
        .all()
    )
    result: dict[tuple[uuid.UUID | None, uuid.UUID | None], Application] = {}
    for app in apps:
        if app.job_listing_id is not None and app.job_analysis_id is not None:
            result[(app.job_listing_id, app.job_analysis_id)] = app
        if app.job_listing_id is not None:
            result[(app.job_listing_id, None)] = app
        if app.job_analysis_id is not None:
            result[(None, app.job_analysis_id)] = app
    return result
