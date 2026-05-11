from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.models.scrape_run import ACTIVE_SCRAPE_RUN_STATUSES, ScrapeRun
from backend.app.services.scrapers.base import BaseScraper, JobListingDraft
from backend.app.services.scrapers.persistence import UpsertStats, upsert_drafts_with_stats
from backend.app.services.scrapers.registry import SCRAPERS, resolve_sources

logger = logging.getLogger(__name__)


async def scrape_with_runner(
    scraper: BaseScraper,
    keyword: str,
    limit: int,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[JobListingDraft], int, list[str], bool]:
    if callable(should_cancel) and should_cancel():
        return [], 0, [], True

    drafts = await scraper.search(keyword, limit)
    if callable(should_cancel) and should_cancel():
        return [], 0, [], True

    enriched: list[JobListingDraft] = []
    failed = 0
    errors: list[str] = []
    for draft in drafts:
        if callable(should_cancel) and should_cancel():
            return enriched, failed, errors, True
        try:
            enriched.append(await scraper.fetch_detail(draft))
        except Exception as exc:
            failed += 1
            message = f"{draft.source_id}: {exc}"
            errors.append(message)
            logger.warning("scrape_detail_failed source=%s %s", scraper.source, message)
            enriched.append(draft)
    return enriched, failed, errors, False


def create_scrape_runs(
    db: Session,
    *,
    source: str,
    keyword: str,
    limit: int,
) -> list[ScrapeRun]:
    runs = [
        ScrapeRun(source=item, keyword=keyword, limit=limit, status="queued")
        for item in resolve_sources(source)
    ]
    db.add_all(runs)
    db.commit()
    for run in runs:
        db.refresh(run)
    return runs


def request_cancel_active_runs(db: Session) -> list[ScrapeRun]:
    runs = (
        db.query(ScrapeRun)
        .filter(ScrapeRun.status.in_(ACTIVE_SCRAPE_RUN_STATUSES))
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .all()
    )
    now = datetime.now(UTC)
    for run in runs:
        if run.status == "queued":
            run.status = "cancelled"
            run.finished_at = now
            continue
        if run.status == "running":
            run.status = "cancel_requested"
    db.commit()
    for run in runs:
        db.refresh(run)
    return runs


def active_scrape_runs(db: Session) -> list[ScrapeRun]:
    return (
        db.query(ScrapeRun)
        .filter(ScrapeRun.status.in_(ACTIVE_SCRAPE_RUN_STATUSES))
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .all()
    )


async def execute_scrape_run(db: Session, run_id: uuid.UUID) -> ScrapeRun:
    run = db.get(ScrapeRun, run_id)
    if run is None:
        raise LookupError(f"scrape run {run_id} not found")

    if run.status in {"cancel_requested", "cancelled"}:
        _mark_cancelled(run)
        db.commit()
        db.refresh(run)
        return run

    run.status = "running"
    run.started_at = datetime.now(UTC)
    run.error_summary = None
    db.commit()

    try:
        scraper_cls = SCRAPERS[run.source]
        async with scraper_cls() as scraper:  # type: ignore[attr-defined]
            drafts, detail_failures, errors, cancelled = await scrape_with_runner(
                scraper,
                run.keyword,
                run.limit,
                should_cancel=lambda: _is_cancel_requested(db, run_id),
            )
        if cancelled or _is_cancel_requested(db, run_id):
            run = db.get(ScrapeRun, run_id)
            if run is None:
                raise LookupError(f"scrape run {run_id} not found")
            _mark_cancelled(run)
            db.commit()
            db.refresh(run)
            return run
        stats = upsert_drafts_with_stats(db, drafts)
        _apply_stats(run, stats, detail_failures, errors)
    except Exception as exc:
        db.rollback()
        run = db.get(ScrapeRun, run_id)
        if run is None:
            raise
        run.status = "failed"
        run.failed = max(run.failed, 1)
        run.error_summary = str(exc)
        run.finished_at = datetime.now(UTC)
        db.commit()
        logger.exception("scrape_run_failed id=%s source=%s", run_id, run.source)
        return run

    db.commit()
    db.refresh(run)
    return run


def _apply_stats(
    run: ScrapeRun,
    stats: UpsertStats,
    detail_failures: int,
    errors: list[str],
) -> None:
    run.inserted = stats.inserted
    run.updated = stats.updated
    run.skipped = stats.skipped
    run.failed = detail_failures
    run.status = "partial" if detail_failures else "succeeded"
    run.error_summary = "\n".join(errors[:10]) or None
    run.finished_at = datetime.now(UTC)


def _is_cancel_requested(db: Session, run_id: uuid.UUID) -> bool:
    run = db.get(ScrapeRun, run_id)
    if run is None:
        return True
    db.refresh(run)
    return run.status in {"cancel_requested", "cancelled"}


def _mark_cancelled(run: ScrapeRun) -> None:
    run.status = "cancelled"
    run.finished_at = datetime.now(UTC)
    if run.error_summary is None:
        run.error_summary = "Cancelled by user."


async def execute_scrape_runs(db: Session, run_ids: list[uuid.UUID]) -> list[ScrapeRun]:
    completed = []
    for run_id in run_ids:
        completed.append(await execute_scrape_run(db, run_id))
    return completed


def run_scrape_background(
    run_ids: list[uuid.UUID],
    session_factory: Callable[[], Session],
) -> None:
    import asyncio

    with session_factory() as db:
        asyncio.run(execute_scrape_runs(db, run_ids))
