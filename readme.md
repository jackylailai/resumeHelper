# Resume Helper

Resume Helper is a single-user AI workflow tool for job search execution. It
helps you collect job descriptions, score them against baseline profiles,
generate reviewable tailored resumes, and track application decisions.

The product is intentionally workflow-first rather than chatbot-first. LLMs are
used inside bounded steps with explicit inputs, expected outputs, and
application-owned state transitions.

## Current Workflow

1. Save one or more baseline profiles.
2. Paste a JD, bulk-evaluate JDs, or scrape listings into the JD database.
3. Score each JD against a selected baseline profile.
4. Route the result by score:

| Score | Status | Behavior |
|-------|--------|----------|
| 85-100 | `ready_to_submit` | Strong match; ready for review and application tracking. |
| 60-84 | `needs_tailoring` | Generate a tailored resume draft/PDF for review. |
| 0-59 | `skip` | Keep the analysis, but do not recommend applying. |

5. Review suggested opportunities and source URLs.
6. Add selected jobs to the application tracker.
7. Review generated resumes/PDFs before submitting.

## Implemented Product Areas

- Baseline profile CRUD and PDF upload.
- Single JD evaluation.
- Bulk JD evaluation.
- Three-tier scoring and status routing.
- Generated resume drafts and beautified PDF/HTML output.
- JD database with source listings.
- Scrapers for 104, Yourator, and LinkedIn guest listings.
- Scrape run history and controllable scrape scheduling UI.
- Cron wrapper for scheduled scrape + evaluate jobs.
- Job opportunities / recommended application surface.
- Application tracker with status and follow-up fields.
- Production-style JSON error envelopes with request IDs.

## Main Pages

| Page | Purpose |
|------|---------|
| `/` | Evaluate JDs, review history, profiles, and submittable results. |
| `/jobs.html` | Browse stored JDs, filter listings, inspect source links, and score selected rows. |
| `/scrapes.html` | Run and monitor source ingestion for 104, Yourator, and LinkedIn. |
| `/applications.html` | Track jobs you intend to act on after reviewing Opportunities or Submittable. |

## LLM Backends

The app supports a configurable LLM backend:

- `fake` for deterministic tests and local development.
- `claude_cli` for local Claude CLI usage.
- `anthropic` for Anthropic API usage.

The current LLM flow is:

```text
baseline profile + JD
  -> evaluate LLM call
  -> application-owned score routing
  -> optional tailoring LLM call
  -> optional beautify/PDF generation
  -> human review
```

The LLM can suggest and generate content, but the application owns state
transitions. Human review is required before any real submission.

## AI Engineering Direction

High-priority hardening work is tracked in:

- [#113: LLM eval harness and stricter output constraints](https://github.com/jackylailai/resumeHelper/issues/113)
- [#114: AI engineering production maturity checklist](https://github.com/jackylailai/resumeHelper/issues/114)
- [#115: README and current product specs refresh](https://github.com/jackylailai/resumeHelper/issues/115)

Target practices:

- Explicit input and output specs for every LLM call.
- Schema validation for LLM outputs.
- Deterministic state machine in application code.
- Prompt/model versioning and audit trail.
- Eval harness with golden fixtures and regression reports.
- Factuality checks for tailored resumes.
- Durable background jobs for long-running work.
- Cost, latency, quota, and privacy controls.

The first eval harness implementation covers deterministic evaluate-output
contracts and score routing. See [docs/eval-harness.md](docs/eval-harness.md).

See [specs/current-product-spec.md](specs/current-product-spec.md) for the
current product spec.

## Stack

| Layer | Tech |
|-------|------|
| API | FastAPI |
| DB | PostgreSQL, SQLAlchemy, Alembic |
| LLM | Claude CLI, Anthropic API, deterministic fake backend |
| UI | Vanilla HTML/CSS/JS |
| PDF | WeasyPrint |
| Tests | pytest, testcontainers, Playwright flow tests |

## Quickstart

Python 3.11+ is required.

```bash
# Start Postgres
docker compose up -d postgres

# Install backend dependencies
python -m pip install -r backend/requirements.txt

# Run migrations
alembic -c backend/alembic.ini upgrade head

# Start API and static UI
uvicorn backend.app.main:app --reload --port 8000
```

Open:

- http://localhost:8000/
- http://localhost:8000/jobs.html
- http://localhost:8000/scrapes.html
- http://localhost:8000/applications.html

## Scrape Scheduling

The Scrapes page includes controls to:

- choose a keyword and source
- start a scrape schedule
- inspect active runs
- stop current runs
- stop and immediately run a new keyword
- optionally evaluate pending listings after scraping

For cron or launchd usage, see [docs/scheduling.md](docs/scheduling.md).

## Useful CLI Commands

```bash
# Scrape default safe sources: 104 + Yourator
python -m backend.app.cli scrape --source all --keyword "backend engineer" --limit 25

# Include LinkedIn explicitly
python -m backend.app.cli scrape --source all_with_linkedin --keyword "backend engineer" --limit 10

# Scrape and then evaluate pending listings
python -m backend.app.cli scrape --source all --keyword "java backend" --evaluate

# Evaluate pending stored listings
python -m backend.app.cli evaluate-listings --limit 100

# Run deterministic LLM evaluate contract/routing fixtures
python -m backend.app.cli eval-harness --backend fake
```

## Running Tests

```bash
# Recommended wrapper
./scripts/test.sh

# Forward pytest args
./scripts/test.sh -k scrape

# Direct pytest when dependencies are already installed
python -m pytest backend/tests/unit/ backend/tests/integration/v2/ -q
```

Docker must be running for integration tests that use testcontainers.

## Documentation

- [Current product spec](specs/current-product-spec.md)
- [Roadmap](specs/roadmap.md)
- [AI workflow engineering](docs/ai-workflow/README.md)
- [Historical OpenAPI contract](specs/001-resume-upload-rating/contracts/openapi.yaml)
- [Eval harness](docs/eval-harness.md)
- [Scrape scheduling](docs/scheduling.md)
- [Scrapers (per-platform mechanisms)](docs/scrapers.md)
- [Script inventory](scripts/README.md)
- Historical Phase 1 spec: [specs/001-resume-upload-rating/spec.md](specs/001-resume-upload-rating/spec.md)
