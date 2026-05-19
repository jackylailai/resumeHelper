from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class LLMAuditLog(Base):
    __tablename__ = "llm_audit_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_llm_audit_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    workflow_step: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    backend: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    baseline_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("baseline_profile.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    generated_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generated_resumes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resume_beautification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_beautifications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, index=True
    )
