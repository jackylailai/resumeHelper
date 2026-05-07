from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("resume_id", "version_number", name="uq_resume_version"),
        CheckConstraint("file_size_bytes <= 10485760", name="ck_file_size"),
        CheckConstraint("file_format IN ('pdf', 'docx')", name="ck_file_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_format: Mapped[str] = mapped_column(String(8), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_text: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    resume: Mapped[Resume] = relationship("Resume", back_populates="versions")  # noqa: F821
    evaluations: Mapped[list[ResumeEvaluation]] = relationship(  # noqa: F821
        "ResumeEvaluation", back_populates="version", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[EvaluationJob]] = relationship(  # noqa: F821
        "EvaluationJob", back_populates="version", cascade="all, delete-orphan"
    )
