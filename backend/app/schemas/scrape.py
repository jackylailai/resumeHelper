from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ScrapeSource = Literal["104", "yourator", "linkedin", "all", "all_with_linkedin"]
ScrapeRunStatus = Literal[
    "queued",
    "running",
    "cancel_requested",
    "cancelled",
    "succeeded",
    "partial",
    "failed",
]
MatchMode = Literal["all", "any"]


class ScrapeRunCreateIn(BaseModel):
    source: ScrapeSource = "all"
    keyword: Annotated[str, Field(min_length=1, max_length=120)]
    limit: Annotated[int, Field(ge=1, le=100)] = 25
    must_contain: list[Annotated[str, Field(min_length=1, max_length=120)]] | None = None
    match_mode: MatchMode = "all"
    regex: bool = False


class ScrapeControlStartIn(ScrapeRunCreateIn):
    evaluate_after_scrape: bool = True
    evaluate_limit: Annotated[int, Field(ge=1, le=500)] = 100
    profile_id: int | None = None
    stop_existing: bool = False


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
    skipped_by_filter: int = 0
    must_contain: list[str] | None = None
    match_mode: MatchMode = "all"
    regex: bool = False
    error_summary: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class ScrapeRunCreatedOut(BaseModel):
    runs: list[ScrapeRunOut]


class ScrapeStatusOut(BaseModel):
    recent_runs: list[ScrapeRunOut]


class ScrapeControlStatusOut(ScrapeStatusOut):
    active: bool
    active_runs: list[ScrapeRunOut]
