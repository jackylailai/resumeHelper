from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, ClassVar

import httpx

from backend.app.services.scrapers.base import BaseScraper, JobListingDraft

log = logging.getLogger(__name__)

BASE = "https://www.yourator.co"
SEARCH_URL = f"{BASE}/api/v4/jobs"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

_JSONLD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _strip_html(html: str) -> str:
    """Convert the HTML-flavoured JSON-LD description into readable plain text."""
    if not html:
        return ""
    text = html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    text = (
        text.replace("&mdash;", "—")
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_jobposting(html: str) -> dict[str, Any] | None:
    for m in _JSONLD_RE.finditer(html):
        try:
            data = json.loads(m.group(1))
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return None


class ScraperYourator(BaseScraper):
    source: ClassVar[str] = "yourator"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        page_delay_seconds: float = 1.5,
        detail_delay_seconds: float = 0.8,
        max_pages: int = 50,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self.page_delay = page_delay_seconds
        self.detail_delay = detail_delay_seconds
        self.max_pages = max_pages

    async def __aenter__(self) -> ScraperYourator:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS, timeout=httpx.Timeout(15.0)
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "ScraperYourator must be used inside `async with` context"
            )
        return self._client

    async def search(self, keyword: str, limit: int) -> list[JobListingDraft]:
        # Yourator's /api/v4/jobs ignores `term`/`keyword`/`categories` query params
        # at the time of writing (returns the same 20/page regardless), so we
        # paginate the full feed and filter client-side by job title.
        needle = keyword.lower().strip()
        drafts: list[JobListingDraft] = []
        seen: set[str] = set()
        page = 1
        while len(drafts) < limit and page <= self.max_pages:
            payload = await self._fetch_search_page(keyword, page)
            jobs = payload.get("jobs") or []
            if not jobs:
                break
            for item in jobs:
                draft = self._draft_from_search(item)
                if draft is None or draft.source_id in seen:
                    continue
                if needle and needle not in draft.title.lower():
                    continue
                seen.add(draft.source_id)
                drafts.append(draft)
                if len(drafts) >= limit:
                    break
            if not payload.get("hasMore"):
                break
            page = payload.get("nextPage") or page + 1
            if self.page_delay > 0:
                await asyncio.sleep(self.page_delay)
        return drafts

    async def fetch_detail(self, draft: JobListingDraft) -> JobListingDraft:
        try:
            r = await self.client.get(draft.url, headers={"Accept": "text/html"})
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("yourator detail fetch failed for %s: %s", draft.url, exc)
            return draft
        posting = _extract_jobposting(r.text)
        if posting is None:
            log.warning("yourator detail had no JSON-LD JobPosting: %s", draft.url)
            return draft
        description_html = str(posting.get("description") or "")
        description = _strip_html(description_html)
        if description:
            draft.description = description
        draft.raw_json = posting
        if self.detail_delay > 0:
            await asyncio.sleep(self.detail_delay)
        return draft

    async def _fetch_search_page(self, keyword: str, page: int) -> dict[str, Any]:
        # `term` is sent for parity with the public search URL even though the
        # backend currently ignores it — keeps our requests indistinguishable
        # from the website's own.
        params = {"term": keyword, "page": str(page)}
        r = await self.client.get(SEARCH_URL, params=params)
        r.raise_for_status()
        body = r.json()
        return body.get("payload") or {}  # type: ignore[no-any-return]

    def _draft_from_search(self, item: dict[str, Any]) -> JobListingDraft | None:
        job_id = item.get("id")
        path = item.get("path") or ""
        if job_id is None or not path:
            return None
        company = (item.get("company") or {}).get("brand") or ""
        return JobListingDraft(
            source=self.source,
            source_id=str(job_id),
            title=item.get("name") or "",
            company=company,
            url=f"{BASE}{path}",
            location=item.get("location") or None,
            description="",
        )
