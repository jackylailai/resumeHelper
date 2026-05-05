# Tasks

**Scope authority**: `scope-correction.md`
**Roadmap**: `specs/roadmap.md`
**Agent roles**: `agent.md`

TDD is non-negotiable: tests written and confirmed RED before implementation.

---

## Phase 1 — POC (current)

### P1-T01 · Schema + Migration
- [ ] Delete old 4-table Alembic migration
- [ ] Write new `0002_poc_schema.py`: `baseline_profile`, `job_analyses`, `generated_resumes`
- [ ] New ORM models: `models/baseline_profile.py`, `models/job_analysis.py`, `models/generated_resume.py`
- [ ] Delete old models: `resume.py`, `resume_version.py`, `resume_evaluation.py`, `evaluation_job.py`

### P1-T02 · Pydantic Schemas
- [ ] `schemas/profile.py`: `ProfileIn`, `ProfileOut`
- [ ] `schemas/evaluate.py`: `EvaluateIn`, `EvaluateOut`, `CallbackIn`
- [ ] `schemas/history.py`: `HistoryItemOut`, `GeneratedResumeOut`

### P1-T03 · Services
- [ ] `services/evaluator.py` rewrite: read baseline → build prompt → call LLMClient → return score
- [ ] `services/generator.py`: POST n8n webhook with `{job_analysis_id, jd_full_text, baseline_skills}`
- [ ] Keep: `services/hashing.py`, `services/parsing.py`
- [ ] Delete: `services/storage.py`, `services/evaluator.py` (old), `workers/tasks.py`

### P1-T04 · API Endpoints
Write tests RED first, then implement:

| Endpoint | Test file |
|----------|-----------|
| `POST /api/profile` | `test_profile_endpoint.py` |
| `GET /api/profile` | `test_profile_endpoint.py` |
| `POST /api/evaluate` | `test_evaluate_endpoint.py` |
| `POST /api/callback` | `test_callback_endpoint.py` |
| `GET /api/history` | `test_history_endpoint.py` |
| `GET /api/history/{id}` | `test_history_detail.py` |
| `POST /api/history/{id}/regenerate` | `test_regenerate.py` |

### P1-T05 · ClaudeCLIClient unit test
- [ ] `tests/unit/test_claude_cli_client.py`: mock subprocess, verify prompt rendering, JSON parse, error handling

### P1-T06 · n8n workflow setup
- [ ] `docker compose up n8n` → configure webhook trigger node
- [ ] LLM node: use `modes/generate.md` prompt
- [ ] Output node: POST to `http://host.docker.internal:8000/api/callback`
- [ ] Document workflow export in `specs/n8n-workflow.json`

### P1-T07 · UI rewrite
- [ ] `static/upload.html`: profile setup section + JD input + evaluate button + result card + history list
- [ ] `static/app.js`: full rewrite for new API surface

### P1-T08 · Cleanup
- [ ] Delete old test files: `test_upload_sync.py`, `test_upload_async.py`, `test_upload_rejections.py`, `test_version_increments.py`, `test_history_endpoint.py` (old), `test_dedupe_cache_hit.py`
- [ ] `ruff check` + `mypy --strict` clean
- [ ] Coverage ≥ 85% on `backend/app/`
- [ ] Update README: quickstart section

**Checkpoint**: `docker compose up -d postgres n8n` → `uvicorn` → paste JD → get score → get resume.

---

## Phase 2 — Infra (future)

- [ ] `GroqLLMClient` + `LLM_BACKEND` env switch
- [ ] LangChain: `PromptTemplate`, `StructuredOutputParser`, streaming
- [ ] `nginx` in docker-compose (reverse proxy + rate limit)
- [ ] `Dockerfile` for FastAPI
- [ ] `docker-compose.prod.yml`
- [ ] SSL setup (Let's Encrypt)

## Phase 3 — High Concurrency (future)

See `specs/roadmap.md` for full design.

- [ ] Redis + Celery workers (replace n8n for generation)
- [ ] pgBouncer connection pooling
- [ ] Kubernetes manifests + Ingress
- [ ] Multi-user (add `user_id` to all tables)
- [ ] LangSmith tracing
