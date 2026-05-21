# Resume Helper

Resume Helper is a single-user AI workflow product for job search execution. It
turns raw job descriptions into scored opportunities, reviewable resume drafts,
and trackable application decisions.

The project is intentionally workflow-first rather than chatbot-first. LLMs are
bounded providers inside explicit steps; the application owns persistence,
status transitions, validation, retry/cancel behavior, and the human review
gate before submission.

## Showoff Summary

```text
profile library + JD database
  -> sync or async JD evaluation
  -> deterministic score routing
  -> durable tailoring job when useful
  -> generated Markdown / HTML / PDF for review
  -> opportunities, submittable list, and application tracker
```

What is worth showing:

| Moment | What the user sees | What the system proves |
|--------|--------------------|------------------------|
| Add profile | Upload or paste a baseline resume profile. | Profiles are persisted and selected explicitly. |
| Score JD | A 0-100 score, explanation, strengths, and gaps. | LLM output is schema-validated before it affects state. |
| Choose async | Evaluation can run as a durable job and be polled. | Long-running AI work has queued/running/succeeded/failed/cancelled states. |
| Tailor resume | Mid-score jobs queue a resume generation job. | Resume generation is observable, retryable, and not lost on restart. |
| Review draft | The user opens Markdown, beautified HTML, and PDF output. | The product keeps a human approval boundary. |
| Track application | Promising listings move into the application tracker. | The AI workflow ends in explicit user action, not auto-submit. |

## Product Workflow

1. Save one or more baseline profiles.
2. Paste a JD, bulk-evaluate JDs, or scrape listings into the JD database.
3. Score each JD against a selected baseline profile. Single JD evaluation is
   synchronous by default, with an optional durable async mode.
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
- Single JD evaluation, synchronous by default with optional async job mode.
- Bulk JD evaluation.
- Three-tier scoring and status routing.
- Durable AI jobs for async evaluate and background tailoring.
- Generated resume drafts and beautified PDF/HTML output.
- JD database with source listings.
- Scrapers for 104, Yourator, and LinkedIn guest listings.
- Scrape run history and controllable scrape scheduling UI.
- Cron wrapper for scheduled scrape + evaluate jobs.
- Job opportunities / recommended application surface.
- Application tracker with status and follow-up fields.
- Metadata-first LLM audit logs, prompt versions, and deterministic harnesses.
- Batch cost/quota/privacy guardrails.
- Production-style JSON error envelopes with request IDs.

## Main Pages

| Page | Purpose |
|------|---------|
| `/` | Evaluate JDs, optionally queue async scoring, review history, profiles, and submittable results. |
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
  -> evaluate LLM call or durable evaluate job
  -> application-owned score routing
  -> optional durable tailoring job
  -> optional beautify/PDF generation
  -> human review
```

The LLM can suggest and generate content, but the application owns state
transitions. Human review is required before any real submission.

## Spend And Privacy Guardrails

Batch workflows run a quota preflight before launching provider calls. Configure
the limits in `.env`:

- `MAX_BULK_EVALUATE_ITEMS`, `MAX_EVALUATE_LISTING_ITEMS`,
  `MAX_EVALUATE_PENDING_ITEMS`, and `MAX_SCRAPE_AFTER_EVALUATE_ITEMS` cap how
  many JDs can be evaluated in one workflow.
- `MAX_TAILORING_JOBS_PER_BATCH` caps how many generated resume jobs can be
  queued from one batch.
- `MAX_BATCH_ESTIMATED_TOKENS` and `MAX_BATCH_ESTIMATED_COST_USD` block batches
  whose preflight estimate is too large. `0` disables that specific budget.
- `LLM_INPUT_COST_PER_MILLION_TOKENS` and
  `LLM_OUTPUT_COST_PER_MILLION_TOKENS` drive approximate cost estimates. Provider
  token metadata is stored in `llm_audit_logs` when available, with estimated
  cost in micro-USD.
- `AI_PROVIDER_CALLS_ENABLED=false` blocks real provider calls for batch
  workflows when `LLM_BACKEND` is not `fake`.

Privacy posture: evaluation sends the selected baseline profile full text and
the full JD text to the configured LLM provider. Tailoring sends the baseline
profile, structured profile data when present, the full JD text, score, and gaps.
Beautification sends the generated resume markdown. The audit log stores hashes,
workflow metadata, latency, token counts, and estimated cost; it does not store
raw resume/JD/provider output text. Application tables still store baseline
profiles, JDs, analyses, and generated resumes because those are the product
state users review.

## AI Engineering Direction

High-priority hardening work is tracked in:

- [#113: LLM eval harness and stricter output constraints](https://github.com/jackylailai/resumeHelper/issues/113)
- [#114: AI engineering production maturity checklist](https://github.com/jackylailai/resumeHelper/issues/114)
- [#115: README and current product specs refresh](https://github.com/jackylailai/resumeHelper/issues/115)

The current readiness map is maintained in
[docs/ai-engineering-readiness.md](docs/ai-engineering-readiness.md).

Target practices:

- Explicit input and output specs for every LLM call.
- Schema validation for LLM outputs.
- Deterministic state machine in application code.
- Prompt/model versioning and audit trail.
- Eval harness with golden fixtures and regression reports.
- Factuality checks for tailored resumes.
- Durable background jobs for long-running work.
- Cost, latency, quota, and privacy controls.

The deterministic harnesses cover evaluate, tailor, structured extraction, and
beautify contracts in CI. See [docs/eval-harness.md](docs/eval-harness.md).

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

## Demo Script

Use this path when showing the project end to end:

1. Open `/`, confirm System Status is ready, and select a profile.
2. Paste a JD and run the default synchronous evaluation.
3. Re-run with **Async job** checked to show durable job polling.
4. Use a mid-score JD to queue tailoring, then open the generated resume modal.
5. Beautify the resume and download the PDF.
6. Open `/jobs.html`, inspect a stored listing, and add it to Applications.
7. Open `/applications.html` and move the job through status/follow-up fields.
8. Point to CI harness reports and `llm_audit_logs` as the engineering proof
   behind the workflow.

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

- [Quickstart (end-user, 5 minutes)](docs/quickstart.md)
- [Current product spec](specs/current-product-spec.md)
- [Roadmap](specs/roadmap.md)
- [AI workflow engineering](docs/ai-workflow/README.md)
- [AI workflow showcase](docs/ai-workflow/SHOWCASE.md)
- [AI engineering readiness](docs/ai-engineering-readiness.md)
- [Prompt registry](docs/prompts.md)
- [Historical OpenAPI contract](specs/001-resume-upload-rating/contracts/openapi.yaml)
- [Eval harness](docs/eval-harness.md)
- [Scrape scheduling](docs/scheduling.md)
- [Scrapers (per-platform mechanisms)](docs/scrapers.md)
- [Script inventory](scripts/README.md)
- Historical Phase 1 spec: [specs/001-resume-upload-rating/spec.md](specs/001-resume-upload-rating/spec.md)
