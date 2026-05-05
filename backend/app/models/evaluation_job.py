from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


VALID_STATUSES = ("pending", "running", "succeeded", "failed")


class EvaluationJob(Base):
    __tablename__ = "evaluation_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jd_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_evaluations.id", ondelete="SET NULL"), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[ResumeVersion] = relationship(  # noqa: F821
        "ResumeVersion", back_populates="jobs"
    )
    evaluation: Mapped[ResumeEvaluation | None] = relationship(  # noqa: F821
        "ResumeEvaluation", foreign_keys=[evaluation_id]
    )


class EvaluationCache(Base):
    __tablename__ = "evaluation_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_evaluations.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    evaluation: Mapped[ResumeEvaluation] = relationship(  # noqa: F821
        "ResumeEvaluation", back_populates="cache_entry"
    )
