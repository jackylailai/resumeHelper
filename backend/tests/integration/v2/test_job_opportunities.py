from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.application import Application
from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_listing import JobListing


def _analysis(score: int, status: str) -> JobAnalysis:
    return JobAnalysis(
        jd_hash=uuid.uuid4().hex,
        jd_full_text=f"JD score {score}",
        score=score,
        threshold_met=score >= 70,
        status=status,
        can_submit=status == "ready_to_submit",
    )


def _listing(analysis: JobAnalysis, title: str) -> JobListing:
    return JobListing(
        source="104",
        source_id=f"opp-{uuid.uuid4()}",
        title=title,
        company="Example Co",
        location="Taipei",
        url=f"https://example.com/jobs/{uuid.uuid4()}",
        description=analysis.jd_full_text,
        job_analysis_id=analysis.id,
    )


@pytest.mark.integration
def test_job_opportunities_returns_high_fit_untracked_jobs(
    client: TestClient,
    db_session: Session,
):
    high = _analysis(91, "ready_to_submit")
    low = _analysis(35, "skip")
    tailored = _analysis(72, "needs_tailoring")
    db_session.add_all([high, low, tailored])
    db_session.flush()

    high_listing = _listing(high, "High Fit Engineer")
    low_listing = _listing(low, "Low Fit Engineer")
    tailored_listing = _listing(tailored, "Tailored Engineer")
    resume = GeneratedResume(
        job_analysis_id=tailored.id,
        resume_text="Tailored resume",
        pdf_url="/api/generated-resumes/example/pdf",
    )
    db_session.add_all([high_listing, low_listing, tailored_listing, resume])
    db_session.commit()

    response = client.get("/api/job-opportunities")

    assert response.status_code == 200
    data = response.json()["data"]
    ids = {item["job_listing_id"] for item in data}
    assert str(high_listing.id) in ids
    assert str(tailored_listing.id) in ids
    assert str(low_listing.id) not in ids
    high_item = next(item for item in data if item["job_listing_id"] == str(high_listing.id))
    assert high_item["source_url"] == high_listing.url
    assert high_item["frontend_url"] == f"/jobs.html?listing_id={high_listing.id}"


@pytest.mark.integration
def test_job_opportunities_excludes_tracked_by_default(
    client: TestClient,
    db_session: Session,
):
    analysis = _analysis(90, "ready_to_submit")
    db_session.add(analysis)
    db_session.flush()
    listing = _listing(analysis, "Tracked Engineer")
    db_session.add(listing)
    db_session.flush()
    app = Application(
        job_listing_id=listing.id,
        job_analysis_id=analysis.id,
        company=listing.company,
        title=listing.title,
        source_url=listing.url,
        status="planned",
    )
    db_session.add(app)
    db_session.commit()

    response = client.get("/api/job-opportunities")
    assert response.status_code == 200
    assert str(listing.id) not in {
        item["job_listing_id"] for item in response.json()["data"]
    }

    include_response = client.get("/api/job-opportunities?include_tracked=true")
    assert include_response.status_code == 200
    tracked = [
        item
        for item in include_response.json()["data"]
        if item["job_listing_id"] == str(listing.id)
    ]
    assert tracked
    assert tracked[0]["tracked"] is True
    assert tracked[0]["application_id"] == str(app.id)
