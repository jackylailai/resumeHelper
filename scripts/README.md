# scripts/

Helper scripts for local dev. Daily flow is just two:

```bash
./scripts/restart-docker.sh --full   # bring up postgres + app container
./scripts/dev-verify.sh              # sanity-check the running app
```

## Catalog

### Running the app

| Script | What it does | When to use |
|---|---|---|
| `restart-docker.sh` | `docker compose -f docker-compose.yml -f docker-compose.app.yml` rebuild + restart the app container. `--full` also brings up postgres first. Stops any host uvicorn on :8000 to avoid port conflict. | **Default dev path.** After backend code edits or first-time setup. |
| `start.sh` | Boots postgres in docker, then runs uvicorn on the host (with `--reload`). | Host-mode debugging — when you want hot-reload without rebuilding the image. Falls back to `restart-app.sh` for the uvicorn portion. |
| `restart-app.sh` | Restart only the host uvicorn (kills `:8000`, clears `__pycache__`, relaunches in background, logs to `/tmp/resumehelper-fastapi.log`). | Host mode only, after editing backend code without restarting docker. |

### Verification

| Script | What it does |
|---|---|
| `dev-verify.sh` | Hits `/api/health` and `/api/debug/claude-cli-ping`. Exits non-zero if either fails. Honours `BASE_URL=...` env var. |
| `e2e-check.sh` | Runs API smoke tests and optionally posts results to a GitHub PR. |

### Tests

| Script | What it does |
|---|---|
| `test.sh` | Bootstraps `.venv` with brew's `python3.11`/`3.12` (the system Anaconda python is too old), then runs the full pytest suite. Forwards args (`-k some_test`, `--recreate` to rebuild the venv). |
| `e2e.sh` | Runs the Playwright E2E suite under `tools/e2e/tests/`. Bootstraps Playwright on first call. |

### Data

| Script | What it does |
|---|---|
| `scrape_jobs.py` | Scrapes job listings from configured sources and persists drafts. Writes a CSV snapshot to `RESUMEHELPER_BACKUP_DIR` (default `~/resumeHelper_data/backups`) after each successful run. |

### Development utilities

| Script | What it does |
|---|---|
| `validate.py` | Sanity check that all modules import and every FastAPI route is registered. Useful before committing big refactors. |

## Adding a new script

1. Drop it in `scripts/`, set executable bit, give it a `#!/usr/bin/env bash` (or python) shebang.
2. Add a comment block at the top describing purpose + usage.
3. Add a row to the relevant table above.
