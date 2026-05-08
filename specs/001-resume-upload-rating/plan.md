# Implementation Plan: Resume Scoring & Generation

**Branch**: `001-resume-upload-rating` | **Updated**: 2026-05-06 (rev 2)
**Scope authority**: `scope-correction.md` — read before making any implementation decision.

## Summary

Single-user FastAPI service that:
1. Maintains a **library of baseline profiles** (name + skills text); each created via raw text or PDF upload; full CRUD at `/api/profiles`
2. Accepts a **job description (JD)** and scores the fit (0–100) via LLM against a selected or latest profile
3. If score ≥ `RESUME_GEN_THRESHOLD`, triggers a **FastAPI BackgroundTask** to generate a tailored resume via Anthropic API directly (n8n removed)
4. Cache scoped to `(jd_hash, profile_id)` — same JD against different profiles = independent evaluations
5. Stores all analyses and generated resumes; serves them via a minimal browser UI

No resume versioning. No async job queue (Phase 1). No auth. Runs locally on Mac.

## Architecture (Phase 1 — POC)

```
Browser
  │
FastAPI (uvicorn, single process)
  ├── GET    /api/profiles          → list all baseline profiles
  ├── POST   /api/profiles          → create profile (text)
  ├── POST   /api/profiles/upload   → create profile (PDF, pypdf extraction)
  ├── GET    /api/profiles/{id}     → get one profile
  ├── PUT    /api/profiles/{id}     → update profile
  ├── DELETE /api/profiles/{id}     → delete profile
  ├── POST   /api/profile           → legacy: create profile (backward compat)
  ├── GET    /api/profile           → legacy: return latest profile
  ├── POST   /api/evaluate          → score JD against selected/latest profile; if threshold → BackgroundTask
  ├── POST   /api/callback          → external resume delivery (e.g. CI pipeline)
  ├── GET    /api/history           → list past job_analyses
  ├── GET    /api/history/{id}      → one analysis + all generated_resumes
  └── GET    /api/health
  │
  ├── PostgreSQL  (3 tables: baseline_profile, job_analyses, generated_resumes)
  └── Anthropic API (tailoring via BackgroundTask — no n8n)
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
- **Job-board crawlers (Phase 2.5)**: per-source scrapers under `services/scrapers/` implement `BaseScraper`; outputs land in `job_listings`; a separate batch evaluator feeds `evaluator_v2` to keep crawl and scoring decoupled. No headless browser — only public JSON / guest HTML endpoints; failures in one source must not block the others.
- **Prompt files**: `modes/score.md`, `modes/generate.md`
- **Testing**: pytest; `FakeLLMClient` for unit tests; testcontainers-postgres for integration
- **Lint/Type**: ruff (hard gate, target py311, `UP` enabled) + mypy (soft gate, `continue-on-error`)
- **Target**: local Mac only (Phase 1)

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
| **No auth** | ✅ waiver | Single user, local only |
| **BackgroundTasks** | ✅ | Tailoring uses FastAPI BackgroundTask → Anthropic API directly; scoring is synchronous |
