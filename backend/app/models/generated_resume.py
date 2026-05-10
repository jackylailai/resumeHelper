from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class GeneratedResume(Base):
    __tablename__ = "generated_resumes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    job_analysis: Mapped[JobAnalysis] = relationship(  # noqa: F821
        "JobAnalysis", back_populates="generated_resumes"
    )
    beautifications: Mapped[list[ResumeBeautification]] = relationship(  # noqa: F821
        "ResumeBeautification",
        back_populates="generated_resume",
        cascade="all, delete-orphan",
        order_by="ResumeBeautification.created_at.desc()",
    )
