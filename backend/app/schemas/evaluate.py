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
    prompt_version: str | None = None
    llm_backend: str | None = None
    llm_model: str | None = None
    tailoring_job_id: uuid.UUID | None = None
    tailoring_status: str | None = None


class CallbackIn(BaseModel):
    job_analysis_id: uuid.UUID
    resume_text: str
    pdf_url: str | None = None
    prompt_version: str | None = None


class BeautificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    generated_resume_id: uuid.UUID
    style: str
    prompt_version: str | None
    llm_backend: str | None = None
    llm_model: str | None = None
    html_url: str | None = None
    pdf_url: str | None = None
    created_at: datetime


class GeneratedResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    resume_text: str
    pdf_url: str | None = None
    prompt_version: str | None
    llm_backend: str | None = None
    llm_model: str | None = None
    proof_point_ids: list[str] = Field(default_factory=list)
    revision_source: str = "ai_draft"
    exported_at: datetime | None = None
    created_at: datetime
    beautifications: list[BeautificationOut] = []


class ResumeRevisionIn(BaseModel):
    resume_text: Annotated[str, Field(min_length=1)]


class BeautifyIn(BaseModel):
    style: Literal["modern", "classic", "minimal"] = "modern"


class HistoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    profile_id: int | None = None
    jd_snippet: str | None
    score: int | None
    threshold_met: bool
    status: str | None = None
    can_submit: bool = False
    prompt_version: str | None = None
    llm_backend: str | None = None
    llm_model: str | None = None
    tailoring_job_id: uuid.UUID | None = None
    tailoring_status: str | None = None
    created_at: datetime


class HistoryDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    profile_id: int | None = None
    jd_snippet: str | None
    jd_full_text: str
    score: int | None
    threshold_met: bool
    status: str | None = None
    can_submit: bool = False
    skip_reason: str | None = None
    prompt_version: str | None = None
    llm_backend: str | None = None
    llm_model: str | None = None
    tailoring_job_id: uuid.UUID | None = None
    tailoring_status: str | None = None
    created_at: datetime
    baseline_profile_text: str | None = None
    generated_resumes: list[GeneratedResumeOut] = []


class SubmittableResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    profile_id: int | None = None
    score: int | None
    jd_snippet: str | None
    status: str | None
    can_submit: bool
    prompt_version: str | None = None
    llm_backend: str | None = None
    llm_model: str | None = None
    created_at: datetime


class BulkEvaluateIn(BaseModel):
    jd_texts: Annotated[list[str], Field(min_length=1, max_length=100)]


class BulkEvaluateResult(BaseModel):
    job_analysis_id: uuid.UUID
    jd_snippet: str | None
    score: int
    status: Literal["ready_to_submit", "needs_tailoring", "skip"]
    cached: bool
    tailoring_job_id: uuid.UUID | None = None
    tailoring_status: str | None = None


class BulkEvaluateOut(BaseModel):
    total: int
    new: int
    cached: int
    skipped: int = 0
    blocked: int = 0
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    estimated_total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    results: list[BulkEvaluateResult]


class EvaluateByListingsIn(BaseModel):
    profile_id: int | None = None
    job_listing_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=20)]


class EvaluatePendingListingsIn(BaseModel):
    profile_id: int | None = None
    source: str | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 100


class EvaluateByListingsResult(BaseModel):
    listing_id: uuid.UUID
    job_analysis_id: uuid.UUID | None = None
    score: int | None = None
    status: Literal["ready_to_submit", "needs_tailoring", "skip"] | None = None
    cached: bool = False
    error: str | None = None
    tailoring_job_id: uuid.UUID | None = None
    tailoring_status: str | None = None


class EvaluateByListingsOut(BaseModel):
    total: int
    succeeded: int
    failed: int
    skipped: int = 0
    blocked: int = 0
    tailoring_blocked: int = 0
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    estimated_total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    warnings: list[dict[str, object]] = Field(default_factory=list)
    results: list[EvaluateByListingsResult]
