from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.models.job_listing import JobListing
from backend.app.schemas.job_listing import JobListingDetailOut, JobListingSummaryOut

router = APIRouter()

_PREVIEW_CHARS = 220


def _preview(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _PREVIEW_CHARS:
        return compact
    return compact[: _PREVIEW_CHARS - 1].rstrip() + "..."


def _summary(listing: JobListing) -> JobListingSummaryOut:
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
        analyzed=listing.job_analysis_id is not None,
        job_analysis_id=listing.job_analysis_id,
        scraped_at=listing.scraped_at,
    )


@router.get("/job-listings")
def list_job_listings(
    q: str | None = Query(default=None, max_length=120),
    source: str | None = Query(default=None, max_length=32),
    analyzed: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JSONResponse:
    query = db.query(JobListing)

    if source:
        query = query.filter(JobListing.source == source)

    if analyzed is True:
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
    listings = (
        query.order_by(JobListing.scraped_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    data = [_summary(listing).model_dump(mode="json") for listing in listings]
    return success(data, total=total, limit=limit, offset=offset)


@router.get("/job-listings/{listing_id}")
def get_job_listing(listing_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    listing = db.get(JobListing, listing_id)
    if listing is None:
        return error("not_found", f"Job listing {listing_id} not found", status_code=404)

    summary = _summary(listing)
    detail = JobListingDetailOut(
        **summary.model_dump(),
        description=listing.description,
        raw_json=listing.raw_json,
    )
    return success(detail.model_dump(mode="json"))
