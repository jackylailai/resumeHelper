from __future__ import annotations

from datetime import datetime

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
    created_at: datetime | None
    updated_at: datetime


class ProfilePdfPreviewOut(BaseModel):
    filename: str
    skills_text: str


class ProfileDeleteImpactOut(BaseModel):
    profile_id: int
    job_analyses_count: int
    generated_resumes_count: int
