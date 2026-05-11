from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx

from backend.app.services.scrapers.base import BaseScraper, JobListingDraft

log = logging.getLogger(__name__)

BASE = "https://www.linkedin.com"
SEARCH_URL = f"{BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL_FMT = f"{BASE}/jobs-guest/jobs/api/jobPosting/{{job_id}}"
JOB_PAGE_FMT = f"{BASE}/jobs/view/{{job_id}}"
PAGE_SIZE = 25
DEFAULT_LOCATION = "Taiwan"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
}

_JOB_ID_PATTERNS = (
    re.compile(r"jobPosting:(\d+)"),
    re.compile(r"/jobPosting/(\d+)"),
    re.compile(r"/jobs/view/(?:[^/?#]*-)?(\d+)(?:[/?#]|$)"),
)
_HTML_WS_RE = re.compile(r"\n{3,}")
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class RateLimitedError(RuntimeError):
    """Raised when LinkedIn guest endpoints reject or throttle the scraper."""


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {k.lower(): v or "" for k, v in attrs})
        self._stack[-1].children.append(node)
        if tag.lower() not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {k.lower(): v or "" for k, v in attrs})
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].text_parts.append(data)


def _parse_html(html: str) -> _Node:
    parser = _TreeParser()
    parser.feed(html)
    parser.close()
    return parser.root


def _walk(node: _Node) -> list[_Node]:
    nodes = [node]
    for child in node.children:
        nodes.extend(_walk(child))
    return nodes


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _has_class(node: _Node, class_name: str) -> bool:
    return class_name in _classes(node)


def _first_node(root: _Node, predicate: Callable[[_Node], bool]) -> _Node | None:
    for node in _walk(root):
        if predicate(node):
            return node
    return None


def _text(node: _Node) -> str:
    parts = list(node.text_parts)
    for child in node.children:
        if child.tag in {"script", "style", "noscript"}:
            continue
        parts.append(_text(child))
    return _normalize_text("\n".join(parts))


def _normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    compact = "\n".join(line for line in lines if line)
    return _HTML_WS_RE.sub("\n\n", compact).strip()


def _raise_if_rate_limited(response: httpx.Response, *, context: str) -> None:
    if response.status_code in {429, 999}:
        raise RateLimitedError(
            f"LinkedIn rate limited {context}: HTTP {response.status_code}"
        )


def _extract_job_id(value: str) -> str | None:
    if not value:
        return None
    for pattern in _JOB_ID_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)

    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    current_job_id = query.get("currentJobId")
    if current_job_id and current_job_id[0].isdigit():
        return current_job_id[0]
    return None


def _clean_linkedin_url(value: str, fallback_job_id: str) -> str:
    if not value:
        return JOB_PAGE_FMT.format(job_id=fallback_job_id)
    if value.startswith("/"):
        value = f"{BASE}{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        return JOB_PAGE_FMT.format(job_id=fallback_job_id)
    return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, "", "", ""))


def _jsonld_jobposting(root: _Node) -> dict[str, Any] | None:
    for node in _walk(root):
        content_type = node.attrs.get("type", "").lower()
        if node.tag != "script" or "application/ld+json" not in content_type:
            continue
        raw = "".join(node.text_parts).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        posting = _find_jobposting(data)
        if posting is not None:
            return posting
    return None


