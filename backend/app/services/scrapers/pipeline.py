from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.models.scrape_run import ACTIVE_SCRAPE_RUN_STATUSES, ScrapeRun
from backend.app.services.scrapers.base import BaseScraper, JobListingDraft
from backend.app.services.scrapers.persistence import UpsertStats, upsert_drafts_with_stats
from backend.app.services.scrapers.registry import SCRAPERS, resolve_sources

logger = logging.getLogger(__name__)

# When a description filter is active, request more drafts from the scraper than
# the user asked for so we can still satisfy `limit` after dropping non-matches.
# Capped to keep politeness/rate-limit budgets bounded.
OVER_FETCH_MULTIPLIER = 3
OVER_FETCH_CAP = 200


@dataclass(frozen=True)
class DescriptionFilter:
    """Optional post-`fetch_detail` filter against `JobListingDraft.description`."""

    terms: tuple[str, ...]
    mode: str = "all"
    regex: bool = False

    @classmethod
    def from_optional(
        cls,
        terms: list[str] | None,
        mode: str = "all",
        regex: bool = False,
    ) -> "DescriptionFilter | None":
        if not terms:
            return None
        cleaned = tuple(term for term in (t.strip() for t in terms) if term)
        if not cleaned:
            return None
        if mode not in {"all", "any"}:
            raise ValueError(f"invalid match_mode {mode!r}; expected 'all' or 'any'")
        return cls(terms=cleaned, mode=mode, regex=regex)

    def matches(self, description: str) -> bool:
        if not description:
            return False
        if self.regex:
            try:
                checks = [
                    bool(re.search(term, description, flags=re.IGNORECASE))
                    for term in self.terms
                ]
            except re.error:
                return False
        else:
            haystack = description.lower()
            checks = [term.lower() in haystack for term in self.terms]
        return all(checks) if self.mode == "all" else any(checks)


async def scrape_with_runner(
    scraper: BaseScraper,
    keyword: str,
    limit: int,
    should_cancel: Callable[[], bool] | None = None,
    description_filter: DescriptionFilter | None = None,
) -> tuple[list[JobListingDraft], int, list[str], bool, int]:
    if callable(should_cancel) and should_cancel():
        return [], 0, [], True, 0

    search_limit = (
        min(limit * OVER_FETCH_MULTIPLIER, OVER_FETCH_CAP)
        if description_filter is not None
        else limit
    )
    drafts = await scraper.search(keyword, search_limit)
    if callable(should_cancel) and should_cancel():
        return [], 0, [], True, 0

    enriched: list[JobListingDraft] = []
    failed = 0
    errors: list[str] = []
    skipped_by_filter = 0
    for draft in drafts:
        if callable(should_cancel) and should_cancel():
            return enriched, failed, errors, True, skipped_by_filter
        try:
            detail = await scraper.fetch_detail(draft)
        except Exception as exc:
            failed += 1
            message = f"{draft.source_id}: {exc}"
            errors.append(message)
            logger.warning("scrape_detail_failed source=%s %s", scraper.source, message)
            enriched.append(draft)
            continue
        if description_filter is not None and not description_filter.matches(
            detail.description
        ):
            skipped_by_filter += 1
            continue
        enriched.append(detail)
        if len(enriched) >= limit:
            break
    return enriched, failed, errors, False, skipped_by_filter


def create_scrape_runs(
    db: Session,
    *,
    source: str,
    keyword: str,
    limit: int,
    must_contain: list[str] | None = None,
    match_mode: str = "all",
    regex: bool = False,
) -> list[ScrapeRun]:
    cleaned_terms: list[str] | None
    if must_contain:
        cleaned_terms = [term.strip() for term in must_contain if term and term.strip()]
        if not cleaned_terms:
            cleaned_terms = None
    else:
        cleaned_terms = None
    runs = [
        ScrapeRun(
            source=item,
            keyword=keyword,
            limit=limit,
            status="queued",
            must_contain=cleaned_terms,
            match_mode=match_mode if cleaned_terms else "all",
            regex=regex if cleaned_terms else False,
        )
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
        description_filter = DescriptionFilter.from_optional(
            run.must_contain,
            mode=run.match_mode,
            regex=run.regex,
        )
        async with scraper_cls() as scraper:  # type: ignore[attr-defined]
            (
                drafts,
                detail_failures,
                errors,
                cancelled,
                skipped_by_filter,
            ) = await scrape_with_runner(
                scraper,
                run.keyword,
                run.limit,
                should_cancel=lambda: _is_cancel_requested(db, run_id),
                description_filter=description_filter,
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
        _apply_stats(run, stats, detail_failures, errors, skipped_by_filter)
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
    skipped_by_filter: int = 0,
) -> None:
    run.inserted = stats.inserted
    run.updated = stats.updated
    run.skipped = stats.skipped
    run.failed = detail_failures
    run.skipped_by_filter = skipped_by_filter
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
