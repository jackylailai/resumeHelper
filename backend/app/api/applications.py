from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import get_db
from backend.app.models.application import APPLICATION_STATUSES, Application
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_listing import JobListing
from backend.app.schemas.application import (
    ApplicationCreateIn,
    ApplicationOut,
    ApplicationUpdateIn,
)

router = APIRouter()

ApplicationStatusFilter = Literal[
    "planned",
    "applied",
    "interviewing",
    "rejected",
    "offer",
    "archived",
]
ApplicationSortBy = Literal[
    "created_at",
    "updated_at",
    "follow_up_date",
    "score",
    "company",
    "status",
]
SortDirection = Literal["asc", "desc"]


def _latest_resume(
    db: Session,
    job_analysis_id: uuid.UUID | None,
) -> GeneratedResume | None:
    if job_analysis_id is None:
        return None
    return (
        db.query(GeneratedResume)
        .filter(GeneratedResume.job_analysis_id == job_analysis_id)
        .order_by(GeneratedResume.created_at.desc())
        .first()
    )


def _validate_links(
    db: Session,
    body: ApplicationCreateIn,
) -> tuple[JobListing | None, JobAnalysis | None, GeneratedResume | None] | JSONResponse:
    listing = db.get(JobListing, body.job_listing_id) if body.job_listing_id else None
    if body.job_listing_id and listing is None:
        return error(
            "not_found",
            f"Job listing {body.job_listing_id} not found",
            status_code=404,
        )

    analysis = db.get(JobAnalysis, body.job_analysis_id) if body.job_analysis_id else None
    if body.job_analysis_id and analysis is None:
        return error(
            "not_found",
            f"Job analysis {body.job_analysis_id} not found",
            status_code=404,
        )

    resume = (
        db.get(GeneratedResume, body.generated_resume_id)
        if body.generated_resume_id
        else None
    )
    if body.generated_resume_id and resume is None:
        return error(
            "not_found",
            f"Generated resume {body.generated_resume_id} not found",
            status_code=404,
        )

    if listing and analysis is None and listing.job_analysis_id:
        analysis = db.get(JobAnalysis, listing.job_analysis_id)
    if resume and analysis is None:
        analysis = db.get(JobAnalysis, resume.job_analysis_id)
    if resume is None:
        resume = _latest_resume(db, analysis.id if analysis else None)

    return listing, analysis, resume


def _find_existing(
    db: Session,
    listing: JobListing | None,
    analysis: JobAnalysis | None,
) -> Application | None:
    clauses = []
    if listing is not None:
        clauses.append(Application.job_listing_id == listing.id)
    if analysis is not None:
        clauses.append(Application.job_analysis_id == analysis.id)
    if not clauses:
        return None
    return (
        db.query(Application)
        .filter(or_(*clauses))
        .order_by(Application.created_at.desc())
        .first()
    )


def _application_out(
    app: Application,
    listing: JobListing | None,
    analysis: JobAnalysis | None,
    resume: GeneratedResume | None,
) -> dict:
    return ApplicationOut(
        id=app.id,
        job_listing_id=app.job_listing_id,
        job_analysis_id=app.job_analysis_id,
        generated_resume_id=app.generated_resume_id,
        status=app.status,  # type: ignore[arg-type]
        follow_up_date=app.follow_up_date,
        notes=app.notes,
        created_at=app.created_at,
        updated_at=app.updated_at,
        company=listing.company if listing else None,
        title=listing.title if listing else None,
        source_url=listing.url if listing else None,
        score=analysis.score if analysis else None,
        analysis_status=analysis.status if analysis else None,
        pdf_url=resume.pdf_url if resume else None,
    ).model_dump(mode="json")


def _hydrate(db: Session, apps: list[Application]) -> list[dict]:
    listing_ids = [app.job_listing_id for app in apps if app.job_listing_id]
    analysis_ids = [app.job_analysis_id for app in apps if app.job_analysis_id]
    resume_ids = [app.generated_resume_id for app in apps if app.generated_resume_id]

    listings = (
        {
            row.id: row
            for row in db.query(JobListing).filter(JobListing.id.in_(listing_ids)).all()
        }
        if listing_ids
        else {}
    )
    analyses = (
        {
            row.id: row
            for row in db.query(JobAnalysis).filter(JobAnalysis.id.in_(analysis_ids)).all()
        }
        if analysis_ids
        else {}
    )
    resumes = (
        {
            row.id: row
            for row in db.query(GeneratedResume)
            .filter(GeneratedResume.id.in_(resume_ids))
            .all()
        }
        if resume_ids
        else {}
    )

    missing_resume_analysis_ids = [
        app.job_analysis_id
        for app in apps
        if app.job_analysis_id and app.generated_resume_id is None
    ]
    if missing_resume_analysis_ids:
        latest = (
            db.query(GeneratedResume)
            .filter(GeneratedResume.job_analysis_id.in_(missing_resume_analysis_ids))
            .order_by(
                GeneratedResume.job_analysis_id,
                GeneratedResume.created_at.desc(),
            )
            .distinct(GeneratedResume.job_analysis_id)
            .all()
        )
        latest_by_analysis = {row.job_analysis_id: row for row in latest}
    else:
        latest_by_analysis = {}

    rows = []
    for app in apps:
        listing = listings.get(app.job_listing_id)
        analysis = analyses.get(app.job_analysis_id)
        resume = resumes.get(app.generated_resume_id) or latest_by_analysis.get(
            app.job_analysis_id
        )
        rows.append(_application_out(app, listing, analysis, resume))
    return rows


