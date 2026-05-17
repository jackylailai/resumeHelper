from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx

from backend.app.services.http.safe_client import safe_async_client
from backend.app.services.scrapers.base import BaseScraper, JobListingDraft

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_URL_FMT = "https://www.104.com.tw/job/ajax/content/{slug}"
JOB_PAGE_FMT = "https://www.104.com.tw/job/{slug}"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Referer": "https://www.104.com.tw/jobs/search/",
    "Accept": "application/json, text/plain, */*",
}


def _extract_slug(link_job: str) -> str | None:
    """Pull the job slug out of `https://www.104.com.tw/job/<slug>` (or `//www...`)."""
    if not link_job:
        return None
    if link_job.startswith("//"):
        link_job = "https:" + link_job
    path = urlparse(link_job).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "job":
        return parts[1] or None
    return None


class Scraper104(BaseScraper):
    source: ClassVar[str] = "104"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        page_delay_seconds: float = 1.5,
        detail_delay_seconds: float = 0.8,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self.page_delay = page_delay_seconds
        self.detail_delay = detail_delay_seconds

    async def __aenter__(self) -> Scraper104:
        if self._client is None:
            self._client = safe_async_client(
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
            raise RuntimeError("Scraper104 must be used inside `async with` context")
        return self._client

    async def search(self, keyword: str, limit: int) -> list[JobListingDraft]:
        drafts: list[JobListingDraft] = []
        seen: set[str] = set()
        page = 1
        while len(drafts) < limit:
            payload = await self._fetch_search_page(keyword, page)
            page_data = payload.get("data") or []
            if not page_data:
                break
            for item in page_data:
                draft = self._draft_from_search(item)
                if draft is None or draft.source_id in seen:
                    continue
                seen.add(draft.source_id)
                drafts.append(draft)
                if len(drafts) >= limit:
                    break
            if len(page_data) < 20:
                # 104 returns ~20 per page; a short page = end of results
                break
            page += 1
            if self.page_delay > 0:
                await asyncio.sleep(self.page_delay)
        return drafts

    async def fetch_detail(self, draft: JobListingDraft) -> JobListingDraft:
        slug = _extract_slug(draft.url)
        if slug is None:
            log.warning("104 detail skipped — cannot extract slug from %s", draft.url)
            return draft
        try:
            r = await self.client.get(
                DETAIL_URL_FMT.format(slug=slug),
                headers={"Referer": JOB_PAGE_FMT.format(slug=slug)},
            )
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("104 detail fetch failed for %s: %s", slug, exc)
            return draft
        data = body.get("data") or {}
        job_detail = data.get("jobDetail") or {}
        description = job_detail.get("jobDescription") or ""
        if description:
            draft.description = description
        draft.raw_json = data
        if self.detail_delay > 0:
            await asyncio.sleep(self.detail_delay)
        return draft

    async def _fetch_search_page(self, keyword: str, page: int) -> dict[str, Any]:
        params = {
            "ro": "1",
            "kwop": "7",
            "keyword": keyword,
            "order": "15",
            "asc": "0",
            "page": str(page),
            "mode": "s",
            "jobsource": "2018indexpoc",
        }
        r = await self.client.get(SEARCH_URL, params=params)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def _draft_from_search(self, item: dict[str, Any]) -> JobListingDraft | None:
        job_no = item.get("jobNo")
        link = (item.get("link") or {}).get("job") or ""
        if not job_no or not link:
            return None
        if link.startswith("//"):
            link = "https:" + link
        return JobListingDraft(
            source=self.source,
            source_id=str(job_no),
            title=item.get("jobName") or "",
            company=item.get("custName") or "",
            url=link,
            location=item.get("jobAddrNoDesc") or None,
            description=item.get("description") or "",
        )
