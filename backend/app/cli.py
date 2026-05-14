from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.app.config import get_settings
from backend.app.db import SessionLocal
from backend.app.services.batch_evaluator import (
    ListingEvaluationSummary,
    evaluate_pending_listings,
)
from backend.app.services.eval_harness import (
    load_evaluation_fixture_set,
    run_evaluation_harness,
    write_report_json,
    write_report_markdown,
)
from backend.app.services.llm import LLMClient, LLMUnavailableError
from backend.app.services.llm.audit import llm_metadata
from backend.app.services.llm.factory import create_llm_client
from backend.app.services.llm.fake import FakeLLMClient
from backend.app.services.llm.prompt_registry import (
    STEP_EVALUATE,
    STEP_TAILOR,
    prompt_version_for_step,
)
from backend.app.services.prompt_replay import (
    compare_evaluation_prompt_versions,
    write_prompt_replay_json,
    write_prompt_replay_markdown,
)
from backend.app.services.scrapers.pipeline import create_scrape_runs, execute_scrape_runs
from backend.app.services.scrapers.registry import SCRAPERS, resolve_sources
from backend.app.services.tailor_harness import (
    load_tailor_fixture_set,
    run_tailor_harness,
    write_tailor_report_json,
    write_tailor_report_markdown,
)
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
                source=None
                if args.source in {"all", "all_with_linkedin"}
                else args.source,
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
                prompt_version=prompt_version_for_step(
                    STEP_TAILOR,
                    settings=settings,
                ),
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


