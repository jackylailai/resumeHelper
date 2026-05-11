from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.db import SessionLocal, get_db
from backend.app.models.scrape_run import ScrapeRun
from backend.app.schemas.scrape import (
    ScrapeRunCreateIn,
    ScrapeRunCreatedOut,
    ScrapeRunOut,
    ScrapeStatusOut,
)
from backend.app.services.scrapers.pipeline import create_scrape_runs, run_scrape_background
from backend.app.services.scrapers.registry import resolve_sources

router = APIRouter()


def _session_factory(request: Request):
    return getattr(request.app.state, "session_factory", SessionLocal)


@router.post("/scrape/run")
def run_scrape(
    body: ScrapeRunCreateIn,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    keyword = body.keyword.strip()
    if not keyword:
        return error("invalid_keyword", "keyword must not be blank", status_code=422)

    try:
        resolve_sources(body.source)
    except ValueError as exc:
        return error("invalid_source", str(exc), status_code=422)

    runs = create_scrape_runs(
        db,
        source=body.source,
        keyword=keyword,
        limit=body.limit,
    )
    background_tasks.add_task(
        run_scrape_background,
        [run.id for run in runs],
        _session_factory(request),
    )
    out = ScrapeRunCreatedOut(
        runs=[ScrapeRunOut.model_validate(run) for run in runs]
    )
    return success(out.model_dump(mode="json"), status_code=202)


@router.get("/scrape/status")
def scrape_status(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> JSONResponse:
    runs = (
        db.query(ScrapeRun)
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .limit(limit)
        .all()
    )
    out = ScrapeStatusOut(
        recent_runs=[ScrapeRunOut.model_validate(run) for run in runs]
    )
    return success(out.model_dump(mode="json"))


@router.get("/scrape/runs/{run_id}")
def get_scrape_run(run_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    run = db.get(ScrapeRun, run_id)
    if run is None:
        return error("not_found", f"scrape run {run_id} not found", status_code=404)
    return success(ScrapeRunOut.model_validate(run).model_dump(mode="json"))
