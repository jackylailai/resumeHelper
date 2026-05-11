from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_listing import JobListing


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
    result = data["results"][0]
    assert result["listing_id"] == str(target.id)
    assert result["job_analysis_id"]

    db_session.expire_all()
    analysis_id = db_session.get(JobListing, target.id).job_analysis_id
    assert analysis_id is not None
    assert db_session.get(JobListing, other_source.id).job_analysis_id is None
    assert db_session.get(JobListing, empty_description.id).job_analysis_id is None
    assert (
        db_session.query(GeneratedResume)
        .filter(GeneratedResume.job_analysis_id == analysis_id)
        .count()
        == 1
    )
