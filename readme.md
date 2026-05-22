# Resume Fit Evaluator

A single-user job search assistant that scores job descriptions against saved
resume profiles, generates tailored resumes for good matches, and tracks the
application pipeline.

---

## How It Works

1. **Create resume profiles** - paste skills text or upload a PDF. You can keep
   multiple profiles and mark one as the default.
2. **Evaluate jobs** - paste a JD directly or score stored listings from the JD
   Database. The system scores each JD from 0-100:

| Score | Status | What happens |
|-------|--------|--------------|
| 85+ | `ready_to_submit` | Strong match; submit as-is |
| 60-84 | `needs_tailoring` | Good match; tailored resume generated in background |
| <60 | `skip` | Weak match; skip with a reason |

3. **Review outputs** - history and submittable views show scores, generated
   resumes, and on-demand PDF downloads.
4. **Track applications** - add scored JD Database listings to the Applications
   tracker and update status/follow-up dates.

For a screen-by-screen map of buttons, API calls, and screenshot callouts, see
[docs/ui-flow.md](docs/ui-flow.md).

---

## Pages

| Page | Purpose |
|------|---------|
| **Profile** | Save resume baselines and choose the default profile |
| **Evaluate** | Paste one JD and get a fit score, status, strengths, and gaps |
| **JD Database** | Search stored listings and batch-score selected jobs |
| **Submittable** | Review generated resumes and download PDFs |
| **Applications** | Track opportunities, statuses, and follow-up dates |
| **History** | Reopen previous evaluations and generated resume details |

---

## User Walkthrough

1. Open the UI and go to **Profile**.
2. Click **+ Add Profile**, paste skills text or preview a PDF, then click
   **Save Profile**.
3. Go to **Evaluate**, choose the profile, paste a JD, and click **Evaluate**.
4. If the score needs tailoring, open **Submittable** and use **View** or
   **PDF** after generation finishes.
5. For stored jobs, open **JD Database**, select listings, and click
   **Score selected**.
6. Open a scored listing, click **Track Application**, then manage it from
   **Applications** with status and follow-up dates.
7. Use **History** to review previous evaluations.

The complete step-by-step guide with annotated screenshots is in
[docs/ui-flow.md](docs/ui-flow.md).

---

## Current Scope

- FastAPI backend + PostgreSQL with Alembic migrations
- Multi-profile CRUD, PDF upload preview, default profile selection
- Three-tier JD scoring via configurable LLM backend (`claude_cli`,
  `anthropic`, or `fake`)
- Background resume tailoring and generated PDF download
- JD Database for scraped/stored listings, batch scoring, and paste-to-score
- Application tracker with search, status filters, sorting, and follow-up dates
- Health endpoints: `/api/health`, `/api/health/live`, `/api/health/ready`
- Optional write-operation guard via bearer token or basic auth
- Vanilla JS UI: Evaluate, JD Database, Applications, History, Submittable,
  Profile

## Stack

| Layer | Tech |
|-------|------|
| API | FastAPI |
| DB | PostgreSQL (SQLAlchemy + Alembic) |
| LLM | Claude CLI or Anthropic API |
| UI | Vanilla JS |
| Tests | pytest + testcontainers |

---

## Quickstart

> Python 3.11+ required.

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

## Running Tests

```bash
# Recommended wrapper
./scripts/test.sh

# Forward args
./scripts/test.sh -k applications_tracker

# Direct pytest, if Python 3.11+ deps are already installed
python -m pytest backend/tests/unit/ backend/tests/integration/v2/ -q
```

Docker must be running because integration tests use testcontainers Postgres.

---

## Production Notes

For non-local deployments, set explicit CORS origins and enable write auth:

```env
ENVIRONMENT=production
CORS_ALLOWED_ORIGINS=https://resumehelper.example.com
MANAGEMENT_AUTH_ENABLED=true
MANAGEMENT_AUTH_TOKEN=<strong-token>
```

`/api/health/ready` returns HTTP 503 when required dependencies are not ready.
