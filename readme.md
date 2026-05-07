# Resume Fit Evaluator

A single-user tool that scores job descriptions against your baseline resume
profile and automatically tailors your resume for strong-but-not-perfect matches.

---

## How it works

1. **Save your baseline profile** — paste your skills/experience text once.
2. **Evaluate a JD** — paste any job description. The system scores it 0–100
   against your baseline and classifies it into one of three tiers:

| Score | Status | What happens |
|-------|--------|-------------|
| 85+ | `ready_to_submit` | Strong match — submit as-is |
| 60–84 | `needs_tailoring` | Good match — resume tailored in background |
| <60 | `skip` | Weak match — skip with a reason |

3. **View history** — all evaluated JDs with scores and statuses.
4. **Check submittable** — jobs with a generated resume ready to submit.

---

## Phase 1 (current)

- FastAPI backend + PostgreSQL
- Three-tier scoring via Claude API
- Background tailoring (FastAPI BackgroundTasks)
- Single-page UI (Evaluate / History / Profile tabs)
- JD deduplication by content hash
- Bulk JD evaluation endpoint

## Stack

| Layer | Tech |
|-------|------|
| API | FastAPI |
| DB | PostgreSQL (SQLAlchemy + Alembic) |
| LLM | Claude (local `claude` CLI or Anthropic API) |
| UI | Vanilla JS single-page app |
| Tests | pytest + testcontainers |

---

## Quickstart

> **Python 3.11+ required.** The codebase uses `datetime.UTC`, PEP 604
> unions inside SQLAlchemy `Mapped[...]` annotations (which are evaluated
> at runtime), and other typing-modernise constructs. There is no 3.9/3.10
> fallback — `pyenv install 3.11 && pyenv local 3.11` if you're on Anaconda
> 3.9 or similar.

See [specs/001-resume-upload-rating/quickstart.md](specs/001-resume-upload-rating/quickstart.md).

```bash
# Start DB
docker compose up -d postgres

# Run migrations
alembic -c backend/alembic.ini upgrade head

# Start API
uvicorn backend.app.main:app --reload --port 8000

# Open UI
open http://localhost:8000
```

---

## Running tests

```bash
python -m pytest backend/tests/unit/ backend/tests/integration/v2/ -q
```

---

## Roadmap (future phases)

- Job crawler / n8n ingestion pipeline
- PDF resume generation (weasyprint)
- Multi-user support
- Kubernetes deployment
- Discord agent interface
