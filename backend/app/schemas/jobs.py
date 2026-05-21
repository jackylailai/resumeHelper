from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

AIJobStatus = Literal[
    "queued",
    "running",
    "retry_wait",
    "cancel_requested",
    "cancelled",
    "succeeded",
    "failed",
]
AIJobKind = Literal[
    "tailor",
    "evaluate",
    "evaluate_bulk",
    "evaluate_listing",
    "evaluate_pending_listings",
]


class AIJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: AIJobKind
    status: AIJobStatus
    parent_job_id: uuid.UUID | None = None
    dedupe_key: str | None = None
    priority: int
    run_after: datetime
    attempts: int
    max_attempts: int
    locked_by: str | None = None
    locked_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress_current: int
    progress_total: int | None = None
    profile_id: int | None = None
    job_analysis_id: uuid.UUID | None = None
    job_listing_id: uuid.UUID | None = None
    generated_resume_id: uuid.UUID | None = None
    prompt_version: str | None = None
    request_id: str | None = None
    input_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
