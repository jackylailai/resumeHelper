"""Bulk delete on /api/job-listings/bulk-delete — issue #150."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_listing import JobListing


def _exists(session: Session, listing_id: uuid.UUID) -> bool:
    """Bypass the identity map for cross-session deletion checks."""
    return session.query(JobListing).filter_by(id=listing_id).first() is not None


def _make_listing(
    *,
    source_id: str,
    description: str = "Build APIs.",
    scraped_at: datetime | None = None,
    job_analysis_id: uuid.UUID | None = None,
) -> JobListing:
    listing = JobListing(
        source="104",
        source_id=source_id,
        title="Test role",
        company="Example",
        url=f"https://www.104.com.tw/job/{source_id}",
        description=description,
        job_analysis_id=job_analysis_id,
    )
    if scraped_at is not None:
        listing.scraped_at = scraped_at
    return listing


@pytest.mark.integration
def test_bulk_delete_by_ids_unanalyzed(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RESUMEHELPER_BACKUP_DIR", str(tmp_path))
    listings = [
        _make_listing(source_id=f"bd-ids-{uuid.uuid4()}") for _ in range(3)
    ]
    db_session.add_all(listings)
    db_session.commit()
    ids = [str(listing.id) for listing in listings]

    response = client.post(
        "/api/job-listings/bulk-delete",
        json={"ids": ids},
    )
    assert response.status_code == 200, response.text
    db_session.expire_all()
    data = response.json()["data"]
    assert data["deleted"] == 3
    assert data["refused"] == 0
    assert data["backup_path"] is not None
    assert Path(data["backup_path"]).exists()

    remaining = (
        db_session.query(JobListing)
        .filter(JobListing.id.in_([uuid.UUID(i) for i in ids]))
        .count()
    )
    assert remaining == 0


@pytest.mark.integration
def test_bulk_delete_refuses_analyzed_without_force(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RESUMEHELPER_BACKUP_DIR", str(tmp_path))
    analysis = JobAnalysis(
        jd_hash=f"hash-{uuid.uuid4()}",
        jd_full_text="JD here",
        score=70,
        explanation="ok",
        status="needs_tailoring",
    )
    db_session.add(analysis)
    db_session.commit()

    analyzed = _make_listing(
        source_id=f"bd-an-{uuid.uuid4()}",
        job_analysis_id=analysis.id,
    )
    plain = _make_listing(source_id=f"bd-plain-{uuid.uuid4()}")
    db_session.add_all([analyzed, plain])
    db_session.commit()

    analyzed_id = analyzed.id
    plain_id = plain.id
    response = client.post(
        "/api/job-listings/bulk-delete",
        json={"ids": [str(analyzed_id), str(plain_id)]},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["deleted"] == 1
    assert data["refused"] == 1
    assert data["refused_ids"] == [str(analyzed_id)]

    # Bypass the identity map — those objects were deleted in another session.
    db_session.expunge_all()
    assert _exists(db_session, analyzed_id) is True
    assert _exists(db_session, plain_id) is False


@pytest.mark.integration
def test_bulk_delete_force_deletes_analyzed(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RESUMEHELPER_BACKUP_DIR", str(tmp_path))
    analysis = JobAnalysis(
        jd_hash=f"hash-{uuid.uuid4()}",
        jd_full_text="JD here",
        score=80,
        explanation="ok",
        status="ready_to_submit",
    )
    db_session.add(analysis)
    db_session.commit()

    analyzed = _make_listing(
        source_id=f"bd-force-{uuid.uuid4()}",
        job_analysis_id=analysis.id,
    )
    db_session.add(analyzed)
    db_session.commit()

    analyzed_id = analyzed.id
    analysis_id = analysis.id
    response = client.post(
        "/api/job-listings/bulk-delete",
        json={"ids": [str(analyzed_id)], "force": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["deleted"] == 1
    assert data["refused"] == 0
    db_session.expunge_all()
    assert _exists(db_session, analyzed_id) is False
    # The JobAnalysis row survives (FK is SET NULL on delete).
    assert db_session.query(JobAnalysis).filter_by(id=analysis_id).first() is not None


@pytest.mark.integration
def test_bulk_delete_by_older_than_days(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RESUMEHELPER_BACKUP_DIR", str(tmp_path))
    old = _make_listing(
        source_id=f"bd-old-{uuid.uuid4()}",
        scraped_at=datetime.now(UTC) - timedelta(days=60),
    )
    fresh = _make_listing(
        source_id=f"bd-new-{uuid.uuid4()}",
        scraped_at=datetime.now(UTC) - timedelta(days=5),
    )
    db_session.add_all([old, fresh])
    db_session.commit()

    old_id = old.id
    fresh_id = fresh.id
    response = client.post(
        "/api/job-listings/bulk-delete",
        json={"older_than_days": 30, "only_unanalyzed": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["deleted"] == 1
    db_session.expunge_all()
    assert _exists(db_session, old_id) is False
    assert _exists(db_session, fresh_id) is True


@pytest.mark.integration
def test_bulk_delete_requires_exactly_one_target(
    client: TestClient,
):
    both = client.post(
        "/api/job-listings/bulk-delete",
        json={"ids": [str(uuid.uuid4())], "older_than_days": 30},
    )
    assert both.status_code == 422

    neither = client.post(
        "/api/job-listings/bulk-delete",
        json={},
    )
    assert neither.status_code == 422


@pytest.mark.integration
def test_bulk_delete_empty_ids_returns_zero(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RESUMEHELPER_BACKUP_DIR", str(tmp_path))
    response = client.post(
        "/api/job-listings/bulk-delete",
        json={"ids": []},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["deleted"] == 0
    assert data["backup_path"] is None
