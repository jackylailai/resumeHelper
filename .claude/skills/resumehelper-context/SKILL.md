---
name: "resumehelper-context"
description: "Quick context index for the resumeHelper project — entry points, file map, response envelope, common commands, project rules, open work. Load early in any session that touches this codebase to avoid re-reading the same files. Updated 2026-05-07."
user-invocable: true
disable-model-invocation: false
---

# resumeHelper — Quick Context Index

> **Read CLAUDE.md too.** This skill is supplementary, not a replacement — it focuses on *where to look* and *current state*, while CLAUDE.md covers domain logic.

## What it does
Evaluates JDs against a baseline resume profile and scores three ways:

| Score | Status | Action |
|---|---|---|
| 85+ | `ready_to_submit` | return immediately, no tailoring |
| 60–84 | `needs_tailoring` | BackgroundTask → Claude API → `GeneratedResume` |
| <60 | `skip` | return immediately with `skip_reason` |

## Entry-point map (where to look first)

| To... | Look at |
|---|---|
| Start the stack (host FastAPI + docker pg/n8n) | `scripts/start.sh` |
| Start everything in docker (force-rebuild image) | `scripts/restart-docker.sh --full` |
| Restart only FastAPI | `scripts/restart-app.sh` |
| Run unit + integration tests | `scripts/test.sh` (auto-bootstraps py3.11+ venv) |
| Scrape jobs into DB | `scripts/scrape_jobs.py --keyword <kw> --site 104,yourator` |
| Smoke-test the API | `scripts/e2e-check.sh` |
| FastAPI app factory | `backend/app/main.py::create_app` |
| API routes | `backend/app/api/{evaluate,profile,health}.py` |
| Three-tier scoring logic | `backend/app/services/evaluator_v2.py::evaluate_jd` |
| LLM client (Anthropic SDK) | `backend/app/services/llm/anthropic.py` |
| LLM client (Claude CLI, default in dev) | `backend/app/services/llm/claude_cli.py` |
| Fake LLM (used in tests) | `backend/app/services/llm/fake.py` |
| Background tailoring worker | `backend/app/workers/tailor.py` |
| DB models | `backend/app/models/{baseline_profile,job_analysis,generated_resume,job_listing}.py` |
| Alembic migrations | `backend/alembic/versions/` (latest: 0003 three-tier) |
| Scrapers | `backend/app/services/scrapers/scraper_{104,yourator}.py` |
| Scraper persistence helper | `backend/app/services/scrapers/persistence.py` |
| Test fixtures (TestClient, fake LLM, testcontainers pg) | `backend/tests/conftest.py` |

## Response envelope

Every JSON response (success or error) goes through `backend/app/api/envelope.py`:

```json
{ "data": ..., "error": null | {"code","message","details"}, "meta": {...} }
```

As of #53 a global `@app.exception_handler(Exception)` in `main.py` ensures that **even uncaught 500s are JSON** (no more plain `Internal Server Error` from Starlette).

## DB sessions

- App (route handlers): `Depends(get_db)` from `backend.app.db`
- Scripts / workers: `from backend.app.db import SessionLocal` then `with SessionLocal() as session:`
- Tests: `db_session` and `client` fixtures spin a testcontainers postgres per session

## Stack at a glance

FastAPI + PostgreSQL (SQLAlchemy 2.x, Alembic) + Anthropic Claude (SDK or CLI) + Docker Compose. **Python 3.11+ required** (PEP 604 unions inside `Mapped[...]`, `datetime.UTC`).

## Common commands

```bash
# Tests
./scripts/test.sh                          # full SIT (unit + v2 integration)
./scripts/test.sh -k <pattern>             # subset
./scripts/test.sh --recreate               # rebuild .venv

# Local stack
./scripts/start.sh                         # postgres + n8n (docker) + FastAPI (host)
./scripts/restart-app.sh                   # FastAPI only (kills lingering uvicorn, clears __pycache__)
./scripts/restart-docker.sh --full         # everything via docker, --no-cache rebuild

# Seed data
./.venv/bin/python scripts/scrape_jobs.py --keyword "後端工程師" --limit 25 --site 104,yourator

# Smoke
./scripts/e2e-check.sh                     # exercise API endpoints
./scripts/e2e-check.sh --pr <n>            # post results as PR comment
```

## Workflow rules (project-wide)

- **NEVER push directly to `main` or `develop`.** Feature branches + PR (`fix/...`, `feat/...`, `chore/...`).
- **Run `./scripts/test.sh` before any push** and post the result as a PR comment. (Memory rule, applies broadly.)
- **Speckit sync** — when shipping behaviour, update `specs/spec.md`, `specs/plan.md`, `specs/tasks.md`.
- **Discord notify** at the end of every completed task — chat id `1241933442434732128`. Format:
  ```
  [role] title

  ✅/⚠️/❌ outcome
  • bullets

  Branch: x  |  PR: #n
  ```

## Open work / known gaps (as of 2026-05-07)

- **#51 — long-JD evaluate blowup.** Quick JSON-fix landed in #53 so the front end no longer breaks on errors. **Still TODO**: server-side resume *summarisation* (compute once when profile is saved, store on `BaselineProfile`, feed summary instead of raw `skills_text` to `evaluate()`) so long inputs don't hit context limits. Was selected as the strategic fix.
- **Job-listing data**: 36 rows seeded via `scrape_jobs.py` (104: 25 with "後端工程師"; yourator: 11 across "後端工程師" + "後端"). Yourator's API ignores keyword; substring filter is client-side, so wider keywords yield more rows.
- **No real e2e against live LLM** has been run on the seeded data yet — pending.
- **`weasyprint` not installed**; `pdf_url` is null from the BackgroundTask path. To set it manually, POST `/api/callback`.
- **v1 endpoints removed** in migration 0002. Only v2 (profile + evaluate + history) remains.

## Token-saving tips for future sessions

- Don't re-read CLAUDE.md and this skill — load both early, work from memory.
- Prefer `grep` / `rg` over `find -type f` for keyword searches.
- For "where is X used", `grep -rn "X" backend/ scripts/ | grep -v __pycache__ | grep -v test`.
- The `scripts/` directory is the canonical entry-point list — start there before grepping for app code.
