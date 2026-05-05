from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.evaluation import EvaluationOut


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    created_at: datetime
    updated_at: datetime
    latest_version_number: int | None = None
    latest_score: int | None = None


class ResumeVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    version_number: int
    file_format: str
    file_size_bytes: int
    content_hash: str
    uploaded_at: datetime
    evaluation: EvaluationOut | None = None