@router.get("/applications")
def list_applications(
    q: str | None = Query(default=None, max_length=120),
    status: ApplicationStatusFilter | None = Query(default=None),
    sort_by: ApplicationSortBy = Query(default="updated_at"),
    sort_dir: SortDirection = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JSONResponse:
    query = db.query(Application)
    joined_listing = False
    joined_analysis = False

    if status:
        query = query.filter(Application.status == status)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.outerjoin(
            JobListing,
            Application.job_listing_id == JobListing.id,
        )
        joined_listing = True
        query = query.filter(
            or_(
                JobListing.title.ilike(pattern),
                JobListing.company.ilike(pattern),
                Application.notes.ilike(pattern),
            )
        )

    total = query.count()
    direction = sort_dir == "asc"
    if sort_by == "company":
        if not joined_listing:
            query = query.outerjoin(
                JobListing,
                Application.job_listing_id == JobListing.id,
            )
        order = (
            func.lower(JobListing.company).asc()
            if direction
            else func.lower(JobListing.company).desc()
        )
        order_by = [order.nullslast(), Application.updated_at.desc()]
    elif sort_by == "score":
        if not joined_analysis:
            query = query.outerjoin(
                JobAnalysis,
                Application.job_analysis_id == JobAnalysis.id,
            )
        order = JobAnalysis.score.asc() if direction else JobAnalysis.score.desc()
        order_by = [order.nullslast(), Application.updated_at.desc()]
    elif sort_by == "follow_up_date":
        order = (
            Application.follow_up_date.asc()
            if direction
            else Application.follow_up_date.desc()
        )
        order_by = [order.nullslast(), Application.updated_at.desc()]
    elif sort_by == "status":
        order = Application.status.asc() if direction else Application.status.desc()
        order_by = [order, Application.updated_at.desc()]
    elif sort_by == "created_at":
        order = Application.created_at.asc() if direction else Application.created_at.desc()
        order_by = [order, Application.id.asc()]
    else:
        order = Application.updated_at.asc() if direction else Application.updated_at.desc()
        order_by = [order, Application.id.asc()]

    apps = query.order_by(*order_by).offset(offset).limit(limit).all()
    rows = _hydrate(db, apps)
    return success(
        rows,
        total=total,
        limit=limit,
        offset=offset,
        range_start=0 if not rows else offset + 1,
        range_end=0 if not rows else min(offset + len(rows), total),
        sort_by=sort_by,
        sort_dir=sort_dir,
        status=status,
    )


@router.post("/applications")
def create_application(
    body: ApplicationCreateIn,
    db: Session = Depends(get_db),
) -> JSONResponse:
    if not any([body.job_listing_id, body.job_analysis_id, body.generated_resume_id]):
        return error(
            "missing_link",
            "Provide at least one of job_listing_id, job_analysis_id, "
            "or generated_resume_id.",
            status_code=422,
        )

    links = _validate_links(db, body)
    if isinstance(links, JSONResponse):
        return links
    listing, analysis, resume = links

    existing = _find_existing(db, listing, analysis)
    if existing is not None:
        changed = False
        if existing.generated_resume_id is None and resume is not None:
            existing.generated_resume_id = resume.id
            changed = True
        if body.follow_up_date is not None:
            existing.follow_up_date = body.follow_up_date
            changed = True
        if body.notes is not None:
            existing.notes = body.notes
            changed = True
        if body.status != existing.status:
            existing.status = body.status
            changed = True
        if changed:
            db.commit()
            db.refresh(existing)
        return success(
            _application_out(existing, listing, analysis, resume),
            status_code=200,
            existing=True,
        )

    app = Application(
        job_listing_id=listing.id if listing else None,
        job_analysis_id=analysis.id if analysis else None,
        generated_resume_id=resume.id if resume else None,
        status=body.status,
        follow_up_date=body.follow_up_date,
        notes=body.notes,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return success(_application_out(app, listing, analysis, resume), status_code=201)


@router.patch("/applications/{application_id}")
def update_application(
    application_id: uuid.UUID,
    body: ApplicationUpdateIn,
    db: Session = Depends(get_db),
) -> JSONResponse:
    app = db.get(Application, application_id)
    if app is None:
        return error(
            "not_found",
            f"Application {application_id} not found",
            status_code=404,
        )

    if body.status is not None:
        if body.status not in APPLICATION_STATUSES:
            return error(
                "invalid_status",
                f"Invalid status {body.status}",
                status_code=422,
            )
        app.status = body.status
    if "follow_up_date" in body.model_fields_set:
        app.follow_up_date = body.follow_up_date
    if "notes" in body.model_fields_set:
        app.notes = body.notes

    db.commit()
    db.refresh(app)
    rows = _hydrate(db, [app])
    return success(rows[0])
