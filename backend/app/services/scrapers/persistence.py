from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.models.job_listing import JobListing
from backend.app.services.scrapers.base import JobListingDraft


@dataclass(frozen=True)
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


def upsert_drafts(session: Session, drafts: Iterable[JobListingDraft]) -> int:
    """Insert drafts as JobListing rows and return newly-inserted count."""
    return upsert_drafts_with_stats(session, drafts).inserted


def upsert_drafts_with_stats(
    session: Session,
    drafts: Iterable[JobListingDraft],
) -> UpsertStats:
    """Insert or update drafts, deduping by (source, source_id)."""
    inserted = 0
    updated = 0
    skipped = 0
    seen: set[tuple[str, str]] = set()
    now = datetime.now(UTC)

    for draft in drafts:
        row = asdict(draft)
        row["source"] = row.get("source") or ""
        row["source_id"] = row.get("source_id") or ""
        row["description"] = row.get("description") or ""
        key = (row["source"], row["source_id"])
        if not key[0] or not key[1] or key in seen:
            skipped += 1
            continue
        seen.add(key)

        existing = (
            session.query(JobListing)
            .filter(
                JobListing.source == row["source"],
                JobListing.source_id == row["source_id"],
            )
            .first()
        )
        if existing is None:
            session.add(JobListing(**row, changed_at=now))
            inserted += 1
            continue

        changed = False
        material_changed = False
        material_fields = ("title", "company", "location", "url", "description")
        for field in (*material_fields, "raw_json"):
            value = row.get(field)
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
                if field in material_fields:
                    material_changed = True
        existing.scraped_at = now
        if changed:
            existing.changed_at = now
            if material_changed:
                existing.job_analysis_id = None
            updated += 1
        else:
            skipped += 1

    session.commit()
    return UpsertStats(inserted=inserted, updated=updated, skipped=skipped)
