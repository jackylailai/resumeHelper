"""scrapers/persistence.upsert_drafts — integration test against real Postgres."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.job_listing import JobListing
from backend.app.services.scrapers.base import JobListingDraft
from backend.app.services.scrapers.persistence import upsert_drafts


def _draft(source_id: str, title: str = "t") -> JobListingDraft:
    return JobListingDraft(
        source="104",
        source_id=source_id,
        title=title,
        company="Acme",
        url=f"https://www.104.com.tw/job/{source_id}",
        description="d",
    )


@pytest.mark.integration
def test_upsert_drafts_inserts_new(db_session: Session):
    inserted = upsert_drafts(db_session, [_draft("a"), _draft("b")])
    assert inserted == 2
    rows = db_session.execute(
        select(JobListing).where(JobListing.source == "104")
    ).scalars().all()
    assert {r.source_id for r in rows} >= {"a", "b"}


@pytest.mark.integration
def test_upsert_drafts_skips_duplicates(db_session: Session):
    upsert_drafts(db_session, [_draft("dup", title="first")])
    inserted = upsert_drafts(db_session, [_draft("dup", title="second"), _draft("new")])
    assert inserted == 1  # only "new" is added; "dup" skipped
    row = db_session.execute(
        select(JobListing).where(JobListing.source_id == "dup")
    ).scalar_one()
    assert row.title == "first"  # original row was not overwritten


@pytest.mark.integration
def test_upsert_drafts_empty_list(db_session: Session):
    assert upsert_drafts(db_session, []) == 0