def _find_jobposting(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        if data.get("@type") == "JobPosting":
            return data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                posting = _find_jobposting(item)
                if posting is not None:
                    return posting
    if isinstance(data, list):
        for item in data:
            posting = _find_jobposting(item)
            if posting is not None:
                return posting
    return None


def _company_from_jsonld(posting: dict[str, Any]) -> str:
    hiring_org = posting.get("hiringOrganization")
    if isinstance(hiring_org, dict):
        name = hiring_org.get("name")
        if isinstance(name, str):
            return name.strip()
    return ""


def _description_from_detail(html: str) -> tuple[str, dict[str, Any] | None]:
    root = _parse_html(html)
    posting = _jsonld_jobposting(root)

    for class_name in (
        "show-more-less-html__markup",
        "show-more-less-html",
        "description__text",
        "jobs-description-content__text",
    ):
        node = _first_node(root, lambda candidate, name=class_name: _has_class(candidate, name))
        if node is not None:
            description = _text(node)
            if description:
                return description, posting

    if posting is not None:
        description_html = posting.get("description")
        if isinstance(description_html, str):
            description = _text(_parse_html(description_html))
            if description:
                return description, posting

    return "", posting


class ScraperLinkedIn(BaseScraper):
    source: ClassVar[str] = "linkedin"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        page_delay_seconds: float = 4.0,
        detail_delay_seconds: float = 3.0,
        jitter_seconds: float = 1.0,
        location: str = DEFAULT_LOCATION,
        max_pages: int = 10,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self.page_delay = page_delay_seconds
        self.detail_delay = detail_delay_seconds
        self.jitter = jitter_seconds
        self.location = location
        self.max_pages = max_pages

    async def __aenter__(self) -> ScraperLinkedIn:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS, timeout=httpx.Timeout(20.0)
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ScraperLinkedIn must be used inside `async with` context")
        return self._client

    async def search(self, keyword: str, limit: int) -> list[JobListingDraft]:
        drafts: list[JobListingDraft] = []
        seen: set[str] = set()
        start = 0
        page = 0

        while len(drafts) < limit and page < self.max_pages:
            html = await self._fetch_search_page(keyword, start)
            page_drafts = self._drafts_from_search_html(html)
            if not page_drafts:
                break

            for draft in page_drafts:
                if draft.source_id in seen:
                    continue
                seen.add(draft.source_id)
                drafts.append(draft)
                if len(drafts) >= limit:
                    break

            if len(page_drafts) < PAGE_SIZE:
                break
            page += 1
            start += PAGE_SIZE
            await self._sleep(self.page_delay)

        return drafts

    async def fetch_detail(self, draft: JobListingDraft) -> JobListingDraft:
        detail_url = DETAIL_URL_FMT.format(job_id=draft.source_id)
        try:
            r = await self.client.get(
                detail_url,
                headers={"Referer": draft.url or JOB_PAGE_FMT.format(job_id=draft.source_id)},
            )
            _raise_if_rate_limited(r, context=f"detail {draft.source_id}")
            r.raise_for_status()
        except RateLimitedError:
            raise
        except httpx.HTTPError as exc:
            log.warning("linkedin detail fetch failed for %s: %s", draft.source_id, exc)
            return draft

        description, posting = _description_from_detail(r.text)
        if description:
            draft.description = description
        if posting is not None:
            draft.raw_json = posting
            if not draft.company:
                draft.company = _company_from_jsonld(posting)
            title = posting.get("title")
            if not draft.title and isinstance(title, str):
                draft.title = title.strip()
        else:
            draft.raw_json = {
                "source": self.source,
                "source_id": draft.source_id,
                "detail_url": detail_url,
            }

        await self._sleep(self.detail_delay)
        return draft

    async def _fetch_search_page(self, keyword: str, start: int) -> str:
        params = {
            "keywords": keyword,
            "location": self.location,
            "start": str(start),
        }
        r = await self.client.get(SEARCH_URL, params=params)
        _raise_if_rate_limited(r, context=f"search start={start}")
        r.raise_for_status()
        return r.text

    def _drafts_from_search_html(self, html: str) -> list[JobListingDraft]:
        root = _parse_html(html)
        drafts: list[JobListingDraft] = []
        for card in _walk(root):
            entity = card.attrs.get("data-entity-urn", "")
            if "jobPosting" not in entity and not _has_class(card, "base-card"):
                continue

            link = _first_node(
                card,
                lambda node: node.tag == "a"
                and (
                    _has_class(node, "base-card__full-link")
                    or "/jobs/view/" in node.attrs.get("href", "")
                ),
            )
            href = link.attrs.get("href", "") if link is not None else ""
            job_id = _extract_job_id(entity) or _extract_job_id(href)
            if job_id is None:
                continue

            drafts.append(
                JobListingDraft(
                    source=self.source,
                    source_id=job_id,
                    title=self._first_card_text(
                        card,
                        ("base-search-card__title", "job-search-card__title"),
                        fallback_tags=("h3",),
                    ),
                    company=self._first_card_text(
                        card,
                        ("base-search-card__subtitle", "job-search-card__subtitle"),
                        fallback_tags=("h4",),
                    ),
                    url=_clean_linkedin_url(href, job_id),
                    location=self._first_card_text(
                        card,
                        (
                            "job-search-card__location",
                            "base-search-card__metadata",
                            "job-result-card__location",
                        ),
                    )
                    or None,
                    description="",
                )
            )
        return drafts

    def _first_card_text(
        self,
        card: _Node,
        class_names: tuple[str, ...],
        *,
        fallback_tags: tuple[str, ...] = (),
    ) -> str:
        node = _first_node(
            card,
            lambda candidate: any(_has_class(candidate, name) for name in class_names),
        )
        if node is None and fallback_tags:
            node = _first_node(card, lambda candidate: candidate.tag in fallback_tags)
        return _text(node) if node is not None else ""

    async def _sleep(self, base_delay: float) -> None:
        if base_delay <= 0:
            return
        jitter = random.uniform(0, self.jitter) if self.jitter > 0 else 0
        await asyncio.sleep(base_delay + jitter)
