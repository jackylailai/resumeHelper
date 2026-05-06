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
| `backend/tests/integration/v2/` | All v2 tests (30 pass) |
| `todo.md` | Full spec and DB schema |

## Architecture decisions
- **No n8n** — tailoring runs as FastAPI BackgroundTask calling Claude API directly
- **PDF**: weasyprint not installed; pdf_url is null from background task, can be set via POST /api/callback
- **v1 endpoints** (`/api/resumes`, `/api/jobs`) were removed in migration 0002 — their tests (22) are expected failures

## Running tests
```bash
cd /Users/laijacky/resumeHelper
python -m pytest backend/tests/integration/v2/ -x -q
```

## Stack
FastAPI + PostgreSQL (via SQLAlchemy/Alembic) + Claude API (anthropic SDK) + Docker Compose
