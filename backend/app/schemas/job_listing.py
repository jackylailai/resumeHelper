from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


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


class JobListingBulkDeleteIn(BaseModel):
    """Either `ids` or `older_than_days` must be set, not both.

    Listings with a linked job_analysis_id are refused by default; pass
    `force=True` to delete them anyway (their JobAnalysis row stays with
    job_analysis_id orphaned)."""

    ids: list[uuid.UUID] | None = None
    older_than_days: Annotated[int, Field(ge=1, le=365)] | None = None
    only_unanalyzed: bool = True
    force: bool = False
    backup: bool = True

    @model_validator(mode="after")
    def _exactly_one_target(self) -> JobListingBulkDeleteIn:
        if (self.ids is None) == (self.older_than_days is None):
            raise ValueError(
                "Provide exactly one of `ids` or `older_than_days`.",
            )
        return self


class JobListingBulkDeleteOut(BaseModel):
    deleted: int
    refused: int
    refused_ids: list[uuid.UUID]
    backup_path: str | None = None
