from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.models.job_listing import JobListing
from backend.app.services.scrapers.base import JobListingDraft


def upsert_drafts(session: Session, drafts: Iterable[JobListingDraft]) -> int:
    """Insert drafts as JobListing rows, skipping rows that collide on (source, source_id).

    Returns the number of newly-inserted rows. Uses Postgres ON CONFLICT DO NOTHING.
    """
    rows = []
    for draft in drafts:
        row = asdict(draft)
        # description is required NOT NULL on the table — guarantee a string
        row["description"] = row.get("description") or ""
        rows.append(row)
    if not rows:
        return 0
    stmt = (
        insert(JobListing)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_job_listings_source")
        .returning(JobListing.id)
    )
    result = session.execute(stmt)
    inserted = result.scalars().all()
    session.commit()
    return len(inserted)
