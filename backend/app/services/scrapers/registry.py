from __future__ import annotations

from backend.app.services.scrapers.base import BaseScraper
from backend.app.services.scrapers.scraper_104 import Scraper104
from backend.app.services.scrapers.scraper_yourator import ScraperYourator

SCRAPERS: dict[str, type[BaseScraper]] = {
    "104": Scraper104,
    "yourator": ScraperYourator,
}


def resolve_sources(source: str) -> list[str]:
    if source == "all":
        return list(SCRAPERS)
    if source not in SCRAPERS:
        raise ValueError(f"unknown source {source!r}; valid: {list(SCRAPERS)} or 'all'")
    return [source]
