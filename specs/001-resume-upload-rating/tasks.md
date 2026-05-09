# Tasks

**Spec authority**: `spec.md` (three-tier evaluation flow)
**Roadmap**: `specs/roadmap.md`

TDD: write tests RED before implementation.

---

## Phase 1 — Core (complete)

### P1-T01 · Schema + Migration ✅
- [x] `0002_poc_schema.py`: `baseline_profile`, `job_analyses`, `generated_resumes`
- [x] `0003_three_tier_fields.py`: `status`, `can_submit`, `skip_reason`, `explanation`, `strengths`, `gaps`
- [x] ORM models: `baseline_profile.py`, `job_analysis.py`, `generated_resume.py`

### P1-T02 · Pydantic Schemas ✅
- [x] `schemas/profile.py`: `ProfileIn`, `ProfileOut`
- [x] `schemas/evaluate.py`: `EvaluateIn`, `EvaluateOut`, `CallbackIn`, `HistoryItemOut`, `HistoryDetailOut`, `SubmittableResumeOut`

### P1-T03 · Services ✅
- [x] `services/evaluator_v2.py`: read baseline → call LLM → three-tier classification
- [x] `services/hashing.py`: `jd_hash()` deduplication
- [x] `workers/tailor.py`: background tailoring using saved baseline profile
- [x] `services/llm/anthropic.py`: `evaluate()` and `tailor()` via Anthropic API
- [x] `services/llm/fake.py`: deterministic stub for tests

### P1-T04 · API Endpoints ✅

| Endpoint | Test file | Status |
|----------|-----------|--------|
| `POST /api/profile` | `test_profile_endpoint.py` | ✅ |
| `POST /api/profile/upload` | — | ✅ (PDF → pypdf extract → upsert) |
| `GET /api/profile` | `test_profile_endpoint.py` | ✅ |
| `POST /api/evaluate` | `test_evaluate_endpoint.py` | ✅ |
| `POST /api/callback` | `test_callback_endpoint.py` | ✅ |
| `GET /api/history` | `test_history_endpoint.py` | ✅ |
| `GET /api/history/{id}` | `test_history_detail.py` | ✅ |
| `GET /api/submittable` | `test_submittable_endpoint.py` | ✅ |

**Bug fixes shipped with P1-T04:**
- `upsert_baseline`: strips NUL (`\x00`) bytes before DB write (fixes 500 on PDF-pasted text)
- `set_profile`: `ValueError` now returns HTTP 400 with message instead of crashing

### P1-T05 · Three-tier logic tests ✅
- [x] `test_three_tier_evaluate.py`: ready_to_submit / needs_tailoring / skip
- [x] `test_tailor_worker.py`: tailoring uses baseline profile, not JD

### P1-T06 · E2E UI ✅
- [x] `static/app.js`: Evaluate tab, History tab, Profile tab
- [x] `static/index.html`: single-page app
- [x] Profile tab: PDF file picker replaces textarea input; extracted text shown as read-only preview

### P1-T08 · Post-#16 cleanup wave ✅ (PRs #31–#35, 2026-05-07)
- [x] **#31 ci/mypy-soft-gate** — `Type check (mypy, soft gate)` step in pr-review.yml with `continue-on-error: true`
- [x] **#32 ci/shell-script-gate** — `.gitattributes` pins `*.sh` to `eol=lf`; CI runs `bash -n` against `e2e-check.sh`/`start.sh`/`restart-app.sh`
- [x] **#33 refactor/remove-v1-deadcode** — deleted orphaned v1 surface: `api/{resumes,jobs,evaluations}.py`, `services/{evaluator,storage}.py`, `workers/tasks.py`, v1 models + schemas, 6 v1 integration tests; closes the `_job_description` cross-session bug from #26
- [x] **#34 chore/python311-policy** — drop Py3.9, ruff target `py311`, re-enable `UP`, `requires-python = ">=3.11"`, `.python-version`, README/CLAUDE.md state the floor + rationale
- [x] **#35 feat/persist-uploaded-pdf** — alembic 0005 adds `baseline_profile.pdf_path TEXT NULL`; `/api/profiles/upload` and `/api/profile/upload` now write the original bytes under `${STORAGE_DIR}/profiles/<id>/<utc-ts>.pdf` and store the absolute path on the row

