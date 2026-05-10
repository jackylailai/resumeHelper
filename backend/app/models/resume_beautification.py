from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ResumeBeautification(Base):
    __tablename__ = "resume_beautifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generated_resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generated_resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    style: Mapped[str] = mapped_column(String(32), nullable=False, default="modern")
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    generated_resume: Mapped[GeneratedResume] = relationship(  # noqa: F821
        "GeneratedResume", back_populates="beautifications"
    )
