from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_listing import JobListing


def test_list_job_listings_paginates_sorts_and_filters_status(
    client: TestClient, db_session: Session
):
    now = datetime.now(UTC)
    source = f"workbench-{uuid.uuid4().hex[:8]}"
    ready_analysis = JobAnalysis(
        jd_hash=uuid.uuid4().hex,
        jd_full_text="Ready listing",
        score=91,
        threshold_met=True,
        status="ready_to_submit",
        can_submit=True,
    )
    skip_analysis = JobAnalysis(
        jd_hash=uuid.uuid4().hex,
        jd_full_text="Skip listing",
        score=42,
        threshold_met=False,
        status="skip",
        can_submit=False,
    )
    db_session.add_all([ready_analysis, skip_analysis])
    db_session.flush()

    ready_listing = JobListing(
        source=source,
        source_id=f"ready-{uuid.uuid4()}",
        title="Ready Engineer",
        company="Alpha Co",
        location="Taipei",
        url="https://example.com/ready",
        description="Ready listing",
        scraped_at=now - timedelta(minutes=4),
        job_analysis_id=ready_analysis.id,
    )
    unanalyzed_listing = JobListing(
        source=source,
        source_id=f"new-{uuid.uuid4()}",
        title="New Engineer",
        company="Beta Co",
        location="Taipei",
        url="https://example.com/new",
        description="New listing",
        scraped_at=now - timedelta(minutes=3),
    )
    skip_listing = JobListing(
        source=source,
        source_id=f"skip-{uuid.uuid4()}",
        title="Skip Engineer",
        company="Gamma Co",
        location="Remote",
        url="https://example.com/skip",
        description="Skip listing",
        scraped_at=now - timedelta(minutes=2),
        job_analysis_id=skip_analysis.id,
    )
    invalid_listing = JobListing(
        source=source,
        source_id=f"invalid-{uuid.uuid4()}",
        title="Invalid Engineer",
        company="Zeta Co",
        location=None,
        url="https://example.com/invalid",
        description="   ",
        scraped_at=now - timedelta(minutes=1),
    )
    db_session.add_all([
        ready_listing,
        unanalyzed_listing,
        skip_listing,
        invalid_listing,
    ])
    db_session.commit()

    page_response = client.get(
        "/api/job-listings"
        f"?source={source}&limit=2&offset=1&sort_by=company&sort_dir=asc"
    )

    assert page_response.status_code == 200
    page_body = page_response.json()
    assert page_body["meta"]["total"] == 4
    assert page_body["meta"]["range_start"] == 2
    assert page_body["meta"]["range_end"] == 3
    assert [item["company"] for item in page_body["data"]] == [
        "Beta Co",
        "Gamma Co",
    ]

    score_response = client.get(
        f"/api/job-listings?source={source}&sort_by=score&sort_dir=desc&limit=4"
    )
    assert score_response.status_code == 200
    assert [item["last_score"] for item in score_response.json()["data"][:2]] == [
        91,
        42,
    ]

    ready_response = client.get(
        f"/api/job-listings?source={source}&status=ready_to_submit"
    )
    assert ready_response.status_code == 200
    ready_data = ready_response.json()["data"]
    assert [item["id"] for item in ready_data] == [str(ready_listing.id)]
    assert ready_data[0]["list_status"] == "ready_to_submit"

    unanalyzed_response = client.get(
        f"/api/job-listings?source={source}&status=unanalyzed"
    )
    assert unanalyzed_response.status_code == 200
    assert [item["id"] for item in unanalyzed_response.json()["data"]] == [
        str(unanalyzed_listing.id)
    ]

    invalid_response = client.get(
        f"/api/job-listings?source={source}&status=failed-invalid"
    )
    assert invalid_response.status_code == 200
    invalid_data = invalid_response.json()["data"]
    assert [item["id"] for item in invalid_data] == [str(invalid_listing.id)]
    assert invalid_data[0]["has_description"] is False
    assert invalid_data[0]["list_status"] == "failed-invalid"