### P1-T07 · Multi-Profile CRUD + Profile-Scoped Evaluation ✅ (PR #17)
- [x] `0004_multi_profile.py`: add `name`/`created_at` to `baseline_profile`; add `profile_id` FK on `job_analyses` (SET NULL); drop `jd_hash` unique; add composite unique `(jd_hash, profile_id)`
- [x] `models/baseline_profile.py`: add `name`, `created_at` columns
- [x] `models/job_analysis.py`: add `profile_id` FK column
- [x] `schemas/profile.py`: `ProfileIn` adds `name`; new `ProfileUpdateIn`; `ProfileOut` adds `name`, `created_at`
- [x] `schemas/evaluate.py`: `EvaluateIn` adds `profile_id`; `HistoryItemOut` adds `profile_id`
- [x] `services/evaluator_v2.py`: full CRUD (`list_profiles`, `get_profile`, `create_profile`, `update_profile`, `delete_profile`); `evaluate_jd` resolves profile by `profile_id` or latest; cache scoped to `(jd_hash, profile_id)`
- [x] `api/profile.py`: `GET/POST/PUT/DELETE /api/profiles`; `POST /api/profiles/upload`; legacy singular endpoints preserved
- [x] `workers/tailor.py`: looks up profile by `job.profile_id` (falls back to latest)
- [x] `static/index.html` + `app.js`: Profile tab table + Add form; Evaluate tab profile selector dropdown
- [x] `tests/integration/v2/test_profiles_endpoint.py`: 14 tests covering CRUD, upload, cache isolation, legacy compat

---

## Phase 2 — Bulk Ingestion (in progress)

### P2-T01 · Bulk JD Evaluate endpoint
- [ ] `schemas/evaluate.py`: add `BulkEvaluateIn`, `BulkEvaluateResult`, `BulkEvaluateOut`
- [ ] `api/evaluate.py`: add `POST /api/evaluate/bulk`
  - Deduplicate by jd_hash
  - Trigger background tailoring per new needs_tailoring job
  - Return totals: `total`, `new`, `cached`
- [ ] Test: `tests/integration/v2/test_bulk_evaluate.py`
  - bulk returns correct totals
  - duplicate JDs in same batch are cached
  - needs_tailoring JDs trigger tailoring tasks

---

## Phase 2.5 — Job-board crawlers (in progress, epic #38)

### P2.5-T01 · JobListing model + scraper interface ✅ (issue #39)
- [x] `models/job_listing.py`: `(source, source_id)` unique, JSONB `raw_json`, FK `job_analysis_id` (SET NULL)
- [x] `services/scrapers/base.py`: `BaseScraper` ABC + `JobListingDraft` dataclass
- [x] `alembic/versions/0006_job_listings.py`: create `job_listings` table + indexes
- [x] `tests/integration/v2/test_job_listing.py`: persistence, unique constraint, BaseScraper abstract

### P2.5-T02 · 104 scraper (issue #40) ✅
- [x] `services/scrapers/scraper_104.py`: search via public `/jobs/search/api/jobs`, detail via `/job/ajax/content/{slug}` (slug pulled from `link.job`)
- [x] `services/scrapers/persistence.py`: `upsert_drafts()` with Postgres `ON CONFLICT DO NOTHING` on `uq_job_listings_source`
- [x] `tests/unit/test_scraper_104.py` (9 tests, mocked httpx) + `tests/integration/v2/test_scraper_persistence.py` (3 tests)

### P2.5-T03 · Yourator scraper (issue #41) ✅
- [x] `services/scrapers/scraper_yourator.py`: paginates `/api/v4/jobs?page=N` until `hasMore=false` (server-side `term`/`keyword` filters are no-ops, so we filter titles client-side)
- [x] Detail enrichment: GET the public job HTML page, extract description from the embedded `application/ld+json` JobPosting block (no working JSON detail endpoint)
- [x] `tests/unit/test_scraper_yourator.py` (13 tests, mocked httpx): pagination via `hasMore`, dedup, case-insensitive title match, JSON-LD extraction, HTTP-error fallback

### P2.5-T04 · LinkedIn scraper (P2, issue #42)
- [ ] `services/scrapers/scraper_linkedin.py`: guest jobs HTML; rate-limit handling

### P2.5-T05 · Batch evaluator (issue #43)
- [ ] `services/batch_evaluator.py`: pull unevaluated JobListings → evaluator_v2 → JobAnalysis; trigger tailor.py for `needs_tailoring`

### P2.5-T06 · CLI / API trigger (issue #44)
- [ ] `app/cli.py scrape --source ... --keyword ... --limit N`
- [ ] `POST /api/scrape/run`, `GET /api/scrape/status`

