"""ScraperLinkedIn unit tests - mocked httpx, no network."""
from __future__ import annotations

import json

import httpx
import pytest

from backend.app.services.scrapers.base import JobListingDraft
from backend.app.services.scrapers.scraper_linkedin import (
    DETAIL_URL_FMT,
    SEARCH_URL,
    RateLimitedError,
    ScraperLinkedIn,
    _clean_linkedin_url,
    _description_from_detail,
    _extract_job_id,
)


def _search_card(
    job_id: str,
    title: str = "Backend Engineer",
    *,
    company: str = "Acme Co",
    location: str = "Taipei City",
    href: str | None = None,
) -> str:
    href = href or f"https://www.linkedin.com/jobs/view/backend-engineer-{job_id}?trk=guest"
    return f"""
    <li>
      <div class="base-card" data-entity-urn="urn:li:jobPosting:{job_id}">
        <a class="base-card__full-link" href="{href}">View job</a>
        <h3 class="base-search-card__title">{title}</h3>
        <h4 class="base-search-card__subtitle"><a>{company}</a></h4>
        <span class="job-search-card__location">{location}</span>
      </div>
    </li>
    """


def _search_html(cards: list[str]) -> str:
    return "<ul>" + "\n".join(cards) + "</ul>"


def _detail_html(description_html: str) -> str:
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Backend Engineer",
        "description": "<p>Fallback description</p>",
        "hiringOrganization": {"@type": "Organization", "name": "Acme Co"},
    }
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps(posting)
        + "</script>"
        "</head><body>"
        '<section class="show-more-less-html">'
        '<div class="show-more-less-html__markup">'
        + description_html
        + "</div></section>"
        "</body></html>"
    )


