from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Three-tier status constants
STATUS_READY_TO_SUBMIT = "ready_to_submit"
STATUS_NEEDS_TAILORING = "needs_tailoring"
STATUS_SKIP = "skip"

THRESHOLD_HIGH = 85
THRESHOLD_MID = 60


class JobAnalysis(Base):
    __tablename__ = "job_analyses"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_job_score_range"),
        CheckConstraint(
            "status IS NULL OR status IN ('ready_to_submit', 'needs_tailoring', 'skip')",
            name="ck_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("baseline_profile.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    jd_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    jd_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jd_full_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    gaps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    threshold_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    can_submit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skip_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    generated_resumes: Mapped[List[GeneratedResume]] = relationship(  # noqa: F821
        "GeneratedResume", back_populates="job_analysis", cascade="all, delete-orphan"
    )