### P2.5-T07 · JD database browser ✅ (PR #62)
- [x] `GET /api/job-listings` — list with `q` / `source` / `analyzed` / pagination
- [x] `static/jobs.html` + `static/jobs.js` — browse + filter scraped JDs

### P2.5-T08 · Batch JD scoring from DB ✅ (PR #64)
- [x] `POST /api/evaluate/by-listings` — score selected listings, link `JobListing.job_analysis_id` back, surface per-row errors
- [x] `tests/integration/v2/test_evaluate_by_listings.py`
- [x] JD length guard (`max_jd_chars`) on `/api/evaluate`, `/api/evaluate/bulk`, `/api/evaluate/by-listings`

### P2.5-T09 · LLM + upload hardening ✅ (PR #65, closes #48)
- [x] `LLMUnavailableError` / `LLMInvalidOutputError` mapped to 503 / 502 in evaluate endpoints
- [x] `_read_pdf_upload` enforces `max_upload_bytes` for both `/api/profile/upload` and `/api/profiles/upload`
- [x] `services/llm/factory.py` — `LLM_BACKEND` env selects `claude_cli` vs `anthropic` vs `fake`
- [x] `tests/integration/v2/test_migrations.py` — alembic upgrade head smoke test
- [x] `.env.example` documents the LLM_BACKEND choice

### P2.5-T10 · Generated resume PDF download ✅ (PR #80)
- [x] `GET /api/generated-resumes/{id}/pdf` — generate-on-demand and serve via `FileResponse`
- [x] `services/pdf.py` writes PDFs under `STORAGE_DIR/generated/`
- [x] `tests/unit/test_pdf.py`

### P2.5-T11 · Restore app startup + preserve callback pdf_url ✅ (PR #81)
- [x] `download_generated_resume_pdf` decorator gets `response_model=None` so FastAPI does not try to build a Pydantic response model from `FileResponse | JSONResponse` (was crashing app construction → 61 integration tests in ERROR)
- [x] `POST /api/callback` only generates + points at a local PDF when the caller did not supply `pdf_url` — restores the contract for externally-hosted PDFs

### P2.5-T13 · E2E DB isolation + scrape backup ✅ (issue #87)
- [x] `tools/e2e/tests/conftest.py` — testcontainers postgres per session; uvicorn always bound to that DB; `DATABASE_URL` is no longer read from the parent env
- [x] `clean_db` is opt-in (no longer autouse); `seeded_profile` / `seeded_listings` depend on it
- [x] `.github/workflows/e2e.yml` — postgres service container removed (testcontainers handles it)
- [x] `scripts/e2e.sh` — no longer exports `DATABASE_URL`
- [x] `scripts/scrape_jobs.py` — writes a CSV snapshot of `job_listings` to `backend/storage/backups/job_listings-<ts>.csv` after each successful run, so data survives accidental DB wipes
- [x] Verified locally: dev DB row counts identical before/after `scripts/e2e.sh`

### P2.5-T12 · Playwright E2E suite ✅ (issue #84, PRs #83 + this one)
- [x] `tools/e2e/tests/` — 5 flow tests: paste-JD evaluate, profile PDF upload, batch analyze from DB, submittable PDF download, history drilldown
- [x] `tools/e2e/tests/conftest.py` — session uvicorn boot, autouse table truncation, `seeded_profile` / `seeded_listings`
- [x] `backend/app/services/llm/fake.py` — `[[score=N]]` JD marker so different tests can request different scores against one shared uvicorn process
- [x] `.github/workflows/e2e.yml` — runs `pytest tools/e2e/tests/`, uploads `tools/e2e/screenshots/` as 30-day artifact, uploads uvicorn log on failure
- [x] `scripts/e2e.sh` — local runner; bootstraps Playwright on first call
- [x] `pyproject.toml` — `[project.optional-dependencies] e2e` group

---

## Phase 3 — Roadmap (future)

- Crawler / external job ingestion pipeline (n8n removed; will be re-introduced as a separate service if/when needed — `/api/callback` already accepts external resume delivery)
- Multi-user authentication
- PDF generation (weasyprint)
- PDF blob storage (move `baseline_profile.pdf_path` from local disk to S3 — column is already TEXT, scheme-swap only)
- LLM audit log (token cost / latency)
- Type-check cleanup PRs to drop `continue-on-error` from the mypy gate
- Kubernetes deployment
