"""JobListing model + BaseScraper interface — issue #39."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.job_listing import JobListing
from backend.app.services.scrapers import BaseScraper, JobListingDraft


@pytest.mark.integration
def test_job_listing_persists(db_session: Session):
    listing = JobListing(
        source="104",
        source_id="abc123",
        title="Backend Engineer",
        company="Acme",
        url="https://www.104.com.tw/job/abc123",
        description="Build APIs.",
    )
    db_session.add(listing)
    db_session.commit()
    assert listing.id is not None
    assert listing.scraped_at is not None
    assert listing.job_analysis_id is None


@pytest.mark.integration
def test_job_listing_unique_source_pair(db_session: Session):
    db_session.add(
        JobListing(
            source="104",
            source_id="dup-id",
            title="A",
            company="X",
            url="https://example.com/a",
            description="d",
        )
    )
    db_session.commit()

    db_session.add(
        JobListing(
            source="104",
            source_id="dup-id",
            title="B",
            company="Y",
            url="https://example.com/b",
            description="d",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.integration
def test_job_listing_same_source_id_different_source_ok(db_session: Session):
    db_session.add(
        JobListing(
            source="104",
            source_id="same-id",
            title="A",
            company="X",
            url="https://example.com/a",
            description="d",
        )
    )
    db_session.add(
        JobListing(
            source="yourator",
            source_id="same-id",
            title="B",
            company="Y",
            url="https://example.com/b",
            description="d",
        )
    )
    db_session.commit()


def test_base_scraper_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseScraper()  # type: ignore[abstract]


def test_job_listing_draft_defaults():
    draft = JobListingDraft(
        source="104",
        source_id="x",
        title="t",
        company="c",
        url="https://example.com/x",
    )
    assert draft.description == ""
    assert draft.raw_json is None
    assert draft.location is None
