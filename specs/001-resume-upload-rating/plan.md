# Implementation Plan: Resume Scoring & Generation

**Branch**: `001-resume-upload-rating` | **Updated**: 2026-05-11 (rev 3)
**Scope authority**: `spec.md`; `scope-correction.md` is retained as historical context.

## Summary

Single-user FastAPI service that:
1. Maintains a **library of baseline profiles** with one default profile.
2. Accepts direct JD text or stored JD Database rows and scores fit (0-100) via LLM against a selected/default profile.
3. If score is in the tailoring band, triggers a **FastAPI BackgroundTask** to generate a tailored resume.
4. Cache scoped to `(jd_hash, profile_id)` so the same JD against different profiles is evaluated independently.
5. Stores analyses, generated resumes/PDF URLs, scraped listings, and tracked applications.
6. Exposes health/readiness checks and optional write-operation auth for non-local deployments.

No resume versioning. No async job queue. Single-user by default.

## Architecture (Phase 1 — POC)

```
Browser
  │
FastAPI (uvicorn, single process)
  ├── GET    /api/profiles          → list all baseline profiles
  ├── POST   /api/profiles          → create profile (text)
  ├── POST   /api/profiles/upload/preview → extract PDF text without persisting
  ├── POST   /api/profiles/upload   → create profile (PDF, pypdf extraction)
  ├── GET    /api/profiles/{id}     → get one profile
  ├── PUT    /api/profiles/{id}     → update profile
  ├── GET    /api/profiles/{id}/delete-impact → profile delete impact counts
  ├── DELETE /api/profiles/{id}     → delete profile
  ├── POST   /api/profile           → legacy: create profile (backward compat)
  ├── GET    /api/profile           → legacy: return default/latest profile
  ├── POST   /api/evaluate          → score JD against selected/default profile; if needed → BackgroundTask
  ├── POST   /api/evaluate/bulk     → score multiple pasted JDs
  ├── POST   /api/evaluate/by-listings → score stored job_listings
  ├── POST   /api/callback          → external resume delivery (e.g. CI pipeline)
  ├── GET    /api/history           → list past job_analyses
  ├── GET    /api/history/{id}      → one analysis + all generated_resumes
  ├── GET    /api/submittable       → analyses with latest generated resume
  ├── GET    /api/generated-resumes/{id}/pdf → generated PDF download
  ├── GET    /api/job-listings      → browse stored scraped JDs
  ├── GET    /api/job-listings/{id} → listing detail
  ├── GET    /api/applications      → list application tracker rows
  ├── POST   /api/applications      → create/update tracked application
  ├── PATCH  /api/applications/{id} → update tracker status/follow-up/notes
  ├── GET    /api/health
  ├── GET    /api/health/live
  └── GET    /api/health/ready
  │
  ├── PostgreSQL  (baseline_profile, job_analyses, generated_resumes, job_listings, applications)
  └── LLM backend selected by LLM_BACKEND
```

## LLM Strategy

| Phase | LLM Backend | Requirement |
|-------|-------------|-------------|
| 1 (POC) | `claude` CLI via subprocess (`ClaudeCLIClient`) | Claude Code subscription |
| 2+ | Anthropic API / Groq (via `LLM_BACKEND` env var) | API key |

Switching is a one-line config change — `LLMClient` Protocol isolates this.

## Technical Context

- **Language**: Python 3.11+ (`requires-python = ">=3.11"`; SQLAlchemy 2.x evaluates `Mapped[...]` at runtime, so PEP 604 unions and `datetime.UTC` rule out 3.9/3.10)
- **Framework**: FastAPI + SQLAlchemy 2.x + Pydantic v2
- **DB**: PostgreSQL 16 (docker-compose, bind-mounted at `${RESUMEHELPER_DATA_PATH:-~/resumeHelper_data}`)
- **LLM (scoring)**: local `claude` CLI → `ClaudeCLIClient`
- **LLM (generation)**: Anthropic SDK directly via FastAPI BackgroundTask in `workers/tailor.py` (n8n removed in #19)
- **PDF storage**: uploaded PDFs persisted under `${STORAGE_DIR}/profiles/<id>/<utc-ts>.pdf`; absolute path stored on `baseline_profile.pdf_path` (#35; S3 deferred)
- **Generated PDFs**: generated resume PDFs are written on demand under `${STORAGE_DIR}/generated/` and served from `/api/generated-resumes/{id}/pdf`
- **Job-board crawlers (Phase 2.5)**: per-source scrapers under `services/scrapers/` implement `BaseScraper`; outputs land in `job_listings`; a separate batch evaluator feeds `evaluator_v2` to keep crawl and scoring decoupled. No headless browser — only public JSON / guest HTML endpoints; failures in one source must not block the others.
- **Application tracker**: `applications` links listings/analyses/generated resumes and stores status, follow-up date, notes.
- **Production guard**: `ENVIRONMENT=production` rejects wildcard CORS; optional management auth protects write operations.
- **Prompt files**: `modes/score.md`, `modes/generate.md`
- **Testing**: pytest; `FakeLLMClient` for unit tests; testcontainers-postgres for integration
- **Lint/Type**: ruff (hard gate, target py311, `UP` enabled) + mypy (soft gate, `continue-on-error`)
- **Target**: local development first; can run behind a reverse proxy with explicit CORS and management auth.

## Roadmap

See `specs/roadmap.md` for full Phase 1 → 3 plan:
- **Phase 2**: LangChain, nginx ingress, Dockerfile, deployable to VPS
- **Phase 3**: Redis + Celery workers, pgBouncer, k8s ingress, high-concurrency

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Clean Code** | ✅ | Layered: `api/` → `services/` → `models/`; ruff + mypy |
| **II. TDD** | ✅ | Tests written before implementation; FakeLLMClient for unit tests |
| **III. Coverage** | ✅ | ≥85% on `backend/app/`; 100% on `services/hashing.py`, `parsing.py` |
| **IV. UX Envelope** | ✅ | All responses: `{data, error, meta}` |
| **V. Performance** | ✅ | Sync reads ≤200ms; cached JD eval ≤500ms; LLM ≤30s |
| **No Redis (Phase 1)** | ✅ waiver | Single user; jd_hash dedup in DB; Redis added in Phase 3 |
| **Write auth** | ✅ | Optional management auth for non-local deployments; no user accounts |
| **BackgroundTasks** | ✅ | Tailoring uses FastAPI BackgroundTask → Anthropic API directly; scoring is synchronous |
