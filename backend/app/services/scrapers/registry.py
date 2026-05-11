from __future__ import annotations

from backend.app.services.scrapers.base import BaseScraper
from backend.app.services.scrapers.scraper_104 import Scraper104
from backend.app.services.scrapers.scraper_linkedin import ScraperLinkedIn
from backend.app.services.scrapers.scraper_yourator import ScraperYourator

DEFAULT_SOURCES = ("104", "yourator")

SCRAPERS: dict[str, type[BaseScraper]] = {
    "104": Scraper104,
    "yourator": ScraperYourator,
    "linkedin": ScraperLinkedIn,
}


def resolve_sources(source: str) -> list[str]:
    if source == "all":
        return list(DEFAULT_SOURCES)
    if source == "all_with_linkedin":
        return list(SCRAPERS)
    if source not in SCRAPERS:
        raise ValueError(
            f"unknown source {source!r}; valid: {list(SCRAPERS)}, "
            "'all', or 'all_with_linkedin'"
        )
    return [source]
