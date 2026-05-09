# resumeHelper — Agent Quick Reference

## What this project does
Evaluates job descriptions (JD) against a baseline resume profile, scores them, and auto-tailors resumes for medium-match JDs.

## Three-tier scoring logic
| Score | Status | Action |
|-------|--------|--------|
| 85+ | `ready_to_submit` | Return immediately, no tailoring |
| 60–84 | `needs_tailoring` | BackgroundTask → Claude API → GeneratedResume |
| <60 | `skip` | Return immediately with skip_reason |

## Key files
| File | Purpose |
|------|---------|
| `backend/app/api/evaluate.py` | Main endpoints: POST /api/evaluate, GET /api/history, GET /api/submittable, GET /api/history/{id}, POST /api/callback |
| `backend/app/services/evaluator_v2.py` | Scores JD vs baseline, sets status/can_submit/skip_reason |
| `backend/app/workers/tailor.py` | Background tailoring via Claude API (no n8n) |
| `backend/app/services/llm/anthropic.py` | LLM client — has evaluate() and tailor() |
| `backend/app/services/llm/fake.py` | Fake LLM for tests |
| `backend/app/models/job_analysis.py` | JobAnalysis model — status, can_submit, skip_reason, thresholds |
| `backend/app/models/generated_resume.py` | GeneratedResume — resume_text, pdf_url, prompt_version |
| `backend/alembic/versions/` | 0001 initial, 0002 POC schema, 0003 three-tier fields |
| `backend/tests/integration/v2/` | All v2 tests (62 pass) |
| `todo.md` | Full spec and DB schema |

## Architecture decisions
- **No n8n** — tailoring runs as FastAPI BackgroundTask calling Claude API directly
- **PDF**: weasyprint not installed; pdf_url is null from background task, can be set via POST /api/callback
- **v1 endpoints** (`/api/resumes`, `/api/jobs`) were removed in migration 0002 and their orphaned modules deleted in #26 follow-up — only v2 (profile + evaluate + history) remains

## Running the app — host vs container
Two ways to run the FastAPI app. Pick by which LLM credential you have:

| Mode | Command | When to use |
|---|---|---|
| **Host (recommended for dev)** | `scripts/restart-app.sh` — uvicorn directly on host | You have `claude login` on your mac. Host's `claude` CLI is auto-picked up. No API key needed. |
| **Container** | `docker compose -f docker-compose.app.yml up -d` | You only have `ANTHROPIC_API_KEY`. Set `LLM_BACKEND=anthropic` in `.env`. |

The container can't reach the macOS Keychain where `claude` CLI stores its session, so `claude_cli` mode does NOT work inside the container. Either use host mode, or switch the container to API-key mode.

`docker compose up -d` (default `docker-compose.yml`) only brings up `postgres` — the DB is shared by both modes via `~/resumeHelper_data` bind mount.

## Running tests
```bash
cd /Users/laijacky/resumeHelper
./scripts/test.sh                       # bootstraps .venv with python3.11+, runs full suite
./scripts/test.sh -k some_test_name     # forwards args to pytest
./scripts/test.sh --recreate            # rebuild .venv
```
The default system `python` on this machine is Anaconda 3.9, which can't run the codebase post-#34 (`from datetime import UTC`). `scripts/test.sh` finds brew's `python3.11` / `python3.12` automatically.

## Stack
FastAPI + PostgreSQL (via SQLAlchemy/Alembic) + Claude API (anthropic SDK) + Docker Compose

## Python version
**3.11+ required.** Ruff target is `py311`, mypy `python_version = "3.11"`, Dockerfile uses `python:3.11-slim`, CI runs 3.11. SQLAlchemy 2.x evaluates `Mapped[...]` annotations at runtime, so PEP 604 unions and `datetime.UTC` would crash on 3.9/3.10 — there is no fallback path.

## Workflow — Plan / Execute / Test / Review (REQUIRED)
**Hard rule for any non-trivial change.** Follow the four phases in order, no skipping, no reordering. Surface each phase in user-facing output so the user can see the rule is being followed.

1. **Plan** — state what's going to change and in what order before touching code. If the user mentioned parallel work elsewhere, sync first (`git fetch`, compare with main).
2. **Execute** — make the code changes on a feature branch.
3. **Test** — run `./scripts/test.sh` (or targeted `-k`) and confirm green before claiming done.
4. **Review** — re-read the diff, check for scope creep / regressions, simplify.

Role definitions and detailed checklists live in `agent.md` (Planner / Executor / Testing / Reviewer).

## PR workflow (REQUIRED)
**NEVER push directly to `main` or `develop`.** Always work on a feature branch and open a PR.
Branch naming: `fix/<short-desc>`, `feat/<short-desc>`.

## Speckit sync (REQUIRED)
After every completed task, update the relevant speckit files in `specs/`:
- `spec.md` — add/update acceptance scenarios and FRs for any new or changed behaviour
- `plan.md` — keep architecture diagram and constitution table current
- `tasks.md` — tick off completed items; add new task rows for anything shipped outside the original list

## Discord notification (REQUIRED)
At the end of every completed task, send a summary to Discord using the MCP reply tool.
Full rules in `agent.md` — End-of-Process Discord Notification section.

```
chat_id: 1241933442434732128
format:  [role] title\n\n✅/⚠️/❌ outcome\n• bullets\n\nBranch: x  |  PR: #n
```