def _eval_harness(args: argparse.Namespace) -> int:
    prompt_version = _eval_harness_prompt_version(args.backend, args.prompt_version)
    try:
        llm = _create_eval_harness_llm(args.backend, args.model)
        fixture_set, fixture_path = load_evaluation_fixture_set(
            Path(args.fixtures) if args.fixtures else None
        )
    except (LLMUnavailableError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    report = run_evaluation_harness(
        llm=llm,
        fixture_set=fixture_set,
        fixture_path=fixture_path,
        backend=args.backend,
        prompt_version=prompt_version,
    )

    if args.report_json:
        write_report_json(report, Path(args.report_json))
    if args.report_md:
        write_report_markdown(report, Path(args.report_md))

    if not args.quiet:
        print(
            f"eval-harness backend={args.backend} "
            f"fixtures={fixture_path} passed={report.passed}/{report.total}"
        )
        for result in report.results:
            outcome = "PASS" if result.passed else "FAIL"
            print(
                f"  {result.id}: {outcome} "
                f"score={result.score} status={result.status}"
            )
            for failure in result.failures:
                print(f"    - {failure}")

    return 0 if report.failed == 0 else 1


def _tailor_harness(args: argparse.Namespace) -> int:
    prompt_version = _tailor_harness_prompt_version(args.backend, args.prompt_version)
    try:
        llm = _create_eval_harness_llm(args.backend, args.model)
        fixture_set, fixture_path = load_tailor_fixture_set(
            Path(args.fixtures) if args.fixtures else None
        )
    except (LLMUnavailableError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    report = run_tailor_harness(
        llm=llm,
        fixture_set=fixture_set,
        fixture_path=fixture_path,
        backend=args.backend,
        prompt_version=prompt_version,
    )

    if args.report_json:
        write_tailor_report_json(report, Path(args.report_json))
    if args.report_md:
        write_tailor_report_markdown(report, Path(args.report_md))

    if not args.quiet:
        print(
            f"tailor-harness backend={args.backend} "
            f"fixtures={fixture_path} passed={report.passed}/{report.total}"
        )
        for result in report.results:
            outcome = "PASS" if result.passed else "FAIL"
            print(
                f"  {result.id}: {outcome} "
                f"chars={result.tailored_resume_chars} "
                f"suggestions={result.suggestions_count}"
            )
            for failure in result.failures:
                print(f"    - {failure}")

    return 0 if report.failed == 0 else 1


def _prompt_replay(args: argparse.Namespace) -> int:
    old_prompt_version = prompt_version_for_step(
        STEP_EVALUATE,
        override=args.old_prompt_version,
    )
    new_prompt_version = prompt_version_for_step(
        STEP_EVALUATE,
        override=args.new_prompt_version,
    )
    try:
        llm = _create_eval_harness_llm(args.backend, args.model)
        backend, model = llm_metadata(llm)
        fixture_set, fixture_path = load_evaluation_fixture_set(
            Path(args.fixtures) if args.fixtures else None
        )
        report = compare_evaluation_prompt_versions(
            llm=llm,
            fixture_set=fixture_set,
            fixture_path=fixture_path,
            backend=backend,
            model=model,
            old_prompt_version=old_prompt_version,
            new_prompt_version=new_prompt_version,
            case_ids=args.case_id,
        )
    except (LLMUnavailableError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.report_json:
        write_prompt_replay_json(report, Path(args.report_json))
    if args.report_md:
        write_prompt_replay_markdown(report, Path(args.report_md))

    if not args.quiet:
        print(
            f"prompt-replay backend={report.backend} model={report.model or ''} "
            f"old={report.old_prompt_version} new={report.new_prompt_version} "
            f"changed={report.changed}/{report.total} "
            f"new_passed={report.new_passed}/{report.total}"
        )
        for delta in report.deltas:
            score_delta = "" if delta.score_delta is None else f"{delta.score_delta:+d}"
            old_result = "PASS" if delta.old_passed else "FAIL"
            new_result = "PASS" if delta.new_passed else "FAIL"
            print(
                f"  {delta.id}: score={delta.old_score}->{delta.new_score} "
                f"delta={score_delta} status={delta.old_status}->{delta.new_status} "
                f"{old_result}->{new_result}"
            )

    return 0 if report.new_failed == 0 else 1


def _create_eval_harness_llm(backend: str, model: str | None) -> LLMClient:
    if backend == "fake":
        return FakeLLMClient()
    if backend == "configured":
        return create_llm_client()
    if backend == "anthropic":
        from backend.app.services.llm.anthropic import AnthropicLLMClient

        return AnthropicLLMClient()
    if backend == "claude-cli":
        from backend.app.services.llm.claude_cli import ClaudeCLIClient

        return ClaudeCLIClient(model=model or get_settings().llm_model)
    raise LLMUnavailableError(f"unsupported eval harness backend: {backend}")


def _eval_harness_prompt_version(backend: str, override: str | None) -> str:
    if backend == "fake":
        return prompt_version_for_step(STEP_EVALUATE, override=override)
    return prompt_version_for_step(STEP_EVALUATE, override=override)


def _tailor_harness_prompt_version(_backend: str, override: str | None) -> str:
    return prompt_version_for_step(STEP_TAILOR, override=override)


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

    eval_harness = subparsers.add_parser(
        "eval-harness",
        help="run deterministic LLM output contract and routing fixtures",
    )
    eval_harness.add_argument(
        "--backend",
        choices=["fake", "configured", "anthropic", "claude-cli"],
        default="fake",
        help="LLM backend used by the harness",
    )
    eval_harness.add_argument("--model", default=None, help="model override for claude-cli")
    eval_harness.add_argument(
        "--prompt-version",
        default=None,
        help="prompt version passed into the LLM client",
    )
    eval_harness.add_argument(
        "--fixtures",
        default=None,
        help="fixture JSON path; defaults to backend/evals/fixtures/evaluate_cases.json",
    )
    eval_harness.add_argument("--report-json", default=None, help="write JSON report")
    eval_harness.add_argument("--report-md", default=None, help="write Markdown report")
    eval_harness.add_argument("--quiet", action="store_true", help="only return exit code")
    eval_harness.set_defaults(func=_eval_harness)

    tailor_harness = subparsers.add_parser(
        "tailor-harness",
        help="run deterministic tailoring output contract and factuality fixtures",
    )
    tailor_harness.add_argument(
        "--backend",
        choices=["fake", "configured", "anthropic", "claude-cli"],
        default="fake",
        help="LLM backend used by the harness",
    )
    tailor_harness.add_argument(
        "--model",
        default=None,
        help="model override for claude-cli",
    )
    tailor_harness.add_argument(
        "--prompt-version",
        default=None,
        help="prompt version recorded in the harness report",
    )
    tailor_harness.add_argument(
        "--fixtures",
        default=None,
        help="fixture JSON path; defaults to backend/evals/fixtures/tailor_cases.json",
    )
    tailor_harness.add_argument("--report-json", default=None, help="write JSON report")
    tailor_harness.add_argument("--report-md", default=None, help="write Markdown report")
    tailor_harness.add_argument(
        "--quiet",
        action="store_true",
        help="only return exit code",
    )
    tailor_harness.set_defaults(func=_tailor_harness)

    prompt_replay = subparsers.add_parser(
        "prompt-replay",
        help="compare eval fixture output across two evaluate prompt versions",
    )
    prompt_replay.add_argument(
        "--backend",
        choices=["fake", "configured", "anthropic", "claude-cli"],
        default="fake",
        help="LLM backend used by the replay",
    )
    prompt_replay.add_argument("--model", default=None, help="model override for claude-cli")
    prompt_replay.add_argument(
        "--old-prompt-version",
        default=None,
        help="old evaluate prompt version; defaults to configured evaluate prompt",
    )
    prompt_replay.add_argument(
        "--new-prompt-version",
        required=True,
        help="new evaluate prompt version to compare",
    )
    prompt_replay.add_argument(
        "--case-id",
        action="append",
        default=None,
        help="fixture case id to replay; repeat to select multiple cases",
    )
    prompt_replay.add_argument(
        "--fixtures",
        default=None,
        help="fixture JSON path; defaults to backend/evals/fixtures/evaluate_cases.json",
    )
    prompt_replay.add_argument("--report-json", default=None, help="write JSON report")
    prompt_replay.add_argument("--report-md", default=None, help="write Markdown report")
    prompt_replay.add_argument("--quiet", action="store_true", help="only return exit code")
    prompt_replay.set_defaults(func=_prompt_replay)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
