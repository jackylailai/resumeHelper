from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class EvaluateIn(BaseModel):
    jd_text: str


class EvaluateOut(BaseModel):
    job_analysis_id: uuid.UUID
    score: int
    explanation: str
    strengths: List[str]
    gaps: List[str]
    threshold_met: bool


class CallbackIn(BaseModel):
    job_analysis_id: uuid.UUID
    resume_text: str
    prompt_version: Optional[str] = None


class GeneratedResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    resume_text: str
    prompt_version: Optional[str]
    created_at: datetime


class HistoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    jd_snippet: Optional[str]
    score: Optional[int]
    threshold_met: bool
    created_at: datetime


class HistoryDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    jd_snippet: Optional[str]
    jd_full_text: str
    score: Optional[int]
    threshold_met: bool
    created_at: datetime
    generated_resumes: List[GeneratedResumeOut] = []
