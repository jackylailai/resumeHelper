# Scrapers

This page documents *how* resumeHelper gets job listings out of each source —
endpoints, headers, listing-to-detail handoff, keyword handling, pagination,
and known fragilities. It is intentionally low-level. For the UI side, see
[`/scrapes.html` controls in the readme](../readme.md#scrape-scheduling); for
scheduling, see [`scheduling.md`](scheduling.md).

Code lives in `backend/app/services/scrapers/`. All sources are registered in
`registry.py` and orchestrated by `pipeline.py`.

## Architecture

Every source implements `BaseScraper` (`base.py`):

```python
class BaseScraper(ABC):
    async def search(self, keyword: str, limit: int) -> list[JobListingDraft]: ...
    async def fetch_detail(self, draft: JobListingDraft) -> JobListingDraft: ...
```

The pipeline (`pipeline.scrape_with_runner`) runs in two phases:

1. `search()` returns lightweight `JobListingDraft`s populated with the
   cheap-to-fetch fields (title, company, url, location). Description may be
   empty at this point.
2. `fetch_detail()` is awaited per draft to fill in `description` (and
   `raw_json` when useful) from a per-listing detail endpoint or page.

After both phases, `persistence.upsert_drafts_with_stats` writes drafts to
`job_listings`, deduplicated by `(source, source_id)`.

All scrapers:

- use `httpx.AsyncClient` with a Chrome-like `User-Agent`,
- guard against repeated pagination with their own `max_pages` (or by detecting
  short pages / `hasMore=false`),
- sleep `page_delay_seconds` between search pages and `detail_delay_seconds`
  between detail fetches for politeness,
- are context managers (`async with`) so the HTTP client is closed cleanly.

`SCRAPERS` in `registry.py` maps source name → class. `resolve_sources("all")`
returns the default-safe set (104 + Yourator); `"all_with_linkedin"` adds
LinkedIn.

## 104 — `Scraper104`

File: `backend/app/services/scrapers/scraper_104.py`

| Aspect | Value |
|---|---|
| Mechanism | JSON API (no HTML scraping) |
| Search endpoint | `GET https://www.104.com.tw/jobs/search/api/jobs` |
| Detail endpoint | `GET https://www.104.com.tw/job/ajax/content/{slug}` |
| Keyword handling | **Server-side** — passed as `keyword` query param |
| Pagination | `page` query param; ~20 results per page; a short page (<20) signals end |
| Politeness | `page_delay=1.5s`, `detail_delay=0.8s` |
| Description source | `data.jobDetail.jobDescription` in the detail JSON |
| Required headers | Chrome `User-Agent`, `Referer: https://www.104.com.tw/jobs/search/` |

Notable quirks:

- The detail endpoint takes a **slug**, not the numeric `jobNo`. The slug is
  extracted from `link.job` (which may start with `//` and needs an `https:`
  prefix) — see `_extract_slug`.
- The `Referer` on the detail call is set to the public job page for that slug
  to look like a normal browser session.
- `description` may already be populated on the search payload (`item.description`);
  `fetch_detail` will overwrite it with the richer body if available.

Fragility: the `data.data[].link.job` shape and the `data.jobDetail.jobDescription`
path are 104-internal JSON conventions. If 104 reshapes their search/detail
response, the relevant `_draft_from_search` and `fetch_detail` paths break loudly
(missing-key paths fall back to empty strings — listings still insert, just
without description).

## Yourator — `ScraperYourator`

File: `backend/app/services/scrapers/scraper_yourator.py`

| Aspect | Value |
|---|---|
| Mechanism | JSON API for search + HTML page for detail (JSON-LD extraction) |
| Search endpoint | `GET https://www.yourator.co/api/v4/jobs` |
| Detail endpoint | Public job page (`{BASE}/{path}`) — extract `<script type="application/ld+json">` |
| Keyword handling | **Client-side, title-only** (see below) |
| Pagination | `page` query param; uses `payload.hasMore` / `payload.nextPage`; capped at `max_pages=50` |
| Politeness | `page_delay=1.5s`, `detail_delay=0.8s` |
| Description source | JSON-LD `JobPosting.description` (HTML-flavoured; stripped to plain text) |
| Required headers | Chrome `User-Agent`, `Accept: application/json` |

Notable quirks:

- **Yourator's `/api/v4/jobs` ignores `term` / `keyword` / `categories`** at the
  time of writing — it returns the same paginated feed regardless. We still
  send `term` for parity with the website's own requests, but the real keyword
  filter runs in `search()` against `draft.title.lower()`:

  ```python
  needle = keyword.lower().strip()
  ...
  if needle and needle not in draft.title.lower():
      continue
  ```

  This means wider keywords yield more rows because the filter is matched only
  against the **job title**, not the JD body. The JD body is fetched later by
  `fetch_detail()` and is not part of any filter today (issue #141 covers
  extending this).
- Detail extraction reads the first `<script type="application/ld+json">`
  whose `@type == "JobPosting"`. If the page lacks JSON-LD, the description
  stays empty and the listing still persists.
- HTML-to-text conversion handles `<br>`, `</p>`, and a small set of HTML
  entities — it is intentionally not a full HTML parser.

Fragility: depends on Yourator publishing JSON-LD on the detail page. If they
remove it or change `@type`, descriptions stop being captured.

## LinkedIn — `ScraperLinkedIn`

File: `backend/app/services/scrapers/scraper_linkedin.py`

| Aspect | Value |
|---|---|
| Mechanism | HTML scraping (guest endpoints — no login) |
| Search endpoint | `GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search` |
| Detail endpoint | `GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}` |
| Keyword handling | **Server-side** — passed as `keywords` query param |
| Pagination | `start` query param + page size 25; capped at `max_pages=10` |
| Politeness | `page_delay=4s`, `detail_delay=3s`, plus `jitter=1s` |
| Description source | `.show-more-less-html__markup`, `description__text`, or `jobs-description-content__text` containers — or JSON-LD `JobPosting.description` as a fallback |
| Location filter | `location=Taiwan` by default (configurable) |
| Required headers | Chrome `User-Agent`, `Accept: text/html`, `Accept-Language: en-US,en;q=0.9,zh-TW;q=0.8` |

Notable quirks:

- **Guest-only** — no LinkedIn account or cookie is needed. The trade-off is
  these endpoints are *the* hot spot for rate limiting; the scraper raises a
  dedicated `RateLimitedError` on HTTP 429/999 (see `_raise_if_rate_limited`)
  and surfaces it up to `pipeline.scrape_with_runner` so the run fails fast
  rather than silently producing empty descriptions.
- The detail call sets `Referer` to the job's public `/jobs/view/{job_id}` URL.
- HTML is parsed by a small custom parser in `scraper_linkedin.py` (see
  `_parse_html`, `_walk`, `_first_node`) — no `beautifulsoup4` dependency.
  Class-name selectors are tried in priority order to absorb LinkedIn's
  occasional CSS-class renames.
- Job IDs are extracted from `data-entity-urn` (`jobPosting:NNN`), the detail
  URL (`/jobPosting/NNN`), or the public view URL (`/jobs/view/...-NNN`). All
  three are tried because LinkedIn's markup varies.

Fragility: highest of the three sources. CSS class names and HTML structure
can change without notice; the scraper degrades gracefully (missing fields
become empty strings) but description capture is the most likely thing to
silently drop.

## Keyword filtering summary

This is the single most surprising part of the scrapers, so it bears
repeating side-by-side:

| Source | Where the keyword filter runs | Matches against |
|---|---|---|
| 104 | server-side | 104's own search index (likely title + description) |
| Yourator | **client-side, in `search()`** | `draft.title` only |
| LinkedIn | server-side | LinkedIn's own search index |

No scraper today filters on the JD `description` body that ends up in
`job_listings.description`. Issue #141 tracks adding an optional
advanced-search filter that runs after `fetch_detail()` and drops drafts whose
body does not match.

## Adding a new scraper

1. Create `backend/app/services/scrapers/scraper_<source>.py`.
2. Subclass `BaseScraper`, set `source: ClassVar[str] = "<source>"`, and
   implement `search()` and `fetch_detail()`. Use `async with` semantics for
   the HTTP client.
3. Register in `registry.SCRAPERS` (and optionally add to `DEFAULT_SOURCES` if
   it should run under `source=all`).
4. Add the source to the `ScrapeSource` literal in `backend/app/schemas/scrape.py`.
5. Add the source option to the dropdown in `static/scrapes.html`.
6. Cover with tests under `backend/tests/` — see the existing 104 / Yourator /
   LinkedIn tests for the fixture pattern (a recorded HTTP response asserted
   against the produced `JobListingDraft`).

Persistence and run bookkeeping are inherited from `pipeline.py` and
`persistence.py` — no changes needed there for a new source.
