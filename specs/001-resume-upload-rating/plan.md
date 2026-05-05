# Implementation Plan: Resume Upload & Rating

**Branch**: `001-resume-upload-rating` | **Date**: 2026-05-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-resume-upload-rating/spec.md`

## Summary

Build a single-user FastAPI service that accepts PDF/DOCX resume uploads, parses
the text, runs a job-fit evaluation against a user-provided job description via
the Anthropic Claude API, and returns a 0–100 score plus an explanation. Each
upload is stored as an immutable `ResumeVersion`; ratings are cached by content
hash; evaluations longer than 5 s switch to a `job_id` polling pattern. The
existing static `index.html` docs page is preserved and FastAPI also serves a
minimal upload UI from the same origin (no separate frontend project).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, Uvicorn, SQLAlchemy 2.x, Pydantic v2, `pypdf`,
`python-docx`, `anthropic` SDK, `python-dotenv`, `pytest`, `httpx` (test client)
**Storage**: PostgreSQL 16 (system of record); local filesystem `backend/storage/`
for original binary files; Redis intentionally **not** used in v1 (single-user
waiver — see Complexity Tracking)
**Testing**: pytest + pytest-asyncio; contract tests with `schemathesis` against
the OpenAPI spec; LLM stubbed with deterministic fixtures
**Target Platform**: Local developer machine (macOS / Linux); single-user mode
**Project Type**: Web service with co-located static frontend
**Performance Goals**: per constitution Principle V — sync reads p95 ≤ 200 ms;
cached evaluation ≤ 500 ms; async LLM evaluation end-to-end ≤ 30 s
**Constraints**: file ≤ 10 MB; 50-version per-user cap; explanations English-only;
single FastAPI replica; no auth (FR-012)
**Scale/Scope**: 1 user, ~50 resume versions, ~3 endpoints active simultaneously

## Constitution Check

*Re-evaluated after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| **I. Clean Code & Code Quality** | ✅ Pass | Layered structure (`api/` → `services/` → `models/`); side-effects (LLM, DB, file I/O) isolated in `services/`; ruff + mypy in CI |
| **II. Test-Driven Development** | ✅ Pass | Every user story has contract + integration tests scheduled before implementation in `tasks.md`; LLM faked via `services/llm/fake.py` |
| **III. Comprehensive Testing Standards** | ⚠️ Conditional | Unit + integration + contract layers covered. **85% line coverage** target on `backend/app/`; 100% on scoring + parsing paths. Pyramidal coverage gates added to `tasks.md` polish phase |
| **IV. UX Consistency** | ⚠️ Waiver | Idempotency-Key support **deferred** — single-user, no concurrent retries expected. Documented below. Envelope `{data, error, meta}` enforced. State vocabulary `pending/running/succeeded/failed` matches constitution |
| **V. Performance & Scalability** | ⚠️ Waiver | LLM-cache via PostgreSQL `(content_hash, jd_hash, prompt_version)` lookup instead of Redis. Throughput floor of 50 concurrent eval/replica **not** required (single user). Latency budgets for sync endpoints still enforced |

**Gates**: Plan **passes** with two recorded waivers (Principles IV/V) tied to
the FR-012 single-user scope. Waivers MUST be revisited before any multi-user
deployment.

## Project Structure

### Documentation (this feature)

```text
specs/001-resume-upload-rating/
├── spec.md              # Feature spec (already authored)
├── plan.md              # This file
├── research.md          # Phase 0 — tech decisions
├── data-model.md        # Phase 1 — entities
├── quickstart.md        # Phase 1 — dev bootstrap
├── contracts/
│   └── openapi.yaml     # Phase 1 — REST contract
├── tasks.md             # Phase 2 — task breakdown (TDD ordered)
└── checklists/          # Optional review checklists
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py                  # FastAPI app, mounts /static, includes routers
│   ├── config.py                # Settings via pydantic-settings + .env
│   ├── db.py                    # SQLAlchemy engine + session
│   ├── api/
│   │   ├── health.py            # GET /health
│   │   ├── resumes.py           # POST /resumes, GET /resumes, GET /resumes/{id}
│   │   ├── evaluations.py       # GET /evaluations/{id}, GET /jobs/{job_id}
│   │   └── envelope.py          # {data, error, meta} response wrapper
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── resume.py
│   │   ├── resume_version.py
│   │   ├── resume_evaluation.py
│   │   └── evaluation_job.py
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── resume.py
│   │   └── evaluation.py
│   ├── services/                # Side-effect boundary
│   │   ├── parsing.py           # pypdf + python-docx → plain text
│   │   ├── hashing.py           # SHA-256 of canonicalized text
│   │   ├── storage.py           # local filesystem put/get
│   │   ├── evaluator.py         # orchestrates job → LLM → persist
│   │   └── llm/
│   │       ├── __init__.py      # protocol + factory
│   │       ├── anthropic.py     # production client
│   │       └── fake.py          # deterministic test double
│   └── workers/
│       └── tasks.py             # FastAPI BackgroundTasks entrypoints
├── tests/
│   ├── conftest.py              # fixtures: db, client, fake LLM, sample files
│   ├── contract/                # schemathesis-driven OpenAPI conformance
│   ├── integration/             # real DB (testcontainers), faked LLM
│   └── unit/                    # parsing, hashing, scoring rule helpers
├── alembic/                     # migrations (added in foundational phase)
└── requirements.txt

static/
├── index.html                   # existing docs viewer (moved from repo root)
├── upload.html                  # new: minimal upload UI
├── styles.css                   # existing
└── app.js                       # vanilla JS for upload + history view

docker-compose.yml               # postgres + (optional) backend service
.env.example                     # DATABASE_URL, ANTHROPIC_API_KEY, STORAGE_DIR
```

**Structure Decision**: Single-project layout with co-located static frontend.
FastAPI serves the API under `/api/...` and the static UI from `/` via
`StaticFiles`. The current `index.html` (docs viewer) is preserved at
`static/index.html`; the new upload UI lives at `static/upload.html`. No
separate `frontend/` package, no Node toolchain in v1. When UI complexity grows
(e.g., User Story 3 comparison view becomes unwieldy) the plan is to introduce
Vite + TypeScript in a follow-up feature.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **No Redis (caching, idempotency, rate limit)** — Constitution Principles IV/V | Single-user FR-012 means no concurrent writers, no replay risk, no rate-limit attack surface. Adding Redis triples ops surface for zero current value. | A 3-row Postgres lookup `evaluation_cache(content_hash, jd_hash, prompt_version)` satisfies SC-006 (<1 s cached return) without an extra service. |
| **No typed frontend framework** — Constitution Engineering Constraints | User is unfamiliar with frontend tooling; v1 UI is upload form + score display + history list — under 200 LoC of vanilla JS. | React/Vue + Vite + TS doubles the learning surface and adds CORS / build pipeline that produce no v1 user-visible benefit. Upgrade path documented in Structure Decision. |
| **FastAPI BackgroundTasks instead of Celery/RQ workers** — Constitution Principle V throughput floor | 50 concurrent evals/replica is not a v1 requirement (one user, one tab). BackgroundTasks runs in-process and avoids broker setup. | Celery requires Redis + worker process + result backend; RQ requires Redis. Neither is justifiable until concurrency is real. |

All three waivers are scoped to v1 single-user mode and MUST be re-opened
before any multi-user or public deployment.
