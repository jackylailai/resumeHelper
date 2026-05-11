from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class JobListingSummaryOut(BaseModel):
    id: uuid.UUID
    source: str
    source_id: str
    title: str
    company: str
    location: str | None
    url: str
    description_preview: str
    has_description: bool
    list_status: str
    analyzed: bool
    job_analysis_id: uuid.UUID | None
    last_score: int | None = None
    last_status: str | None = None
    scraped_at: datetime
    changed_at: datetime | None = None


class JobListingDetailOut(JobListingSummaryOut):
    description: str
    raw_json: dict | None
