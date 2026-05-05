from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BaselineProfile(Base):
    __tablename__ = "baseline_profile"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skills_text: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
