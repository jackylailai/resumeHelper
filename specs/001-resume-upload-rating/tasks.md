---
description: "Task list for Resume Upload & Rating feature"
---

# Tasks: Resume Upload & Rating

**Input**: Design documents in `/specs/001-resume-upload-rating/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/openapi.yaml

**Tests**: REQUIRED. Constitution Principle II (TDD) is non-negotiable —
contract + integration tests are written before implementation in every story.

## Format: `[ID] [P?] [Story] Description`

- **[P]** = parallel-safe (different files, no shared state)
- **[Story]** = US1 / US2 / US3 / FOUND / SETUP / POLISH

## Path Conventions

Layout per `plan.md` Structure Decision:

- Backend: `backend/app/...`, tests in `backend/tests/`
- Static UI: `static/`
- Specs / contracts: `specs/001-resume-upload-rating/`

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] **T001** [SETUP] Create directory skeleton: `backend/app/{api,models,schemas,services,services/llm,workers}`, `backend/tests/{unit,integration,contract}`, `static/`, `samples/`
- [ ] **T002** [SETUP] Write `backend/requirements.txt` with pinned versions: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `psycopg2-binary`, `alembic`, `pydantic>=2`, `pydantic-settings`, `python-dotenv`, `python-multipart`, `pypdf`, `python-docx`, `anthropic`, `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx`, `schemathesis`, `testcontainers[postgres]`, `ruff`, `mypy`
- [ ] **T003** [P] [SETUP] Configure `pyproject.toml` with ruff + mypy + pytest settings (line-length 100, strict mypy on `backend/app`, coverage fail-under 85)
- [ ] **T004** [P] [SETUP] Create `docker-compose.yml` with `postgres:16` service (volume `postgres_data`, healthcheck, env vars)
- [ ] **T005** [P] [SETUP] Update `.env.example` per `quickstart.md` (DATABASE_URL, ANTHROPIC_API_KEY, STORAGE_DIR, LLM_PROMPT_VERSION, MAX_UPLOAD_BYTES, PORT)
- [ ] **T006** [P] [SETUP] Move `index.html` and `styles.css` from repo root into `static/`; add stub `static/upload.html` and `static/app.js`
- [ ] **T007** [SETUP] Add a sample resume + JD pair in `samples/` (placeholder `.pdf` + `.txt`) for manual smoke tests and integration fixtures

---

## Phase 2: Foundational (Blocks All User Stories)

- [ ] **T010** [FOUND] Implement `backend/app/config.py` using `pydantic-settings` (loads `.env`, validates required keys, exposes `Settings` singleton)
- [ ] **T011** [FOUND] Implement `backend/app/db.py`: SQLAlchemy 2.x engine, `SessionLocal`, `Base = DeclarativeBase`, `get_db()` dependency
- [ ] **T012** [FOUND] Set up Alembic in `backend/alembic/` with `env.py` reading `Settings.database_url`
- [ ] **T013** [FOUND] Implement all four ORM models per `data-model.md`: `models/resume.py`, `models/resume_version.py`, `models/resume_evaluation.py`, `models/evaluation_job.py`, plus `evaluation_cache` table
- [ ] **T014** [FOUND] Generate Alembic migration `0001_initial.py` covering the four tables + `evaluation_cache` + indexes from `data-model.md`
- [ ] **T015** [P] [FOUND] Implement `backend/app/api/envelope.py`: `success(data, **meta)` / `error(code, message, **meta)` returning `{data, error, meta}` per Principle IV
- [ ] **T016** [P] [FOUND] Implement `backend/app/main.py`: create FastAPI app, attach request-id middleware (uuid7 per request), mount `static/` at `/`, include routers, register startup hook that resets orphaned `running` jobs to `failed (worker_crashed)`
- [ ] **T017** [P] [FOUND] Implement `backend/app/api/health.py` (`GET /api/health` returns envelope `{status: "ok"}`)
- [ ] **T018** [P] [FOUND] Implement `backend/app/services/hashing.py`: `canonicalize(text)`, `content_hash`, `jd_hash`, `cache_key` per `data-model.md`
- [ ] **T019** [P] [FOUND] Implement `backend/app/services/storage.py`: `save(bytes, file_hash, ext) -> path`, `read(path)`, `STORAGE_DIR` from settings; rejects path traversal
- [ ] **T020** [FOUND] Implement `backend/app/services/llm/__init__.py` (`LLMClient` Protocol with `evaluate(parsed_text, jd, prompt_version) -> EvaluationResult`) and `services/llm/fake.py` (deterministic results keyed by `(content_hash, jd_hash)`); production `services/llm/anthropic.py` is a stub raising `NotImplementedError` until US1 implementation phase
- [ ] **T021** [FOUND] Implement `backend/app/services/parsing.py`: dispatches `.pdf` → `pypdf`, `.docx` → `python-docx`, returns plain text or raises `NoExtractableTextError`; magic-byte verification before parser selection
- [ ] **T022** [FOUND] Wire test infrastructure in `backend/tests/conftest.py`: `testcontainers-postgres` fixture, FastAPI `TestClient`, `FakeLLMClient` override, sample-file fixture loader

**Checkpoint**: Foundation green; no user-story endpoints yet but `/api/health` works and tests run.

---

## Phase 3: User Story 1 — Upload Resume and Receive Rating (P1) 🎯 MVP

**Goal**: A user uploads a resume + JD and receives a 0–100 score with explanation.

**Independent Test**: `POST /api/resumes` with a sample PDF + JD → response contains `data.score` in `[0,100]` and a non-empty `data.explanation`. If processing exceeds 5 s, response is 202 with a `job_id` and a subsequent `GET /api/jobs/{job_id}` returns `succeeded` with the evaluation.

### Tests for User Story 1 (write FIRST, ensure RED)

- [ ] **T030** [P] [US1] Contract test: `backend/tests/contract/test_openapi_us1.py` runs `schemathesis` against the spec file, restricted to `POST /api/resumes`, `GET /api/evaluations/{id}`, `GET /api/jobs/{id}`
- [ ] **T031** [P] [US1] Integration test: `backend/tests/integration/test_upload_sync.py` — small PDF + JD → 200 envelope with score + explanation, persisted `ResumeVersion` + `ResumeEvaluation` rows (uses FakeLLMClient → returns within 5 s)
- [ ] **T032** [P] [US1] Integration test: `backend/tests/integration/test_upload_async.py` — FakeLLM with simulated 6 s delay → first response is 202 with `job_id`, subsequent poll transitions `pending → running → succeeded`
- [ ] **T033** [P] [US1] Integration test: `backend/tests/integration/test_upload_rejections.py` — covers FR-001 unsupported format (415), FR-002 oversize (413), FR-010 no extractable text (422)
- [ ] **T034** [P] [US1] Unit test: `backend/tests/unit/test_parsing.py` — pdf path, docx path, scanned-image PDF raises `NoExtractableTextError`, magic-byte mismatch rejected
- [ ] **T035** [P] [US1] Unit test: `backend/tests/unit/test_hashing.py` — canonicalization is NFC + whitespace stable; identical text yields identical `content_hash`; minor whitespace variations collide intentionally

### Implementation for User Story 1

- [ ] **T040** [US1] Implement Pydantic schemas in `backend/app/schemas/resume.py` and `schemas/evaluation.py` matching the OpenAPI components
- [ ] **T041** [US1] Implement `backend/app/services/evaluator.py`: `run_evaluation(version, jd, prompt_version)` — checks `evaluation_cache`, calls `LLMClient`, persists `ResumeEvaluation` + cache row, validates score range (0–100), records `latency_ms` + token counts
- [ ] **T042** [US1] Implement `backend/app/workers/tasks.py`: `enqueue_evaluation(job_id)` body that flips `EvaluationJob.status` `pending → running → succeeded|failed` and links the resulting evaluation
- [ ] **T043** [US1] Implement `backend/app/api/resumes.py` `POST /api/resumes`:
  1. validate file size + extension + magic bytes
  2. parse text (raise 422 on empty)
  3. compute hashes; if cache hit, return 200 envelope with cached evaluation (`meta.cached=true`, `meta.status=succeeded`)
  4. else create Resume (or attach to `resume_id`), insert ResumeVersion (with monotonic version_number), insert pending EvaluationJob, schedule `BackgroundTasks.add_task(enqueue_evaluation, job_id)`
  5. return 202 envelope with `job` payload
- [ ] **T044** [US1] Implement `backend/app/api/evaluations.py` `GET /api/evaluations/{id}` (404 if missing)
- [ ] **T045** [US1] Implement `backend/app/api/resumes.py` `GET /api/jobs/{id}` (separate router file `api/jobs.py`); when `status=succeeded` includes the `evaluation` payload
- [ ] **T046** [US1] Implement production `services/llm/anthropic.py`: structured-output prompt returning `{score, strengths[], gaps[], explanation}`; validate JSON shape; raise `LLMUnavailable` on transport errors so the job moves to `failed (llm_unavailable)`
- [ ] **T047** [US1] Wire structured logging fields per Principle constraints: `request_id`, `job_id`, `prompt_version`, `latency_ms`, `token_count` on every evaluator log line
- [ ] **T048** [US1] Build minimal `static/upload.html` + `static/app.js`: file input, JD textarea, Submit, score + explanation card, polls `/api/jobs/{id}` when 202

**Checkpoint**: US1 fully runnable end-to-end. MVP demonstrable.

---

## Phase 4: User Story 2 — Modify Resume and Get Updated Rating (P2)

**Goal**: New uploads under an existing `resume_id` create a new version and return a fresh rating; identical content returns the cached rating instantly.

**Independent Test**: After completing US1, re-upload a different resume with the same `resume_id` → new `version_number`, new evaluation; re-upload an identical file → returns cached evaluation in <1 s (SC-006).

### Tests for User Story 2

- [ ] **T060** [P] [US2] Integration test: `test_version_increments.py` — second upload with `resume_id` creates `version_number=2`; previous version still retrievable
- [ ] **T061** [P] [US2] Integration test: `test_history_endpoint.py` — `GET /api/resumes/{id}/versions` returns reverse-chronological list with score + uploaded_at + brief explanation summary; pagination respected
- [ ] **T062** [P] [US2] Integration test: `test_dedupe_cache_hit.py` — uploading the same content + same JD returns `meta.cached=true` and `latency < 1 s`; no new evaluation row, only a new ResumeVersion row pointing at the cached evaluation via cache_key

### Implementation for User Story 2

- [ ] **T070** [US2] Extend `POST /api/resumes` to accept optional `resume_id`, append a new `ResumeVersion` with the next `version_number`, enforce 50-version cap (reject with 422 `version_cap_exceeded`)
- [ ] **T071** [US2] Implement `GET /api/resumes/{resume_id}/versions` in `api/resumes.py` honoring SC-005 (returns within 2 s up to 50 versions); add brief evaluation summary (first 200 chars of explanation)
- [ ] **T072** [US2] Implement `GET /api/resumes` listing all resumes with latest version + latest score (limit/cursor pagination)
- [ ] **T073** [US2] Update upload UI (`static/app.js`) to: show version history under the score card; offer a "Re-upload" button that POSTs with the existing `resume_id`

**Checkpoint**: US2 + US1 both pass independently.

---

## Phase 5: User Story 3 — View and Compare Ratings (P3)

**Goal**: List versions in order of upload, show score trend, and compare any two versions to surface what changed.

**Independent Test**: After ≥2 versions exist, `GET /api/resumes/{id}/compare?from_version=1&to_version=2` returns score delta + section-level changes.

### Tests for User Story 3

- [ ] **T080** [P] [US3] Integration test: `test_compare_endpoint.py` — score_delta = to.score − from.score; `changed_sections` lists section names whose text differs (case-insensitive, whitespace-normalized)
- [ ] **T081** [P] [US3] Unit test: `test_section_diff.py` — section detector splits parsed text on canonical headers (`Experience`, `Education`, `Skills`, `Projects`, `Summary`); flags adds/removes/edits

### Implementation for User Story 3

- [ ] **T090** [US3] Implement `backend/app/services/section_diff.py`: `detect_sections(text) -> dict[str,str]`, `diff_sections(a, b) -> list[str]`
- [ ] **T091** [US3] Implement `GET /api/resumes/{resume_id}/compare` in `api/resumes.py`
- [ ] **T092** [US3] Add a comparison view in `static/app.js`: select two versions from the history list → table of score, changed sections, side-by-side excerpt

**Checkpoint**: All three stories pass independently.

---

## Phase 6: Polish & Cross-Cutting

- [ ] **T100** [POLISH] Run full contract suite (`schemathesis`) against the live app; fix any drift between OpenAPI doc and implementation
- [ ] **T101** [P] [POLISH] Add `pytest --cov` gate; raise coverage to ≥85% on `backend/app/`, 100% on `services/parsing.py`, `services/hashing.py`, `services/evaluator.py` (Principle III)
- [ ] **T102** [P] [POLISH] Run `ruff check` and `mypy --strict` on `backend/app`; fix or explicitly justify suppressions
- [ ] **T103** [P] [POLISH] Add `README` snippet pointing to `quickstart.md`; ensure `CLAUDE.md` reference still resolves
- [ ] **T104** [POLISH] Add a smoke script `scripts/smoke.sh`: spin up postgres → migrate → run uvicorn → POST sample → GET job until succeeded → assert score in range
- [ ] **T105** [POLISH] Verify SC-001 (≤30 s end-to-end) and SC-006 (<1 s cached) with a manual measurement, recorded in `quickstart.md` "Performance notes" section

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1) → Foundational (Phase 2) → User Stories (Phases 3–5) → Polish (Phase 6)
- Foundational completion is the **single hard gate** for all user-story work.

### Within Each User Story

- Tests in `tests/contract/` and `tests/integration/` MUST be written and observed RED before any implementation task.
- Models and schemas before services; services before API routes; API before UI wiring.
- Each story finishes with its own checkpoint — do not start the next story until the previous story passes its independent test.

### Parallel Opportunities

- **Phase 1 setup**: T003 / T004 / T005 / T006 / T007 are file-disjoint → all `[P]`.
- **Phase 2 foundational**: T015–T021 are file-disjoint after T010–T014 land.
- **Tests within a story**: T030–T035, T060–T062, T080–T081 are file-disjoint and `[P]`.
- **Stories**: After Foundational, US1 must finish first (others build on its endpoints + UI scaffolding); US2 and US3 can be developed in parallel by different contributors thereafter, but in single-developer mode run them in priority order.

---

## Implementation Strategy

### MVP First

1. Phase 1 → Phase 2 → Phase 3 (US1).
2. **STOP and demo**: upload a sample, see a score. This is the minimum value proposition.

### Incremental Delivery

1. MVP → demo
2. Add US2 → demo (history + cache)
3. Add US3 → demo (comparison)
4. Polish → coverage / lint / smoke / measurements

---

## Notes

- `[P]` = file-disjoint, no shared mutable state.
- Test history MUST show tests preceded code (Principle II); reviewers verify via git log.
- Commit after each task or logical group.
- Every PR description states which principles are touched per Constitution governance.
