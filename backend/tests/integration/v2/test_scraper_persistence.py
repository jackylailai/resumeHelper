"""scrapers/persistence.upsert_drafts — integration test against real Postgres."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_listing import JobListing
from backend.app.services.scrapers.base import JobListingDraft
from backend.app.services.scrapers.persistence import (
    upsert_drafts,
    upsert_drafts_with_stats,
)


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
def test_upsert_drafts_updates_existing_rows(db_session: Session):
    upsert_drafts(db_session, [_draft("dup", title="first")])
    row = db_session.execute(
        select(JobListing).where(JobListing.source_id == "dup")
    ).scalar_one()
    analysis = JobAnalysis(
        jd_hash=uuid4_hex("dup"),
        jd_full_text="old description",
        score=70,
        threshold_met=True,
        status="needs_tailoring",
    )
    db_session.add(analysis)
    db_session.flush()
    row.job_analysis_id = analysis.id
    db_session.commit()

    stats = upsert_drafts_with_stats(
        db_session,
        [_draft("dup", title="second"), _draft("new")],
    )
    assert stats.inserted == 1
    assert stats.updated == 1
    assert stats.skipped == 0
    row = db_session.execute(
        select(JobListing).where(JobListing.source_id == "dup")
    ).scalar_one()
    assert row.title == "second"
    assert row.changed_at is not None
    assert row.job_analysis_id is None


@pytest.mark.integration
def test_upsert_drafts_empty_list(db_session: Session):
    assert upsert_drafts(db_session, []) == 0


def uuid4_hex(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"
