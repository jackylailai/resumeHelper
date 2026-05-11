from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_listing import JobListing
from backend.app.schemas.job_listing import JobListingDetailOut, JobListingSummaryOut

router = APIRouter()

_PREVIEW_CHARS = 220
_ANALYSIS_STATUSES = frozenset({"ready_to_submit", "needs_tailoring", "skip"})

ListingStatusFilter = Literal[
    "unanalyzed",
    "ready_to_submit",
    "needs_tailoring",
    "skip",
    "failed-invalid",
    "failed_invalid",
]
ListingSortBy = Literal["scraped_at", "score", "company", "source"]
SortDirection = Literal["asc", "desc"]


def _preview(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _PREVIEW_CHARS:
        return compact
    return compact[: _PREVIEW_CHARS - 1].rstrip() + "..."


def _summary(
    listing: JobListing,
    analysis: JobAnalysis | None = None,
) -> JobListingSummaryOut:
    return JobListingSummaryOut(
        id=listing.id,
        source=listing.source,
        source_id=listing.source_id,
        title=listing.title,
        company=listing.company,
        location=listing.location,
        url=listing.url,
        description_preview=_preview(listing.description),
        has_description=bool(listing.description.strip()),
        list_status=_listing_status(listing, analysis),
        analyzed=listing.job_analysis_id is not None,
        job_analysis_id=listing.job_analysis_id,
        last_score=analysis.score if analysis else None,
        last_status=analysis.status if analysis else None,
        scraped_at=listing.scraped_at,
        changed_at=listing.changed_at,
    )


def _listing_status(listing: JobListing, analysis: JobAnalysis | None) -> str:
    if not listing.description.strip():
        return "failed-invalid"
    if listing.job_analysis_id is None:
        return "unanalyzed"
    if analysis and analysis.status:
        return analysis.status
    return "analyzed"


@router.get("/job-listings")
def list_job_listings(
    q: str | None = Query(default=None, max_length=120),
    source: str | None = Query(default=None, max_length=32),
    analyzed: bool | None = Query(default=None),
    status: ListingStatusFilter | None = Query(default=None),
    sort_by: ListingSortBy = Query(default="scraped_at"),
    sort_dir: SortDirection = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JSONResponse:
    query = db.query(JobListing)
    joined_analysis = False

    if source:
        query = query.filter(JobListing.source == source)

    status_value = (
        "failed-invalid"
        if status in {"failed-invalid", "failed_invalid"}
        else status
    )
    if status_value == "failed-invalid":
        query = query.filter(func.length(func.trim(JobListing.description)) == 0)
    elif status_value == "unanalyzed":
        query = query.filter(
            JobListing.job_analysis_id.is_(None),
            func.length(func.trim(JobListing.description)) > 0,
        )
    elif status_value in _ANALYSIS_STATUSES:
        query = query.join(JobAnalysis, JobListing.job_analysis_id == JobAnalysis.id)
        joined_analysis = True
        query = query.filter(JobAnalysis.status == status_value)
    elif analyzed is True:
        query = query.filter(JobListing.job_analysis_id.isnot(None))
    elif analyzed is False:
        query = query.filter(JobListing.job_analysis_id.is_(None))

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                JobListing.title.ilike(pattern),
                JobListing.company.ilike(pattern),
                JobListing.location.ilike(pattern),
                JobListing.description.ilike(pattern),
            )
        )

    total = query.count()
    if sort_by == "score":
        if not joined_analysis:
            query = query.outerjoin(
                JobAnalysis,
                JobListing.job_analysis_id == JobAnalysis.id,
            )
        score_order = (
            JobAnalysis.score.asc()
            if sort_dir == "asc"
            else JobAnalysis.score.desc()
        )
        order_by = [
            score_order.nullslast(),
            JobListing.scraped_at.desc(),
            JobListing.id.asc(),
        ]
    elif sort_by == "company":
        company_order = (
            func.lower(JobListing.company).asc()
            if sort_dir == "asc"
            else func.lower(JobListing.company).desc()
        )
        order_by = [company_order, JobListing.scraped_at.desc(), JobListing.id.asc()]
    elif sort_by == "source":
        source_order = (
            func.lower(JobListing.source).asc()
            if sort_dir == "asc"
            else func.lower(JobListing.source).desc()
        )
        order_by = [source_order, JobListing.scraped_at.desc(), JobListing.id.asc()]
    else:
        scraped_order = (
            JobListing.scraped_at.asc()
            if sort_dir == "asc"
            else JobListing.scraped_at.desc()
        )
        order_by = [scraped_order, JobListing.id.asc()]

    listings = (
        query.order_by(*order_by)
        .offset(offset)
        .limit(limit)
        .all()
    )
    analysis_ids = [listing.job_analysis_id for listing in listings if listing.job_analysis_id]
    analyses: dict[uuid.UUID, JobAnalysis] = {}
    if analysis_ids:
        rows = db.query(JobAnalysis).filter(JobAnalysis.id.in_(analysis_ids)).all()
        analyses = {row.id: row for row in rows}
    data = [
        _summary(listing, analyses.get(listing.job_analysis_id)).model_dump(mode="json")
        for listing in listings
    ]
    if total == 0 or not data:
        range_start = 0
        range_end = 0
    else:
        range_start = offset + 1
        range_end = min(offset + len(data), total)
    return success(
        data,
        total=total,
        limit=limit,
        offset=offset,
        range_start=range_start,
        range_end=range_end,
        sort_by=sort_by,
        sort_dir=sort_dir,
        status=status_value,
    )


@router.get("/job-listings/{listing_id}")
def get_job_listing(listing_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    listing = db.get(JobListing, listing_id)
    if listing is None:
        return error("not_found", f"Job listing {listing_id} not found", status_code=404)

    analysis = db.get(JobAnalysis, listing.job_analysis_id) if listing.job_analysis_id else None
    summary = _summary(listing, analysis)
    detail = JobListingDetailOut(
        **summary.model_dump(),
        description=listing.description,
        raw_json=listing.raw_json,
    )
    return success(detail.model_dump(mode="json"))
