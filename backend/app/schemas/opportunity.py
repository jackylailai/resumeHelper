from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class JobOpportunityOut(BaseModel):
    job_listing_id: uuid.UUID
    job_analysis_id: uuid.UUID
    generated_resume_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    company: str
    title: str
    source: str
    source_url: str
    frontend_url: str
    score: int | None = None
    status: str | None = None
    scraped_at: datetime
    analyzed_at: datetime
    has_generated_resume: bool = False
    pdf_url: str | None = None
    tracked: bool = False
