#!/usr/bin/env python
"""Scrape jobs from one or more sources and persist drafts to the DB.

Examples:
    python scripts/scrape_jobs.py --keyword "後端工程師" --limit 25 --site 104
    python scripts/scrape_jobs.py --keyword "後端工程師" --limit 25 --site 104,yourator

Run from project root with the .venv that scripts/test.sh creates:
    ./.venv/bin/python scripts/scrape_jobs.py --keyword "後端工程師" --limit 25
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
from backend.app.services.scrapers.base import BaseScraper, JobListingDraft
from backend.app.services.scrapers.persistence import upsert_drafts
from backend.app.services.scrapers.scraper_104 import Scraper104
from backend.app.services.scrapers.scraper_yourator import ScraperYourator

_DEFAULT_BACKUP_DIR = Path.home() / "resumeHelper_data" / "backups"
BACKUP_DIR = Path(
    os.environ.get("RESUMEHELPER_BACKUP_DIR") or _DEFAULT_BACKUP_DIR
).expanduser()

SCRAPERS: dict[str, type[BaseScraper]] = {
    "104": Scraper104,
    "yourator": ScraperYourator,
}


async def _scrape_one(
    scraper: BaseScraper, keyword: str, limit: int
) -> list[JobListingDraft]:
    drafts = await scraper.search(keyword, limit)
    print(f"  search returned {len(drafts)} drafts; fetching detail pages...")
    enriched: list[JobListingDraft] = []
    for d in drafts:
        try:
            enriched.append(await scraper.fetch_detail(d))
        except Exception as exc:  # noqa: BLE001 — best-effort enrichment
            print(f"    detail fetch failed for {d.source_id}: {exc}", file=sys.stderr)
            enriched.append(d)
    return enriched


async def run(keyword: str, limit: int, sites: list[str]) -> int:
    total_inserted = 0
    with SessionLocal() as session:
        for site in sites:
            print(f"== {site} == keyword={keyword!r} limit={limit}")
            cls = SCRAPERS[site]
            async with cls() as scraper:  # type: ignore[attr-defined]
                drafts = await _scrape_one(scraper, keyword, limit)
            inserted = upsert_drafts(session, drafts)
            total_inserted += inserted
            print(f"  inserted {inserted} new rows ({len(drafts)} drafts seen)")
    print(f"\nTotal new rows inserted: {total_inserted}")

    # Snapshot the full job_listings table to CSV so the data survives even
    # if the DB is later dropped, truncated, or accidentally wiped by a
    # misbehaving test. Restore via:
    #   psql -c "\copy job_listings FROM 'path.csv' CSV HEADER"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / f"job_listings-{ts}.csv"
    with SessionLocal() as session, backup_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "id", "source", "source_id", "title", "company", "location",
            "url", "description", "raw_json", "scraped_at", "job_analysis_id",
        ])
        for row in session.query(JobListing).order_by(JobListing.scraped_at).all():
            writer.writerow([
                str(row.id), row.source, row.source_id, row.title, row.company,
                row.location or "", row.url, row.description,
                "" if row.raw_json is None else json.dumps(row.raw_json),
                row.scraped_at.isoformat(),
                "" if row.job_analysis_id is None else str(row.job_analysis_id),
            ])
    print(f"Backup written → {backup_path}")

    return total_inserted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keyword", required=True, help="search keyword (e.g. '後端工程師')")
    ap.add_argument("--limit", type=int, default=25, help="per-site limit (default: 25)")
    ap.add_argument(
        "--site",
        default="104,yourator",
        help=f"comma-separated sites; valid: {list(SCRAPERS)} (default: all)",
    )
    args = ap.parse_args(argv)

    sites = [s.strip() for s in args.site.split(",") if s.strip()]
    unknown = [s for s in sites if s not in SCRAPERS]
    if unknown:
        print(f"unknown site(s): {unknown}; valid: {list(SCRAPERS)}", file=sys.stderr)
        return 2

    asyncio.run(run(args.keyword, args.limit, sites))
    return 0


if __name__ == "__main__":
    sys.exit(main())
