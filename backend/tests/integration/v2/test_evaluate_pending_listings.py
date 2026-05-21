from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_listing import JobListing
from backend.app.services.job_queue import AI_JOB_KIND_TAILOR, AI_JOB_STATUS_SUCCEEDED
from backend.app.workers.job_queue import run_job_queue_once


@pytest.mark.integration
def test_evaluate_pending_listings_scores_pending_rows(
    client: TestClient,
    db_session: Session,
):
    profile = client.post(
        "/api/profile",
        json={"skills_text": "Python, FastAPI, PostgreSQL"},
    ).json()["data"]
    target = JobListing(
        source="yourator",
        source_id=f"pending-{uuid.uuid4()}",
        title="Backend Engineer",
        company="Example Co",
        location="Taipei",
        url="https://example.com/jobs/backend",
        description="Build FastAPI services and maintain PostgreSQL systems.",
    )
    other_source = JobListing(
        source="104",
        source_id=f"pending-{uuid.uuid4()}",
        title="Platform Engineer",
        company="Other Co",
        location="Remote",
        url="https://example.com/jobs/platform",
        description="Build platform services.",
    )
    empty_description = JobListing(
        source="yourator",
        source_id=f"pending-empty-{uuid.uuid4()}",
        title="Empty JD",
        company="Example Co",
        location=None,
        url="https://example.com/jobs/empty",
        description="   ",
    )
    db_session.add_all([target, other_source, empty_description])
    db_session.commit()

    response = client.post(
        "/api/evaluate/pending-listings",
        json={"profile_id": profile["id"], "source": "yourator", "limit": 10},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["failed"] == 0
    assert data["skipped"] == 0
    assert data["blocked"] == 0
    assert data["tailoring_blocked"] == 0
    assert data["estimated_total_tokens"] > 0
    result = data["results"][0]
    assert result["listing_id"] == str(target.id)
    assert result["job_analysis_id"]
    assert result["tailoring_job_id"]
    assert result["tailoring_status"] == "queued"

    db_session.expire_all()
    analysis_id = db_session.get(JobListing, target.id).job_analysis_id
    assert analysis_id is not None
    assert db_session.get(JobListing, other_source.id).job_analysis_id is None
    assert db_session.get(JobListing, empty_description.id).job_analysis_id is None

    worker_result = run_job_queue_once(
        llm=client.app.state.llm_client,  # type: ignore[union-attr]
        session_factory=client.app.state.session_factory,  # type: ignore[union-attr]
        kind=AI_JOB_KIND_TAILOR,
    )
    assert worker_result is not None
    assert worker_result.status == AI_JOB_STATUS_SUCCEEDED

    db_session.expire_all()
    assert (
        db_session.query(GeneratedResume)
        .filter(GeneratedResume.job_analysis_id == analysis_id)
        .count()
        == 1
    )


@pytest.mark.integration
def test_evaluate_pending_quota_guard_blocks_without_writes(
    client: TestClient,
    db_session: Session,
):
    profile = client.post(
        "/api/profile",
        json={"skills_text": "Python, FastAPI, PostgreSQL"},
    ).json()["data"]
    listings = [
        JobListing(
            source="yourator",
            source_id=f"pending-{uuid.uuid4()}",
            title=f"Backend Engineer {idx}",
            company="Example Co",
            location="Taipei",
            url=f"https://example.com/jobs/backend-{idx}",
            description="Build FastAPI services and maintain PostgreSQL systems.",
        )
        for idx in range(2)
    ]
    db_session.add_all(listings)
    db_session.commit()

    settings = get_settings()
    original_limit = settings.max_evaluate_pending_items
    settings.max_evaluate_pending_items = 1
    try:
        response = client.post(
            "/api/evaluate/pending-listings",
            json={"profile_id": profile["id"], "source": "yourator", "limit": 10},
        )
    finally:
        settings.max_evaluate_pending_items = original_limit

    assert response.status_code == 429
    payload = response.json()
    assert payload["error"]["code"] == "ai_batch_item_limit_exceeded"
    assert payload["error"]["details"]["workflow"] == "evaluate_listings"
    assert payload["error"]["details"]["items"] == 2

    db_session.expire_all()
    for listing in listings:
        assert db_session.get(JobListing, listing.id).job_analysis_id is None
