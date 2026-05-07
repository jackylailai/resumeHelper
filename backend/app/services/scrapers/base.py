from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass
class JobListingDraft:
    """In-flight job listing before it lands in the DB.

    Scrapers populate the listing fields incrementally — search() returns drafts
    with the cheap-to-fetch fields filled, and fetch_detail() enriches the
    description and raw_json from a per-listing detail endpoint.
    """

    source: str
    source_id: str
    title: str
    company: str
    url: str
    location: str | None = None
    description: str = ""
    raw_json: dict[str, Any] | None = field(default=None)


class BaseScraper(ABC):
    source: ClassVar[str]

    @abstractmethod
    async def search(self, keyword: str, limit: int) -> list[JobListingDraft]:
        """Return drafts from the listing endpoint. Description may be empty."""

    @abstractmethod
    async def fetch_detail(self, draft: JobListingDraft) -> JobListingDraft:
        """Fill in `description` (and `raw_json` when useful) from the detail page."""
