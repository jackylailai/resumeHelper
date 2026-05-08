from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.job_listing import JobListing


@pytest.mark.integration
def test_list_job_listings_returns_scraped_jds(
    client: TestClient, db_session: Session
):
    source_id = f"browser-{uuid.uuid4()}"
    listing = JobListing(
        source="yourator",
        source_id=source_id,
        title="Backend Engineer",
        company="Example Co",
        location="Taipei",
        url="https://example.com/jobs/backend",
        description="Build FastAPI services and maintain PostgreSQL systems.",
    )
    db_session.add(listing)
    db_session.commit()

    response = client.get(f"/api/job-listings?q=FastAPI&source=yourator&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["meta"]["total"] >= 1
    assert any(item["id"] == str(listing.id) for item in body["data"])


@pytest.mark.integration
def test_get_job_listing_returns_full_description(
    client: TestClient, db_session: Session
):
    listing = JobListing(
        source="104",
        source_id=f"detail-{uuid.uuid4()}",
        title="Platform Engineer",
        company="Example Co",
        location="Remote",
        url="https://example.com/jobs/platform",
        description="Full JD text with Kubernetes, Python, and observability.",
    )
    db_session.add(listing)
    db_session.commit()

    response = client.get(f"/api/job-listings/{listing.id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(listing.id)
    assert data["description"] == listing.description
    assert data["has_description"] is True
    assert data["analyzed"] is False
