from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobAnalysis(Base):
    __tablename__ = "job_analyses"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_job_score_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    jd_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    jd_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jd_full_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    gaps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    threshold_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    generated_resumes: Mapped[List[GeneratedResume]] = relationship(  # noqa: F821
        "GeneratedResume", back_populates="job_analysis", cascade="all, delete-orphan"
    )
