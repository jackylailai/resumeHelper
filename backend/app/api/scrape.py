from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.api.envelope import error, success
from backend.app.config import get_settings
from backend.app.db import SessionLocal, get_db
from backend.app.models.scrape_run import ScrapeRun
from backend.app.schemas.scrape import (
    ScrapeControlStartIn,
    ScrapeControlStatusOut,
    ScrapeRunCreatedOut,
    ScrapeRunCreateIn,
    ScrapeRunOut,
    ScrapeStatusOut,
)
from backend.app.services.ai_guardrails import SCRAPE_AFTER_EVALUATE_WORKFLOW
from backend.app.services.batch_evaluator import evaluate_pending_listings
from backend.app.services.scrapers.pipeline import (
    active_scrape_runs,
    create_scrape_runs,
    request_cancel_active_runs,
    run_scrape_background,
)
from backend.app.services.scrapers.registry import resolve_sources
from backend.app.workers.tailor import run_tailoring

router = APIRouter()


def _session_factory(request: Request):
    return getattr(request.app.state, "session_factory", SessionLocal)


def _recent_runs(db: Session, limit: int) -> list[ScrapeRun]:
    return (
        db.query(ScrapeRun)
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .limit(limit)
        .all()
    )


def _control_status_out(db: Session, limit: int = 10) -> ScrapeControlStatusOut:
    active = active_scrape_runs(db)
    return ScrapeControlStatusOut(
        active=bool(active),
        active_runs=[ScrapeRunOut.model_validate(run) for run in active],
        recent_runs=[ScrapeRunOut.model_validate(run) for run in _recent_runs(db, limit)],
    )


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
        must_contain=body.must_contain,
        match_mode=body.match_mode,
        regex=body.regex,
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


@router.get("/scrape/control")
def scrape_control_status(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return success(_control_status_out(db, limit).model_dump(mode="json"))


@router.post("/scrape/control/start")
def start_scrape_control(
    body: ScrapeControlStartIn,
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

    settings = get_settings()
    if (
        body.evaluate_after_scrape
        and settings.max_scrape_after_evaluate_items > 0
        and body.evaluate_limit > settings.max_scrape_after_evaluate_items
    ):
        return error(
            "ai_batch_item_limit_exceeded",
            (
                f"scrape_after_evaluate requested {body.evaluate_limit} items; "
                f"limit is {settings.max_scrape_after_evaluate_items}."
            ),
            status_code=429,
            details={
                "workflow": SCRAPE_AFTER_EVALUATE_WORKFLOW,
                "items": body.evaluate_limit,
                "max_items": settings.max_scrape_after_evaluate_items,
            },
        )

    active = active_scrape_runs(db)
    if active and not body.stop_existing:
        status = _control_status_out(db)
        return error(
            "scrape_already_running",
            "A scrape is already running. Stop it before starting a new keyword.",
            status_code=409,
            details=status.model_dump(mode="json"),
        )
    if active and body.stop_existing:
        request_cancel_active_runs(db)

    runs = create_scrape_runs(
        db,
        source=body.source,
        keyword=keyword,
        limit=body.limit,
        must_contain=body.must_contain,
        match_mode=body.match_mode,
        regex=body.regex,
    )
    background_tasks.add_task(
        run_scrape_control_background,
        [run.id for run in runs],
        _session_factory(request),
        getattr(request.app.state, "llm_client", None),
        body.evaluate_after_scrape,
        body.evaluate_limit,
        body.profile_id,
        None if body.source in {"all", "all_with_linkedin"} else body.source,
    )
    out = ScrapeRunCreatedOut(
        runs=[ScrapeRunOut.model_validate(run) for run in runs]
    )
    return success(
        out.model_dump(mode="json"),
        active_status=_control_status_out(db).model_dump(mode="json"),
        status_code=202,
    )


@router.post("/scrape/control/stop")
def stop_scrape_control(db: Session = Depends(get_db)) -> JSONResponse:
    cancelled = request_cancel_active_runs(db)
    status = _control_status_out(db)
    return success(
        status.model_dump(mode="json"),
        cancelled_runs=[
            ScrapeRunOut.model_validate(run).model_dump(mode="json")
            for run in cancelled
        ],
    )


@router.get("/scrape/status")
def scrape_status(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> JSONResponse:
    runs = _recent_runs(db, limit)
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


def run_scrape_control_background(
    run_ids: list[uuid.UUID],
    session_factory,
    llm,
    evaluate_after_scrape: bool,
    evaluate_limit: int,
    profile_id: int | None,
    source: str | None,
) -> None:
    import asyncio

    from backend.app.config import get_settings
    from backend.app.services.llm.factory import create_llm_client

    with session_factory() as db:
        completed = asyncio.run(run_scrape_runs_for_control(db, run_ids))
        if not evaluate_after_scrape:
            return
        if not any(run.status in {"succeeded", "partial"} for run in completed):
            return

        settings = get_settings()
        if llm is None:
            try:
                llm = create_llm_client()
            except Exception as exc:
                _append_evaluation_error(db, completed, str(exc))
                return
        try:
            summary = evaluate_pending_listings(
                db,
                llm=llm,
                settings=settings,
                profile_id=profile_id,
                source=source,
                limit=evaluate_limit,
                workflow=SCRAPE_AFTER_EVALUATE_WORKFLOW,
                max_items=settings.max_scrape_after_evaluate_items,
            )
        except Exception as exc:
            _append_evaluation_error(db, completed, str(exc))
            return

        for job_id in summary.tailoring_job_ids:
            run_tailoring(
                job_analysis_id=job_id,
                llm=llm,
                prompt_version=settings.llm_prompt_version,
                session_factory=session_factory,
            )


async def run_scrape_runs_for_control(
    db: Session,
    run_ids: list[uuid.UUID],
) -> list[ScrapeRun]:
    from backend.app.services.scrapers.pipeline import execute_scrape_runs

    return await execute_scrape_runs(db, run_ids)


def _append_evaluation_error(
    db: Session,
    runs: list[ScrapeRun],
    message: str,
) -> None:
    for run in runs:
        if run.status not in {"succeeded", "partial"}:
            continue
        prefix = f"Evaluation failed: {message}"
        run.error_summary = f"{run.error_summary}\n{prefix}" if run.error_summary else prefix
    db.commit()
