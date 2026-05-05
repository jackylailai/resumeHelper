# Implementation Plan: Resume Scoring & Generation

**Branch**: `001-resume-upload-rating` | **Updated**: 2026-05-05
**Scope authority**: `scope-correction.md` — read before making any implementation decision.

## Summary

Single-user FastAPI service that:
1. Stores a one-time **baseline skills profile** (user's raw skills/experience)
2. Accepts a **job description (JD)** and scores the fit (0–100) via LLM
3. If score ≥ `RESUME_GEN_THRESHOLD`, triggers **n8n** to generate a tailored resume
4. Stores all analyses and generated resumes; serves them via a minimal browser UI

No resume versioning. No async job queue (Phase 1). No auth. Runs locally on Mac.

## Architecture (Phase 1 — POC)

```
Browser
  │
FastAPI (uvicorn, single process)
  ├── POST /api/profile        → upsert baseline_profile
  ├── POST /api/evaluate       → score JD; if threshold → POST n8n webhook
  ├── POST /api/callback       → n8n posts generated resume back here
  ├── GET  /api/history        → list past job_analyses
  ├── GET  /api/history/{id}   → one analysis + all generated_resumes
  └── GET  /api/health
  │
  ├── PostgreSQL  (3 tables: baseline_profile, job_analyses, generated_resumes)
  └── n8n         (resume generation workflow, prompt editable in UI)
```

## LLM Strategy

| Phase | LLM Backend | Requirement |
|-------|-------------|-------------|
| 1 (POC) | `claude` CLI via subprocess (`ClaudeCLIClient`) | Claude Code subscription |
| 2+ | Anthropic API / Groq (via `LLM_BACKEND` env var) | API key |

Switching is a one-line config change — `LLMClient` Protocol isolates this.

## Technical Context

- **Language**: Python 3.9+ (venv at `.venv/`)
- **Framework**: FastAPI + SQLAlchemy 2.x + Pydantic v2
- **DB**: PostgreSQL 16 (docker-compose)
- **LLM (scoring)**: local `claude` CLI → `ClaudeCLIClient`
- **LLM (generation)**: n8n workflow (port 5678, docker-compose)
- **Prompt files**: `modes/score.md`, `modes/generate.md`
- **Testing**: pytest; `FakeLLMClient` for unit tests; testcontainers-postgres for integration
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
| **No BackgroundTasks** | ✅ | Generation delegated to n8n; scoring is synchronous |
