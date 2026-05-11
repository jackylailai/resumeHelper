from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.models.generated_resume import GeneratedResume
from backend.app.models.job_analysis import JobAnalysis


@pytest.mark.integration
def test_create_generated_resume_revision_saves_user_edit(
    client: TestClient,
    db_session: Session,
):
    analysis = JobAnalysis(
        jd_hash=uuid.uuid4().hex,
        jd_full_text="Backend JD",
        score=78,
        threshold_met=True,
        status="needs_tailoring",
        can_submit=True,
    )
    db_session.add(analysis)
    db_session.flush()
    original = GeneratedResume(
        job_analysis_id=analysis.id,
        resume_text="AI draft",
        pdf_url="/api/generated-resumes/original/pdf",
    )
    db_session.add(original)
    db_session.commit()

    response = client.post(
        f"/api/generated-resumes/{original.id}/revisions",
        json={"resume_text": "User edited draft"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] != str(original.id)
    assert data["resume_text"] == "User edited draft"
    assert data["revision_source"] == "user_edited"
    assert data["pdf_url"].endswith("/pdf")

    saved = db_session.get(GeneratedResume, uuid.UUID(data["id"]))
    assert saved is not None
    assert saved.job_analysis_id == analysis.id
    assert saved.resume_text == "User edited draft"
    assert saved.revision_source == "user_edited"


@pytest.mark.integration
def test_generated_resume_pdf_marks_revision_exported(
    client: TestClient,
    db_session: Session,
):
    analysis = JobAnalysis(
        jd_hash=uuid.uuid4().hex,
        jd_full_text="Backend JD",
        score=90,
        threshold_met=True,
        status="ready_to_submit",
        can_submit=True,
    )
    db_session.add(analysis)
    db_session.flush()
    resume = GeneratedResume(
        job_analysis_id=analysis.id,
        resume_text="Resume for export",
        revision_source="user_edited",
    )
    db_session.add(resume)
    db_session.commit()

    response = client.get(f"/api/generated-resumes/{resume.id}/pdf")

    assert response.status_code == 200
    db_session.expire_all()
    exported = db_session.get(GeneratedResume, resume.id)
    assert exported.exported_at is not None
