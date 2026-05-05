# Quickstart: Resume Upload & Rating

Single-machine developer setup. Target time: 5 minutes from clone to first
evaluation.

## Prerequisites

- Python 3.11 or newer
- Docker + Docker Compose (for PostgreSQL)
- An Anthropic API key (`ANTHROPIC_API_KEY`)

## 1. Clone & enter the repo

```bash
git clone <repo-url> resumeHelper
cd resumeHelper
```

## 2. Create your `.env`

```bash
cp .env.example .env
```

Then edit `.env` and set:

```ini
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/resume_helper
ANTHROPIC_API_KEY=sk-ant-...        # required
STORAGE_DIR=./backend/storage
LLM_PROMPT_VERSION=resume-fit-v1
MAX_UPLOAD_BYTES=10485760
PORT=8000
```

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

# Upload + evaluate
curl -s -X POST http://localhost:8000/api/resumes \
  -F "file=@./samples/sample_resume.pdf" \
  -F "job_description=We need a senior backend engineer with FastAPI and Postgres."
```

If the file is small the response is a synchronous `200` with the evaluation.
If processing exceeds 5 s the response is `202` with a `job_id` — poll it:

```bash
curl -s http://localhost:8000/api/jobs/<job_id>
```

## 8. Open the UI

```bash
open http://localhost:8000/upload.html
```

The existing project docs page remains at `http://localhost:8000/`.

## Running the test suite

```bash
# Unit + integration (uses testcontainers-postgres)
pytest backend/tests

# Contract conformance against the OpenAPI doc
schemathesis run --base-url=http://localhost:8000 \
  specs/001-resume-upload-rating/contracts/openapi.yaml
```

Coverage gate (constitution Principle III):

```bash
pytest --cov=backend/app --cov-fail-under=85
```

## Common issues

| Symptom | Fix |
|---|---|
| `connection refused` to Postgres | `docker compose up -d postgres`; wait for healthy |
| `ANTHROPIC_API_KEY` missing | Set it in `.env`; restart uvicorn |
| Upload returns `unsupported_format` | Only `.pdf` and `.docx` are accepted in v1 |
| Upload returns `no_extractable_text` | Scanned-image PDFs are rejected per FR-010 |
| Job stuck in `pending` after server restart | Crash recovery marks orphaned jobs as `failed`; re-upload to retry |
