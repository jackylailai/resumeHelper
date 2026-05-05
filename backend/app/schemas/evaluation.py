from __future__ import annotations  # enables X | None syntax on Python 3.9

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_version_id: uuid.UUID
    score: int
    explanation: str
    strengths: list[str]
    gaps: list[str]
    prompt_version: str
    model: str
    latency_ms: int
    token_count_input: int | None
    token_count_output: int | None
    created_at: datetime

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: int) -> int:
        if not (0 <= v <= 100):
            raise ValueError(f"score must be 0-100, got {v}")
        return v


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_version_id: uuid.UUID
    status: str
    evaluation_id: uuid.UUID | None
    failure_reason: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
