from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.job_listing import JobListing


@pytest.mark.integration
def test_evaluate_by_listings_scores_and_links_job_analysis(
    client: TestClient,
    db_session: Session,
):
    profile = client.post(
        "/api/profile",
        json={"skills_text": "Python, FastAPI, PostgreSQL"},
    ).json()["data"]
    listing = JobListing(
        source="yourator",
        source_id=f"batch-{uuid.uuid4()}",
        title="Backend Engineer",
        company="Example Co",
        location="Taipei",
        url="https://example.com/jobs/backend",
        description="Build FastAPI services and maintain PostgreSQL systems.",
    )
    db_session.add(listing)
    db_session.commit()

    response = client.post(
        "/api/evaluate/by-listings",
        json={"profile_id": profile["id"], "job_listing_ids": [str(listing.id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["total"] == 1
    assert body["data"]["succeeded"] == 1
    result = body["data"]["results"][0]
    assert result["listing_id"] == str(listing.id)
    assert result["job_analysis_id"]
    assert 0 <= result["score"] <= 100
    assert result["status"] in ("ready_to_submit", "needs_tailoring", "skip")
    assert result["error"] is None

    db_session.expire(listing)
    assert listing.job_analysis_id == uuid.UUID(result["job_analysis_id"])

    listing_response = client.get(f"/api/job-listings/{listing.id}")
    listing_data = listing_response.json()["data"]
    assert listing_data["analyzed"] is True
    assert listing_data["last_score"] == result["score"]
    assert listing_data["last_status"] == result["status"]


@pytest.mark.integration
def test_evaluate_by_listings_uses_default_profile_when_omitted(
    client: TestClient,
    db_session: Session,
):
    profile = client.post(
        "/api/profile",
        json={"skills_text": "Python, FastAPI, PostgreSQL"},
    ).json()["data"]
    listing = JobListing(
        source="yourator",
        source_id=f"default-{uuid.uuid4()}",
        title="Backend Engineer",
        company="Example Co",
        location="Taipei",
        url="https://example.com/jobs/backend-default",
        description="Build FastAPI services and maintain PostgreSQL systems.",
    )
    db_session.add(listing)
    db_session.commit()

    response = client.post(
        "/api/evaluate/by-listings",
        json={"job_listing_ids": [str(listing.id)]},
    )

    assert response.status_code == 200
    result = response.json()["data"]["results"][0]
    assert result["job_analysis_id"]
    assert result["error"] is None

    listing_response = client.get(f"/api/job-listings/{listing.id}")
    listing_data = listing_response.json()["data"]
    assert listing_data["analyzed"] is True
    assert profile["is_default"] is True


@pytest.mark.integration
def test_evaluate_by_listings_rejects_more_than_20_ids(client: TestClient):
    profile = client.post(
        "/api/profile",
        json={"skills_text": "Python, FastAPI, PostgreSQL"},
    ).json()["data"]

    response = client.post(
        "/api/evaluate/by-listings",
        json={
            "profile_id": profile["id"],
            "job_listing_ids": [str(uuid.uuid4()) for _ in range(21)],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


@pytest.mark.integration
def test_evaluate_by_listings_returns_per_listing_errors(
    client: TestClient,
):
    profile = client.post(
        "/api/profile",
        json={"skills_text": "Python, FastAPI, PostgreSQL"},
    ).json()["data"]
    missing_id = uuid.uuid4()

    response = client.post(
        "/api/evaluate/by-listings",
        json={"profile_id": profile["id"], "job_listing_ids": [str(missing_id)]},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["succeeded"] == 0
    assert data["failed"] == 1
    assert data["results"][0]["listing_id"] == str(missing_id)
    assert data["results"][0]["error"]
