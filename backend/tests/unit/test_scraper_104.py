"""Scraper104 unit tests — mocked httpx, no network."""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from backend.app.services.scrapers.scraper_104 import (
    DETAIL_URL_FMT,
    SEARCH_URL,
    Scraper104,
    _extract_slug,
)


def _search_payload(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"data": jobs, "metadata": {}}


def _job(job_no: str, slug: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "jobNo": job_no,
        "jobName": f"Backend Engineer {job_no}",
        "custName": "Acme Co",
        "jobAddrNoDesc": "台北市內湖區",
        "description": "short snippet",
        "link": {"job": f"https://www.104.com.tw/job/{slug}"},
    }
    base.update(overrides)
    return base


def _detail_payload(description: str) -> dict[str, Any]:
    return {"data": {"jobDetail": {"jobDescription": description}}}


def _make_handler(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        # Match by path so tests don't have to encode every query param
        path = request.url.path
        if path == "/jobs/search/api/jobs":
            page = request.url.params.get("page", "1")
            key = f"search:{page}"
            if key in routes:
                return routes[key]
        if path.startswith("/job/ajax/content/"):
            slug = path.rsplit("/", 1)[-1]
            key = f"detail:{slug}"
            if key in routes:
                return routes[key]
        return httpx.Response(404, json={"error": "no route"})

    return handler


def _client(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(_make_handler(routes)),
        base_url="https://www.104.com.tw",
    )


def test_extract_slug_handles_https():
    assert _extract_slug("https://www.104.com.tw/job/81utd") == "81utd"


def test_extract_slug_handles_protocol_relative():
    assert _extract_slug("//www.104.com.tw/job/abc") == "abc"


def test_extract_slug_returns_none_for_garbage():
    assert _extract_slug("") is None
    assert _extract_slug("https://example.com/foo/bar") is None


@pytest.mark.asyncio
async def test_search_returns_drafts(httpx_mock_short_pages: dict):
    routes = {
        "search:1": httpx.Response(
            200,
            json=_search_payload(
                [_job("1", "slug-1"), _job("2", "slug-2"), _job("3", "slug-3")]
            ),
        ),
    }
    async with _client(routes) as c:
        async with Scraper104(client=c, page_delay_seconds=0, detail_delay_seconds=0) as s:
            drafts = await s.search("java", limit=10)
    assert [d.source_id for d in drafts] == ["1", "2", "3"]
    assert all(d.source == "104" for d in drafts)
    assert drafts[0].url == "https://www.104.com.tw/job/slug-1"
    assert drafts[0].location == "台北市內湖區"


@pytest.mark.asyncio
async def test_search_respects_limit():
    routes = {
        "search:1": httpx.Response(
            200,
            json=_search_payload([_job(str(i), f"s-{i}") for i in range(20)]),
        ),
        "search:2": httpx.Response(
            200,
            json=_search_payload([_job(str(i), f"s-{i}") for i in range(20, 40)]),
        ),
    }
    async with _client(routes) as c:
        async with Scraper104(client=c, page_delay_seconds=0, detail_delay_seconds=0) as s:
            drafts = await s.search("java", limit=5)
    assert len(drafts) == 5
    assert [d.source_id for d in drafts] == ["0", "1", "2", "3", "4"]


@pytest.mark.asyncio
async def test_search_dedupes_within_run():
    """If 104 returns the same jobNo twice (it happens), we only emit once."""
    dup_job = _job("dup", "slug-dup")
    routes = {
        "search:1": httpx.Response(
            200,
            json=_search_payload([dup_job, _job("other", "slug-other"), dup_job]),
        ),
    }
    async with _client(routes) as c:
        async with Scraper104(client=c, page_delay_seconds=0, detail_delay_seconds=0) as s:
            drafts = await s.search("java", limit=10)
    assert [d.source_id for d in drafts] == ["dup", "other"]


@pytest.mark.asyncio
async def test_search_stops_on_short_page():
    routes = {
        "search:1": httpx.Response(
            200,
            json=_search_payload([_job(str(i), f"s-{i}") for i in range(3)]),
        ),
    }
    async with _client(routes) as c:
        async with Scraper104(client=c, page_delay_seconds=0, detail_delay_seconds=0) as s:
            drafts = await s.search("java", limit=100)
    assert len(drafts) == 3


@pytest.mark.asyncio
async def test_fetch_detail_fills_full_description():
    routes = {
        "detail:slug-1": httpx.Response(
            200,
            json=_detail_payload("FULL JD with 2000+ chars of stuff."),
        ),
    }
    async with _client(routes) as c:
        async with Scraper104(client=c, page_delay_seconds=0, detail_delay_seconds=0) as s:
            from backend.app.services.scrapers.base import JobListingDraft

            draft = JobListingDraft(
                source="104",
                source_id="1",
                title="t",
                company="c",
                url="https://www.104.com.tw/job/slug-1",
                description="snippet",
            )
            enriched = await s.fetch_detail(draft)
    assert enriched.description == "FULL JD with 2000+ chars of stuff."
    assert enriched.raw_json is not None
    assert "jobDetail" in enriched.raw_json


@pytest.mark.asyncio
async def test_fetch_detail_keeps_snippet_on_http_error():
    routes = {
        "detail:slug-1": httpx.Response(500, json={"error": "boom"}),
    }
    async with _client(routes) as c:
        async with Scraper104(client=c, page_delay_seconds=0, detail_delay_seconds=0) as s:
            from backend.app.services.scrapers.base import JobListingDraft

            draft = JobListingDraft(
                source="104",
                source_id="1",
                title="t",
                company="c",
                url="https://www.104.com.tw/job/slug-1",
                description="snippet",
            )
            enriched = await s.fetch_detail(draft)
    assert enriched.description == "snippet"
    assert enriched.raw_json is None


@pytest.fixture
def httpx_mock_short_pages():
    """Placeholder fixture — kept so the signature is documented and we can
    add shared search payloads later if multiple tests need them."""
    return {}


# Keep imports referenced so linters don't strip them
_ = (json, SEARCH_URL, DETAIL_URL_FMT)
