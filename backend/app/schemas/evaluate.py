from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvaluateIn(BaseModel):
    jd_text: str
    profile_id: int | None = None


class EvaluateOut(BaseModel):
    job_analysis_id: uuid.UUID
    score: int
    explanation: str
    strengths: list[str]
    gaps: list[str]
    threshold_met: bool
    # Three-tier fields
    status: Literal["ready_to_submit", "needs_tailoring", "skip"]
    message: str
    action: Literal["none", "tailoring", "skip"]


class CallbackIn(BaseModel):
    job_analysis_id: uuid.UUID
    resume_text: str
    pdf_url: str | None = None
    prompt_version: str | None = None


class GeneratedResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    resume_text: str
    pdf_url: str | None = None
    prompt_version: str | None
    created_at: datetime


class HistoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    profile_id: int | None = None
    jd_snippet: str | None
    score: int | None
    threshold_met: bool
    status: str | None = None
    can_submit: bool = False
    created_at: datetime


class HistoryDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    jd_snippet: str | None
    jd_full_text: str
    score: int | None
    threshold_met: bool
    status: str | None = None
    can_submit: bool = False
    skip_reason: str | None = None
    created_at: datetime
    generated_resumes: list[GeneratedResumeOut] = []


class SubmittableResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    profile_id: int | None = None
    score: int | None
    jd_snippet: str | None
    status: str | None
    can_submit: bool
    created_at: datetime


class BulkEvaluateIn(BaseModel):
    jd_texts: Annotated[list[str], Field(min_length=1, max_length=100)]


class BulkEvaluateResult(BaseModel):
    job_analysis_id: uuid.UUID
    jd_snippet: str | None
    score: int
    status: Literal["ready_to_submit", "needs_tailoring", "skip"]
    cached: bool


class BulkEvaluateOut(BaseModel):
    total: int
    new: int
    cached: int
    results: list[BulkEvaluateResult]


class EvaluateByListingsIn(BaseModel):
    profile_id: int | None = None
    job_listing_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=20)]


class EvaluateByListingsResult(BaseModel):
    listing_id: uuid.UUID
    job_analysis_id: uuid.UUID | None = None
    score: int | None = None
    status: Literal["ready_to_submit", "needs_tailoring", "skip"] | None = None
    cached: bool = False
    error: str | None = None


class EvaluateByListingsOut(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[EvaluateByListingsResult]
