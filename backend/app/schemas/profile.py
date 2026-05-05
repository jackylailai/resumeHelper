from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ProfileIn(BaseModel):
    skills_text: str


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    skills_text: str
    updated_at: datetime
