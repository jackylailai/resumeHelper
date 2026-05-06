from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProfileIn(BaseModel):
    skills_text: str
    name: Optional[str] = None


class ProfileUpdateIn(BaseModel):
    skills_text: Optional[str] = None
    name: Optional[str] = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: Optional[str]
    skills_text: str
    created_at: Optional[datetime]
    updated_at: datetime
