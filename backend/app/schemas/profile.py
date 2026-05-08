from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProfileIn(BaseModel):
    skills_text: str
    name: str | None = None


class ProfileUpdateIn(BaseModel):
    skills_text: str | None = None
    name: str | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str | None
    skills_text: str
    pdf_path: str | None = None
    created_at: datetime | None
    updated_at: datetime
