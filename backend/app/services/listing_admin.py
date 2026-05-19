"""Admin operations on `job_listings` — bulk deletion with CSV backup.

Mirrors the CSV backup behaviour of scripts/scrape_jobs.py so accidental
deletions can be recovered manually."""

from __future__ import annotations

import csv
import json
import os
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.app.models.job_listing import JobListing

_DEFAULT_BACKUP_DIR = Path.home() / "resumeHelper_data" / "backups"


def _backup_dir() -> Path:
    env_value = os.environ.get("RESUMEHELPER_BACKUP_DIR")
    return Path(env_value).expanduser() if env_value else _DEFAULT_BACKUP_DIR


def _write_backup(listings: list[JobListing]) -> Path:
    if not listings:
        raise ValueError("nothing to back up")
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = backup_dir / f"deletions-{ts}.csv"
    with path.open("w", newline="") as fh:
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
        for row in listings:
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
    return path


def _resolve_targets(
    db: Session,
    *,
    ids: list[uuid.UUID] | None,
    older_than_days: int | None,
    only_unanalyzed: bool,
) -> list[JobListing]:
    query = db.query(JobListing)
    if ids is not None:
        if not ids:
            return []
        query = query.filter(JobListing.id.in_(ids))
    elif older_than_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        query = query.filter(JobListing.scraped_at < cutoff)
        if only_unanalyzed:
            query = query.filter(JobListing.job_analysis_id.is_(None))
    return query.all()


def bulk_delete(
    db: Session,
    *,
    ids: list[uuid.UUID] | None = None,
    older_than_days: int | None = None,
    only_unanalyzed: bool = True,
    force: bool = False,
    backup: bool = True,
) -> tuple[int, list[uuid.UUID], Path | None]:
    """Delete listings matching the target set. Listings with an attached
    analysis are refused unless `force=True`. Returns (deleted_count,
    refused_ids, backup_path)."""
    targets = _resolve_targets(
        db,
        ids=ids,
        older_than_days=older_than_days,
        only_unanalyzed=only_unanalyzed,
    )

    to_delete: list[JobListing] = []
    refused: list[uuid.UUID] = []
    for listing in targets:
        if listing.job_analysis_id is not None and not force:
            refused.append(listing.id)
            continue
        to_delete.append(listing)

    if not to_delete:
        return 0, refused, None

    backup_path = _write_backup(to_delete) if backup else None

    delete_ids = [listing.id for listing in to_delete]
    db.execute(delete(JobListing).where(JobListing.id.in_(delete_ids)))
    db.commit()
    return len(delete_ids), refused, backup_path


def backup_dir_for_tests() -> Path:
    """Exposed so tests can read the resolved backup directory."""
    return _backup_dir()


__all__: Iterable[str] = ("backup_dir_for_tests", "bulk_delete")
