from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProfileIn(BaseModel):
    skills_text: str
    name: str | None = None
    is_default: bool = False


class ProfileUpdateIn(BaseModel):
    skills_text: str | None = None
    name: str | None = None
    is_default: bool | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str | None
    skills_text: str
    pdf_path: str | None = None
    is_default: bool
    structured_data: dict[str, Any] | None = None
    created_at: datetime | None
    updated_at: datetime


class StructuredDataIn(BaseModel):
    """Loose container for the structured profile JSON. We accept any keys —
    Pydantic's strict typing is unhelpful here because the schema evolves and
    consumers (the LLM tailor prompt) are flexible about which fields exist.
    Validation is delegated to the API layer (basic shape check).
    """

    model_config = ConfigDict(extra="allow")


class ProfilePdfPreviewOut(BaseModel):
    filename: str
    skills_text: str


class ProfileDeleteImpactOut(BaseModel):
    profile_id: int
    job_analyses_count: int
    generated_resumes_count: int
