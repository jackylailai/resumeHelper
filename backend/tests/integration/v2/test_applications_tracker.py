from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import JobAnalysis
from backend.app.models.job_listing import JobListing


def test_application_tracker_create_list_filter_sort_update_delete(
    client: TestClient,
    db_session: Session,
):
    now = datetime.now(UTC)
    analysis = JobAnalysis(
        jd_hash=uuid.uuid4().hex,
        jd_full_text="Build APIs",
        score=88,
        threshold_met=True,
        status="ready_to_submit",
        can_submit=True,
    )
    older_analysis = JobAnalysis(
        jd_hash=uuid.uuid4().hex,
        jd_full_text="Run reports",
        score=61,
        threshold_met=True,
        status="needs_tailoring",
        can_submit=False,
    )
    db_session.add_all([analysis, older_analysis])
    db_session.flush()

    resume = GeneratedResume(
        job_analysis_id=analysis.id,
        resume_text="Tailored resume",
        pdf_url="/api/generated-resumes/test/pdf",
    )
    db_session.add(resume)
    db_session.flush()

    listing = JobListing(
        source="tracker-test",
        source_id=f"alpha-{uuid.uuid4()}",
        title="Platform Engineer",
        company="Alpha Co",
        location="Taipei",
        url="https://example.com/alpha",
        description="Build APIs",
        scraped_at=now - timedelta(days=1),
        job_analysis_id=analysis.id,
    )
    older_listing = JobListing(
        source="tracker-test",
        source_id=f"beta-{uuid.uuid4()}",
        title="Data Engineer",
        company="Beta Co",
        location="Remote",
        url="https://example.com/beta",
        description="Run reports",
        scraped_at=now - timedelta(days=2),
        job_analysis_id=older_analysis.id,
    )
    db_session.add_all([listing, older_listing])
    db_session.commit()

    create_response = client.post(
        "/api/applications",
        json={
            "job_listing_id": str(listing.id),
            "status": "planned",
            "follow_up_date": "2026-05-15",
            "notes": "Confirm PDF before applying",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()["data"]
    assert created["company"] == "Alpha Co"
    assert created["title"] == "Platform Engineer"
    assert created["score"] == 88
    assert created["pdf_url"] == "/api/generated-resumes/test/pdf"
    assert created["generated_resume_id"] == str(resume.id)

    second_response = client.post(
        "/api/applications",
        json={
            "job_listing_id": str(older_listing.id),
            "status": "applied",
            "follow_up_date": "2026-05-20",
        },
    )
    assert second_response.status_code == 201

    duplicate_response = client.post(
        "/api/applications",
        json={"job_listing_id": str(listing.id), "status": "applied"},
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["meta"]["existing"] is True
    assert duplicate_response.json()["data"]["id"] == created["id"]
    assert duplicate_response.json()["data"]["status"] == "applied"

    list_response = client.get("/api/applications?q=alpha&sort_by=score&sort_dir=desc")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["meta"]["total"] == 1
    assert list_body["data"][0]["company"] == "Alpha Co"

    status_response = client.get(
        "/api/applications?status=applied&sort_by=follow_up_date&sort_dir=asc"
    )
    assert status_response.status_code == 200
    assert [item["company"] for item in status_response.json()["data"]] == [
        "Alpha Co",
        "Beta Co",
    ]

    detail_response = client.get(f"/api/applications/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["source_url"] == "https://example.com/alpha"

    update_response = client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "interviewing", "follow_up_date": str(date(2026, 5, 22))},
    )
    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["status"] == "interviewing"
    assert updated["follow_up_date"] == "2026-05-22"

    delete_response = client.delete(f"/api/applications/{created['id']}")
    assert delete_response.status_code == 200
    missing_response = client.get(f"/api/applications/{created['id']}")
    assert missing_response.status_code == 404


def test_application_tracker_allows_manual_record(client: TestClient):
    response = client.post(
        "/api/applications",
        json={
            "company": "Manual Co",
            "title": "Staff Engineer",
            "source_url": "https://example.com/manual",
            "status": "planned",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["company"] == "Manual Co"
    assert data["title"] == "Staff Engineer"
    assert data["job_listing_id"] is None
