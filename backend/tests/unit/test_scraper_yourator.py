"""ScraperYourator unit tests — mocked httpx, no network."""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from backend.app.services.scrapers.base import JobListingDraft
from backend.app.services.scrapers.scraper_yourator import (
    ScraperYourator,
    _extract_jobposting,
    _strip_html,
)


def _payload(jobs: list[dict[str, Any]], *, has_more: bool, next_page: int | None) -> dict[str, Any]:
    return {
        "payload": {
            "hasMore": has_more,
            "currentPage": 1,
            "nextPage": next_page,
            "jobs": jobs,
        }
    }


def _job(
    id_: int,
    name: str,
    *,
    company_path: str = "acme",
    company_brand: str = "Acme Co",
    location: str = "台北市",
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "path": f"/companies/{company_path}/jobs/{id_}",
        "salary": "面議",
        "location": location,
        "company": {"path": f"/companies/{company_path}", "brand": company_brand},
    }


def _detail_html(description_html: str) -> str:
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Backend Engineer",
        "description": description_html,
        "identifier": {"@type": "PropertyValue", "value": "1"},
    }
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps(posting)
        + "</script>"
        "</head><body>page</body></html>"
    )


def _make_handler(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v4/jobs":
            page = request.url.params.get("page", "1")
            key = f"search:{page}"
            if key in routes:
                return routes[key]
        if path.startswith("/companies/"):
            key = f"detail:{path}"
            if key in routes:
                return routes[key]
        return httpx.Response(404, json={"error": "no route"})

    return handler


def _client(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(_make_handler(routes)),
        base_url="https://www.yourator.co",
    )


def test_strip_html_renders_paragraphs_and_breaks():
    html = "<p>hello</p><br><p>world</p>"
    out = _strip_html(html)
    assert "hello" in out and "world" in out
    assert "<p>" not in out
    assert "<br>" not in out


def test_strip_html_decodes_common_entities():
    assert "—" in _strip_html("a &mdash; b")
    assert _strip_html("a &amp; b") == "a & b"


def test_strip_html_handles_empty():
    assert _strip_html("") == ""


def test_extract_jobposting_finds_correct_block():
    html = (
        '<script type="application/ld+json">{"@type":"Organization","name":"x"}</script>'
        '<script type="application/ld+json">{"@type":"JobPosting","title":"t","description":"<p>d</p>"}</script>'
    )
    posting = _extract_jobposting(html)
    assert posting is not None
    assert posting["title"] == "t"


def test_extract_jobposting_returns_none_when_missing():
    assert _extract_jobposting("<html>no ld+json</html>") is None


@pytest.mark.asyncio
async def test_search_filters_by_keyword_and_paginates():
    routes = {
        "search:1": httpx.Response(
            200,
            json=_payload(
                [
                    _job(1, "Frontend Engineer"),
                    _job(2, "Backend Engineer"),
                    _job(3, "Data Analyst"),
                ],
                has_more=True,
                next_page=2,
            ),
        ),
        "search:2": httpx.Response(
            200,
            json=_payload(
                [
                    _job(4, "Senior Backend Developer"),
                    _job(5, "Marketing Lead"),
                ],
                has_more=False,
                next_page=None,
            ),
        ),
    }
    async with _client(routes) as c:
        async with ScraperYourator(
            client=c, page_delay_seconds=0, detail_delay_seconds=0
        ) as s:
            drafts = await s.search("backend", limit=10)
    assert [d.source_id for d in drafts] == ["2", "4"]
    assert all(d.source == "yourator" for d in drafts)
    assert drafts[0].url == "https://www.yourator.co/companies/acme/jobs/2"
    assert drafts[0].location == "台北市"
    assert drafts[0].company == "Acme Co"


@pytest.mark.asyncio
async def test_search_respects_limit():
    routes = {
        "search:1": httpx.Response(
            200,
            json=_payload(
                [_job(i, f"Backend {i}") for i in range(10)],
                has_more=True,
                next_page=2,
            ),
        ),
    }
    async with _client(routes) as c:
        async with ScraperYourator(
            client=c, page_delay_seconds=0, detail_delay_seconds=0
        ) as s:
            drafts = await s.search("backend", limit=3)
    assert [d.source_id for d in drafts] == ["0", "1", "2"]


@pytest.mark.asyncio
async def test_search_stops_when_has_more_false():
    routes = {
        "search:1": httpx.Response(
            200,
            json=_payload(
                [_job(1, "Backend One"), _job(2, "Backend Two")],
                has_more=False,
                next_page=None,
            ),
        ),
    }
    async with _client(routes) as c:
        async with ScraperYourator(
            client=c, page_delay_seconds=0, detail_delay_seconds=0
        ) as s:
            drafts = await s.search("backend", limit=100)
    assert len(drafts) == 2


@pytest.mark.asyncio
async def test_search_dedupes_within_run():
    dup = _job(7, "Backend Dup")
    routes = {
        "search:1": httpx.Response(
            200,
            json=_payload(
                [dup, _job(8, "Backend Eight"), dup],
                has_more=False,
                next_page=None,
            ),
        ),
    }
    async with _client(routes) as c:
        async with ScraperYourator(
            client=c, page_delay_seconds=0, detail_delay_seconds=0
        ) as s:
            drafts = await s.search("backend", limit=10)
    assert [d.source_id for d in drafts] == ["7", "8"]


@pytest.mark.asyncio
async def test_search_keyword_match_is_case_insensitive():
    routes = {
        "search:1": httpx.Response(
            200,
            json=_payload(
                [_job(1, "BACKEND Lead"), _job(2, "QA")],
                has_more=False,
                next_page=None,
            ),
        ),
    }
    async with _client(routes) as c:
        async with ScraperYourator(
            client=c, page_delay_seconds=0, detail_delay_seconds=0
        ) as s:
            drafts = await s.search("backend", limit=10)
    assert [d.source_id for d in drafts] == ["1"]


@pytest.mark.asyncio
async def test_fetch_detail_extracts_jsonld_description():
    routes = {
        "detail:/companies/acme/jobs/1": httpx.Response(
            200,
            text=_detail_html("<p>Build APIs.</p><br><p>5+ years experience.</p>"),
        ),
    }
    async with _client(routes) as c:
        async with ScraperYourator(
            client=c, page_delay_seconds=0, detail_delay_seconds=0
        ) as s:
            draft = JobListingDraft(
                source="yourator",
                source_id="1",
                title="Backend",
                company="Acme",
                url="https://www.yourator.co/companies/acme/jobs/1",
            )
            enriched = await s.fetch_detail(draft)
    assert "Build APIs" in enriched.description
    assert "5+ years" in enriched.description
    assert "<p>" not in enriched.description
    assert enriched.raw_json is not None
    assert enriched.raw_json.get("@type") == "JobPosting"


@pytest.mark.asyncio
async def test_fetch_detail_keeps_draft_on_http_error():
    routes = {
        "detail:/companies/acme/jobs/1": httpx.Response(500, text="boom"),
    }
    async with _client(routes) as c:
        async with ScraperYourator(
            client=c, page_delay_seconds=0, detail_delay_seconds=0
        ) as s:
            draft = JobListingDraft(
                source="yourator",
                source_id="1",
                title="Backend",
                company="Acme",
                url="https://www.yourator.co/companies/acme/jobs/1",
                description="snippet",
            )
            enriched = await s.fetch_detail(draft)
    assert enriched.description == "snippet"
    assert enriched.raw_json is None


@pytest.mark.asyncio
async def test_fetch_detail_keeps_draft_when_no_jsonld():
    routes = {
        "detail:/companies/acme/jobs/1": httpx.Response(
            200, text="<html>no structured data</html>"
        ),
    }
    async with _client(routes) as c:
        async with ScraperYourator(
            client=c, page_delay_seconds=0, detail_delay_seconds=0
        ) as s:
            draft = JobListingDraft(
                source="yourator",
                source_id="1",
                title="Backend",
                company="Acme",
                url="https://www.yourator.co/companies/acme/jobs/1",
                description="snippet",
            )
            enriched = await s.fetch_detail(draft)
    assert enriched.description == "snippet"
    assert enriched.raw_json is None