def _make_handler(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/jobs-guest/jobs/api/seeMoreJobPostings/search":
            start = request.url.params.get("start", "0")
            key = f"search:{start}"
            if key in routes:
                return routes[key]
        if path.startswith("/jobs-guest/jobs/api/jobPosting/"):
            job_id = path.rsplit("/", 1)[-1]
            key = f"detail:{job_id}"
            if key in routes:
                return routes[key]
        return httpx.Response(404, text="no route")

    return handler


def _client(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(_make_handler(routes)),
        base_url="https://www.linkedin.com",
    )


def test_extract_job_id_handles_urn():
    assert _extract_job_id("urn:li:jobPosting:2504190020") == "2504190020"


def test_extract_job_id_handles_detail_and_view_urls():
    assert _extract_job_id(DETAIL_URL_FMT.format(job_id="2504190020")) == "2504190020"
    assert (
        _extract_job_id(
            "https://www.linkedin.com/jobs/view/backend-engineer-at-acme-2504190020"
        )
        == "2504190020"
    )
    assert (
        _extract_job_id("https://www.linkedin.com/jobs/view/foo?currentJobId=123456")
        == "123456"
    )


def test_clean_linkedin_url_strips_query_and_uses_fallback():
    assert _clean_linkedin_url(
        "https://www.linkedin.com/jobs/view/backend-123?trk=x", "123"
    ) == "https://www.linkedin.com/jobs/view/backend-123"
    assert _clean_linkedin_url("", "123") == "https://www.linkedin.com/jobs/view/123"


def test_description_from_detail_prefers_visible_markup():
    description, posting = _description_from_detail(
        _detail_html("<p>Build APIs.</p><ul><li>Python</li></ul>")
    )
    assert "Build APIs" in description
    assert "Python" in description
    assert "<p>" not in description
    assert posting is not None
    assert posting["@type"] == "JobPosting"


@pytest.mark.asyncio
async def test_search_returns_drafts_and_paginates():
    first_page = [_search_card(str(i)) for i in range(25)]
    routes = {
        "search:0": httpx.Response(200, text=_search_html(first_page)),
        "search:25": httpx.Response(
            200,
            text=_search_html(
                [
                    _search_card("25", title="Senior Backend Engineer"),
                    _search_card("26", title="Java Engineer"),
                ]
            ),
        ),
    }
    async with _client(routes) as c:
        async with ScraperLinkedIn(
            client=c,
            page_delay_seconds=0,
            detail_delay_seconds=0,
            jitter_seconds=0,
        ) as s:
            drafts = await s.search("backend engineer", limit=27)

    assert len(drafts) == 27
    assert drafts[0].source == "linkedin"
    assert drafts[0].source_id == "0"
    assert drafts[0].title == "Backend Engineer"
    assert drafts[0].company == "Acme Co"
    assert drafts[0].location == "Taipei City"
    assert drafts[0].url == "https://www.linkedin.com/jobs/view/backend-engineer-0"
    assert drafts[-1].source_id == "26"


@pytest.mark.asyncio
async def test_search_respects_limit_and_dedupes():
    routes = {
        "search:0": httpx.Response(
            200,
            text=_search_html(
                [
                    _search_card("1"),
                    _search_card("1", title="Duplicate"),
                    _search_card("2"),
                    _search_card("3"),
                ]
            ),
        ),
    }
    async with _client(routes) as c:
        async with ScraperLinkedIn(
            client=c,
            page_delay_seconds=0,
            detail_delay_seconds=0,
            jitter_seconds=0,
        ) as s:
            drafts = await s.search("backend", limit=2)

    assert [d.source_id for d in drafts] == ["1", "2"]


@pytest.mark.asyncio
async def test_search_raises_on_rate_limit():
    routes = {"search:0": httpx.Response(429, text="slow down")}
    async with _client(routes) as c:
        async with ScraperLinkedIn(
            client=c,
            page_delay_seconds=0,
            detail_delay_seconds=0,
            jitter_seconds=0,
        ) as s:
            with pytest.raises(RateLimitedError):
                await s.search("backend", limit=10)


@pytest.mark.asyncio
async def test_fetch_detail_extracts_description_and_jsonld():
    routes = {
        "detail:2504190020": httpx.Response(
            200,
            text=_detail_html("<p>Build platform APIs.</p><br><p>5+ years.</p>"),
        ),
    }
    async with _client(routes) as c:
        async with ScraperLinkedIn(
            client=c,
            page_delay_seconds=0,
            detail_delay_seconds=0,
            jitter_seconds=0,
        ) as s:
            draft = JobListingDraft(
                source="linkedin",
                source_id="2504190020",
                title="",
                company="",
                url="https://www.linkedin.com/jobs/view/backend-engineer-2504190020",
            )
            enriched = await s.fetch_detail(draft)

    assert "Build platform APIs" in enriched.description
    assert "5+ years" in enriched.description
    assert enriched.raw_json is not None
    assert enriched.raw_json["@type"] == "JobPosting"
    assert enriched.title == "Backend Engineer"
    assert enriched.company == "Acme Co"


@pytest.mark.asyncio
async def test_fetch_detail_keeps_draft_on_http_error():
    routes = {"detail:2504190020": httpx.Response(500, text="boom")}
    async with _client(routes) as c:
        async with ScraperLinkedIn(
            client=c,
            page_delay_seconds=0,
            detail_delay_seconds=0,
            jitter_seconds=0,
        ) as s:
            draft = JobListingDraft(
                source="linkedin",
                source_id="2504190020",
                title="Backend",
                company="Acme",
                url="https://www.linkedin.com/jobs/view/backend-engineer-2504190020",
                description="snippet",
            )
            enriched = await s.fetch_detail(draft)

    assert enriched.description == "snippet"
    assert enriched.raw_json is None


@pytest.mark.asyncio
async def test_fetch_detail_raises_on_rate_limit():
    routes = {"detail:2504190020": httpx.Response(999, text="blocked")}
    async with _client(routes) as c:
        async with ScraperLinkedIn(
            client=c,
            page_delay_seconds=0,
            detail_delay_seconds=0,
            jitter_seconds=0,
        ) as s:
            draft = JobListingDraft(
                source="linkedin",
                source_id="2504190020",
                title="Backend",
                company="Acme",
                url="https://www.linkedin.com/jobs/view/backend-engineer-2504190020",
            )
            with pytest.raises(RateLimitedError):
                await s.fetch_detail(draft)


_ = SEARCH_URL
