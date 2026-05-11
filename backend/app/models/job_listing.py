from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


SOURCE_104 = "104"
SOURCE_YOURATOR = "yourator"
SOURCE_LINKEDIN = "linkedin"
ALLOWED_SOURCES = (SOURCE_104, SOURCE_YOURATOR, SOURCE_LINKEDIN)


class JobListing(Base):
    __tablename__ = "job_listings"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_job_listings_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    job_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
