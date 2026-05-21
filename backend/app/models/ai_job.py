from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


AI_JOB_STATUSES = (
    "queued",
    "running",
    "retry_wait",
    "cancel_requested",
    "cancelled",
    "succeeded",
    "failed",
)
AI_JOB_TERMINAL_STATUSES = ("cancelled", "succeeded", "failed")
AI_JOB_KINDS = (
    "tailor",
    "evaluate",
    "evaluate_bulk",
    "evaluate_listing",
    "evaluate_pending_listings",
)


class AIJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        CheckConstraint(
            (
                "kind IN ("
                "'tailor', 'evaluate', 'evaluate_bulk', "
                "'evaluate_listing', 'evaluate_pending_listings'"
                ")"
            ),
            name="ck_ai_jobs_kind",
        ),
        CheckConstraint(
            (
                "status IN ("
                "'queued', 'running', 'retry_wait', 'cancel_requested', "
                "'cancelled', 'succeeded', 'failed'"
                ")"
            ),
            name="ck_ai_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_ai_jobs_attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="ck_ai_jobs_max_attempts_positive"),
        CheckConstraint(
            "progress_current >= 0",
            name="ck_ai_jobs_progress_current_nonnegative",
        ),
        CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="ck_ai_jobs_progress_total_nonnegative",
        ),
        UniqueConstraint("dedupe_key", name="uq_ai_jobs_dedupe_key"),
        Index(
            "ix_ai_jobs_worker_queue",
            "status",
            "run_after",
            "priority",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("baseline_profile.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    generated_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_resumes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now, index=True
    )
