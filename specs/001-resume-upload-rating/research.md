# Phase 0 Research: Resume Upload & Rating

**Date**: 2026-05-05
**Owner**: jackylailai

This document records the alternatives considered for each technical decision in
the plan, the choice made, and the rationale. Decisions are scoped to v1
single-user mode.

## 1. LLM Provider

| Option | Pros | Cons |
|---|---|---|
| **Anthropic Claude (claude-sonnet-4-6)** ✅ | Strong long-context reasoning, structured output via tool-use, user already has key | Network dependency, cost per token |
| OpenAI GPT-4o | Comparable quality, structured outputs | Different SDK; user has no existing infra |
| Ollama / local Llama 3 | No network cost, fully offline | 8B-class models score job fit poorly; hardware burden on user laptop |

**Decision**: Anthropic Claude `claude-sonnet-4-6`. Wrap behind a `LLMClient`
protocol so swapping is a single class change. Provide a `FakeLLMClient` that
returns deterministic fixtures keyed by `(content_hash, jd_hash)` for tests.

**Prompt versioning**: Each evaluation persists `prompt_version` (e.g.
`"resume-fit-v1"`) so score drift caused by prompt edits is distinguishable
from resume changes (constitution Principle V, Assumption in spec).

## 2. PDF / DOCX Parsing

| Option | Pros | Cons |
|---|---|---|
| **`pypdf` + `python-docx`** ✅ | Pure-Python, no system deps, MIT/BSD licenses | Won't OCR scanned PDFs (acceptable per FR-010 — reject) |
| `pdfplumber` | Better table extraction | Heavier; not needed for resume body text |
| `unstructured` | Handles many formats | Pulls dozens of optional deps; overkill for v1 |
| `tika` | Robust | Requires Java runtime — rejected |

**Decision**: `pypdf` for PDF, `python-docx` for DOCX. Detect zero extracted
text and reject with HTTP 422 per FR-010. Accept only extensions `.pdf`/`.docx`
**and** verify magic bytes (`%PDF-` / ZIP `PK\x03\x04`) before parsing.

## 3. Async Evaluation Strategy

| Option | Pros | Cons |
|---|---|---|
| **FastAPI `BackgroundTasks`** ✅ | In-process, zero infra, runs in same event loop | Lost on process restart; no retry |
| Celery + Redis | Production-grade retries, monitoring | Brokers + workers + Redis — three new processes for one user |
| RQ + Redis | Simpler than Celery | Still needs Redis |
| `asyncio.create_task` directly | Trivial | Same loss-on-restart, less ergonomic than BackgroundTasks |

**Decision**: `BackgroundTasks`. Persist `EvaluationJob` row immediately so
state survives crashes — on startup, mark any `running` jobs as `failed` with
reason `worker_crashed`; user can retrigger. Acceptable because a single user
will simply re-upload.

## 4. File Storage

| Option | Pros | Cons |
|---|---|---|
| **Local filesystem `backend/storage/<sha256>.{pdf,docx}`** ✅ | Zero-config, fast, easy to inspect | Not portable across hosts |
| Postgres `bytea` | Single backup surface | Bloats DB, slow large-file reads |
| S3 / MinIO | Production-shaped | Requires account or extra container |

**Decision**: Local filesystem keyed by `sha256(file_bytes)`. DB stores the
relative path + hash. Path is never user-controlled (no path traversal risk).

## 5. Caching Strategy (LLM Reuse)

Constitution Principle V mandates caching keyed by
`(job_hash, cv_hash, prompt_version)`. With no Redis (waiver), cache lives in
the `evaluation_cache` Postgres table — same key shape, single SELECT on the
hot path. SC-006 ("under 1 second cached return") easily met for a local DB.

## 6. Frontend Hosting

| Option | Pros | Cons |
|---|---|---|
| **FastAPI `StaticFiles` mount** ✅ | One process, no CORS, no Node | Mixes API + static (mild Principle I drift) |
| Separate Vite + TS frontend | Constitution-aligned long-term | User unfamiliar with frontend; v1 UI is trivial |
| Cloudflare Pages / Netlify | Zero-ops hosting | Requires public deploy + CORS config |

**Decision**: FastAPI mounts `static/` at `/`. Existing `index.html` is moved
into `static/`; new `upload.html` is added. JS is vanilla; no build step.

## 7. Database & Migrations

- **PostgreSQL 16** in `docker-compose.yml`, mounted volume for persistence.
- **SQLAlchemy 2.x** with declarative models, `AsyncSession` not required for
  v1 (BackgroundTasks already off the request path); use sync `Session` for
  simplicity and to keep tests straightforward.
- **Alembic** for migrations. First migration creates all four tables.
- **Test DB**: `pytest-postgresql` or `testcontainers-postgres`. Decision:
  `testcontainers-postgres` — closer to prod, single dependency.

## 8. Configuration & Secrets

- `pydantic-settings` reads from `.env`. Required keys:
  - `DATABASE_URL`
  - `ANTHROPIC_API_KEY`
  - `STORAGE_DIR` (default `./backend/storage`)
  - `LLM_PROMPT_VERSION` (default `resume-fit-v1`)
  - `MAX_UPLOAD_BYTES` (default `10485760`)
- `.env.example` is updated to list all keys; real `.env` is git-ignored.

## 9. Observability (lightweight v1)

Constitution Principle requires structured logs with `request_id`, `job_id`,
`prompt_version`, `latency_ms`, `token_count`. v1 emits these via Python's
`logging` with a JSON formatter; Prometheus metrics endpoint deferred to v2
and tracked as a follow-up in plan.md Complexity Tracking → "deferred items".

## 10. Open Questions (resolved during clarification)

- **Multi-user?** No — FR-012 single-user mode confirmed.
- **Job description provisioning?** User pastes JD into the upload form; JD is
  hashed and stored alongside the evaluation. Library of saved JDs is **out of
  scope for v1**.
- **Scoring rubric?** Free-form 0–100 from the LLM; the prompt asks for a
  structured JSON `{score, strengths[], gaps[], explanation}`. The score is
  validated in range; out-of-range responses fail the evaluation job with
  `reason=llm_invalid_score`.
