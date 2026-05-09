from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ApplicationStatus = Literal[
    "planned",
    "applied",
    "interviewing",
    "rejected",
    "offer",
    "archived",
]


class ApplicationCreateIn(BaseModel):
    job_listing_id: uuid.UUID | None = None
    job_analysis_id: uuid.UUID | None = None
    generated_resume_id: uuid.UUID | None = None
    company: str | None = None
    title: str | None = None
    source_url: str | None = None
    status: ApplicationStatus = "planned"
    follow_up_date: date | None = None
    notes: str | None = None


class ApplicationUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_listing_id: uuid.UUID | None = None
    job_analysis_id: uuid.UUID | None = None
    generated_resume_id: uuid.UUID | None = None
    company: str | None = None
    title: str | None = None
    source_url: str | None = None
    status: ApplicationStatus | None = None
    follow_up_date: date | None = None
    notes: str | None = None


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job_listing_id: uuid.UUID | None
    job_analysis_id: uuid.UUID | None
    generated_resume_id: uuid.UUID | None
    status: ApplicationStatus
    follow_up_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    company: str | None = None
    title: str | None = None
    source_url: str | None = None
    score: int | None = None
    analysis_status: str | None = None
    pdf_url: str | None = None
