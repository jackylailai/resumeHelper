from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GeneratedResume(Base):
    __tablename__ = "generated_resumes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    job_analysis: Mapped[JobAnalysis] = relationship(  # noqa: F821
        "JobAnalysis", back_populates="generated_resumes"
    )
