from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ScrapeSource = Literal["104", "yourator", "all"]
ScrapeRunStatus = Literal["queued", "running", "succeeded", "partial", "failed"]


class ScrapeRunCreateIn(BaseModel):
    source: ScrapeSource = "all"
    keyword: Annotated[str, Field(min_length=1, max_length=120)]
    limit: Annotated[int, Field(ge=1, le=100)] = 25


class ScrapeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    keyword: str
    limit: int
    status: ScrapeRunStatus
    inserted: int
    updated: int
    skipped: int
    failed: int
    error_summary: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class ScrapeRunCreatedOut(BaseModel):
    runs: list[ScrapeRunOut]


class ScrapeStatusOut(BaseModel):
    recent_runs: list[ScrapeRunOut]
