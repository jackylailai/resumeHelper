#!/usr/bin/env python
"""Scrape jobs from one or more sources and persist drafts to the DB.

This wrapper keeps the CSV backup behavior for local safety. The canonical
pipeline entrypoint is `python -m backend.app.cli scrape`.

Examples:
    python scripts/scrape_jobs.py --keyword "backend engineer" --limit 25 --site 104
    python scripts/scrape_jobs.py --keyword "python" --limit 25 --site 104,yourator
    python scripts/scrape_jobs.py --keyword "backend engineer" --limit 10 --site linkedin
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db import SessionLocal
from backend.app.models.job_listing import JobListing
from backend.app.services.scrapers.pipeline import create_scrape_runs, execute_scrape_runs
from backend.app.services.scrapers.registry import SCRAPERS

_DEFAULT_BACKUP_DIR = Path.home() / "resumeHelper_data" / "backups"
BACKUP_DIR = Path(
    os.environ.get("RESUMEHELPER_BACKUP_DIR") or _DEFAULT_BACKUP_DIR
).expanduser()


async def run(keyword: str, limit: int, sites: list[str]) -> int:
    total_inserted = 0
    with SessionLocal() as session:
        for site in sites:
            print(f"== {site} == keyword={keyword!r} limit={limit}")
            runs = create_scrape_runs(
                session,
                source=site,
                keyword=keyword.strip(),
                limit=limit,
            )
            completed = await execute_scrape_runs(session, [run.id for run in runs])
            for run in completed:
                total_inserted += run.inserted
                print(
                    f"  {run.status}: inserted={run.inserted} "
                    f"updated={run.updated} skipped={run.skipped} failed={run.failed}"
                )
                if run.error_summary:
                    print(f"  errors: {run.error_summary}", file=sys.stderr)

    print(f"\nTotal new rows inserted: {total_inserted}")
    _write_backup()
    return total_inserted


def _write_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / f"job_listings-{ts}.csv"
    with SessionLocal() as session, backup_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "id",
            "source",
            "source_id",
            "title",
            "company",
            "location",
            "url",
            "description",
            "raw_json",
            "scraped_at",
            "changed_at",
            "job_analysis_id",
        ])
        for row in session.query(JobListing).order_by(JobListing.scraped_at).all():
            writer.writerow([
                str(row.id),
                row.source,
                row.source_id,
                row.title,
                row.company,
                row.location or "",
                row.url,
                row.description,
                "" if row.raw_json is None else json.dumps(row.raw_json),
                row.scraped_at.isoformat(),
                "" if row.changed_at is None else row.changed_at.isoformat(),
                "" if row.job_analysis_id is None else str(row.job_analysis_id),
            ])
    print(f"Backup written to {backup_path}")
    return backup_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--keyword", required=True, help="search keyword")
    parser.add_argument("--limit", type=int, default=25, help="per-site limit")
    parser.add_argument(
        "--site",
        default="104,yourator",
        help=(
            f"comma-separated sites; valid: {list(SCRAPERS)} "
            "(default: 104,yourator; linkedin is opt-in)"
        ),
    )
    args = parser.parse_args(argv)

    keyword = args.keyword.strip()
    if not keyword:
        print("keyword must not be blank", file=sys.stderr)
        return 2

    sites = [s.strip() for s in args.site.split(",") if s.strip()]
    unknown = [s for s in sites if s not in SCRAPERS]
    if unknown:
        print(f"unknown site(s): {unknown}; valid: {list(SCRAPERS)}", file=sys.stderr)
        return 2

    asyncio.run(run(keyword, args.limit, sites))
    return 0


if __name__ == "__main__":
    sys.exit(main())
