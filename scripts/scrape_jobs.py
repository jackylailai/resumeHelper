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
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.scrapers.base import BaseScraper, JobListingDraft
from backend.app.services.scrapers.persistence import upsert_drafts
from backend.app.services.scrapers.scraper_104 import Scraper104
from backend.app.services.scrapers.scraper_yourator import ScraperYourator

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
