from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from backend.app.config import get_settings
from backend.app.db import SessionLocal
from backend.app.services.batch_evaluator import (
    ListingEvaluationSummary,
    evaluate_pending_listings,
)
from backend.app.services.llm import LLMUnavailableError
from backend.app.services.llm.factory import create_llm_client
from backend.app.services.scrapers.pipeline import create_scrape_runs, execute_scrape_runs
from backend.app.services.scrapers.registry import SCRAPERS, resolve_sources
from backend.app.workers.tailor import run_tailoring


def _source_help() -> str:
    return f"source to scrape; valid: {', '.join(SCRAPERS)}, all, or all_with_linkedin"


async def _scrape(args: argparse.Namespace) -> int:
    keyword = args.keyword.strip()
    if not keyword:
        print("keyword must not be blank", file=sys.stderr)
        return 2

    try:
        resolve_sources(args.source)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    with SessionLocal() as db:
        runs = create_scrape_runs(
            db,
            source=args.source,
            keyword=keyword,
            limit=args.limit,
        )
        completed = await execute_scrape_runs(db, [run.id for run in runs])

    if not args.quiet:
        for run in completed:
            print(
                f"{run.source}: {run.status} "
                f"inserted={run.inserted} updated={run.updated} "
                f"skipped={run.skipped} failed={run.failed}"
            )
            if run.error_summary:
                print(f"  errors: {run.error_summary}")

    if args.evaluate:
        return _evaluate_listings(
            argparse.Namespace(
                source=None if args.source == "all" else args.source,
                profile_id=args.profile_id,
                limit=args.evaluate_limit,
                no_tailor=args.no_tailor,
                quiet=args.quiet,
            )
        )

    return 0


def _evaluate_listings(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        llm = create_llm_client()
    except LLMUnavailableError as exc:
        print(f"LLM unavailable: {exc}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            summary = evaluate_pending_listings(
                db,
                llm=llm,
                settings=settings,
                profile_id=args.profile_id,
                source=args.source,
                limit=args.limit,
            )
        except LookupError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if not args.quiet:
        _print_eval_summary(args.source, summary)
    if not args.no_tailor and summary.tailoring_job_ids:
        for job_id in summary.tailoring_job_ids:
            run_tailoring(
                job_analysis_id=job_id,
                llm=llm,
                prompt_version=settings.llm_prompt_version,
                session_factory=SessionLocal,
            )
        if not args.quiet:
            print(f"tailored={len(summary.tailoring_job_ids)}")
    return 0 if summary.failed == 0 else 1


def _print_eval_summary(
    source: str | None,
    summary: ListingEvaluationSummary,
) -> None:
    scope = source or "all"
    print(
        f"evaluated source={scope} total={summary.total} "
        f"succeeded={summary.succeeded} failed={summary.failed}"
    )
    for result in summary.results:
        if result.error:
            print(f"  {result.listing_id}: error={result.error}")
            continue
        print(
            f"  {result.listing_id}: score={result.score} "
            f"status={result.status} cached={result.cached}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape = subparsers.add_parser("scrape", help="scrape jobs into job_listings")
    scrape.add_argument("--source", default="all", help=_source_help())
    scrape.add_argument("--keyword", required=True, help="search keyword")
    scrape.add_argument("--limit", type=int, default=25, help="per-source listing limit")
    scrape.add_argument(
        "--evaluate",
        action="store_true",
        help="evaluate pending listings after scraping",
    )
    scrape.add_argument("--profile-id", type=int, default=None)
    scrape.add_argument(
        "--evaluate-limit",
        type=int,
        default=100,
        help="max pending listings to evaluate after scraping",
    )
    scrape.add_argument(
        "--no-tailor",
        action="store_true",
        help="do not synchronously tailor needs_tailoring results",
    )
    scrape.add_argument("--quiet", action="store_true", help="reduce cron output")
    scrape.set_defaults(func=lambda args: asyncio.run(_scrape(args)))

    evaluate = subparsers.add_parser(
        "evaluate-listings",
        help="score pending job_listings and link job_analyses",
    )
    evaluate.add_argument("--profile-id", type=int, default=None)
    evaluate.add_argument("--source", default=None, help="optional source filter")
    evaluate.add_argument("--limit", type=int, default=100)
    evaluate.add_argument(
        "--no-tailor",
        action="store_true",
        help="do not synchronously tailor needs_tailoring results",
    )
    evaluate.add_argument("--quiet", action="store_true", help="reduce cron output")
    evaluate.set_defaults(func=_evaluate_listings)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
