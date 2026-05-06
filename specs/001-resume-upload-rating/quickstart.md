# Quickstart: Resume Fit Evaluator

Single-machine developer setup. Target time: 5 minutes from clone to first
evaluation.

## Prerequisites

- Python 3.11 or newer
- Docker + Docker Compose (for PostgreSQL)
- `claude` CLI installed and authenticated (used by the LLM service)

## 1. Clone & enter the repo

```bash
git clone <repo-url> resumeHelper
cd resumeHelper
```

## 2. Create your `.env`

```bash
cp .env.example .env
```

The defaults in `.env.example` work for local development. No API key needed —
the backend uses the local `claude` CLI.

## 3. Start PostgreSQL

```bash
docker compose up -d postgres
```

Wait until `docker compose ps` shows postgres as `healthy`.

## 4. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## 5. Run migrations

```bash
alembic -c backend/alembic.ini upgrade head
```

## 6. Start the API

```bash
uvicorn backend.app.main:app --reload --port 8000
```

You should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

## 7. Smoke test

```bash
# Health
curl -s http://localhost:8000/api/health
# → {"data":{"status":"ok"},"error":null,"meta":{...}}

# Save your baseline profile
curl -s -X POST http://localhost:8000/api/profile \
  -H "Content-Type: application/json" \
  -d '{"skills_text": "Python, FastAPI, PostgreSQL, Docker, 5 years backend experience"}'

# Evaluate a job description
curl -s -X POST http://localhost:8000/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{"jd_text": "We need a senior backend engineer with FastAPI and Postgres."}'
# → {"data":{"score":82,"status":"needs_tailoring",...},"error":null,"meta":{...}}

# Check history
curl -s http://localhost:8000/api/history
```

## 8. Open the UI

```bash
open http://localhost:8000
```

The UI has three tabs: **Evaluate**, **History**, and **Profile**.

## 9. Bulk evaluate (optional)

```bash
curl -s -X POST http://localhost:8000/api/evaluate/bulk \
  -H "Content-Type: application/json" \
  -d '{"jd_texts": ["JD one...", "JD two...", "JD three..."]}'
# → {"data":{"total":3,"new":3,"cached":0,"results":[...]},...}
```

## Running the test suite

```bash
# Unit tests (no Docker needed)
python -m pytest backend/tests/unit/ -q

# Unit + integration (uses testcontainers-postgres)
python -m pytest backend/tests/unit/ backend/tests/integration/v2/ -q
```

## Common issues

| Symptom | Fix |
|---|---|
| `connection refused` to Postgres | `docker compose up -d postgres`; wait for healthy |
| `claude: command not found` | Install claude CLI: `npm install -g @anthropic-ai/claude-code` |
| Profile 404 on evaluate | POST to `/api/profile` first |
| Score always 0 | LLM client may be using fake/stub — check `app.state.llm_client` |
