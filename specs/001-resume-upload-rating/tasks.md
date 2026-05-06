# Tasks

**Spec authority**: `spec.md` (three-tier evaluation flow)
**Roadmap**: `specs/roadmap.md`

TDD: write tests RED before implementation.

---

## Phase 1 — Core (complete)

### P1-T01 · Schema + Migration ✅
- [x] `0002_poc_schema.py`: `baseline_profile`, `job_analyses`, `generated_resumes`
- [x] `0003_three_tier_fields.py`: `status`, `can_submit`, `skip_reason`, `explanation`, `strengths`, `gaps`
- [x] ORM models: `baseline_profile.py`, `job_analysis.py`, `generated_resume.py`

### P1-T02 · Pydantic Schemas ✅
- [x] `schemas/profile.py`: `ProfileIn`, `ProfileOut`
- [x] `schemas/evaluate.py`: `EvaluateIn`, `EvaluateOut`, `CallbackIn`, `HistoryItemOut`, `HistoryDetailOut`, `SubmittableResumeOut`

### P1-T03 · Services ✅
- [x] `services/evaluator_v2.py`: read baseline → call LLM → three-tier classification
- [x] `services/hashing.py`: `jd_hash()` deduplication
- [x] `workers/tailor.py`: background tailoring using saved baseline profile
- [x] `services/llm/anthropic.py`: `evaluate()` and `tailor()` via Anthropic API
- [x] `services/llm/fake.py`: deterministic stub for tests

### P1-T04 · API Endpoints ✅

| Endpoint | Test file | Status |
|----------|-----------|--------|
| `POST /api/profile` | `test_profile_endpoint.py` | ✅ |
| `POST /api/profile/upload` | — | ✅ (PDF → pypdf extract → upsert) |
| `GET /api/profile` | `test_profile_endpoint.py` | ✅ |
| `POST /api/evaluate` | `test_evaluate_endpoint.py` | ✅ |
| `POST /api/callback` | `test_callback_endpoint.py` | ✅ |
| `GET /api/history` | `test_history_endpoint.py` | ✅ |
| `GET /api/history/{id}` | `test_history_detail.py` | ✅ |
| `GET /api/submittable` | `test_submittable_endpoint.py` | ✅ |

**Bug fixes shipped with P1-T04:**
- `upsert_baseline`: strips NUL (`\x00`) bytes before DB write (fixes 500 on PDF-pasted text)
- `set_profile`: `ValueError` now returns HTTP 400 with message instead of crashing

### P1-T05 · Three-tier logic tests ✅
- [x] `test_three_tier_evaluate.py`: ready_to_submit / needs_tailoring / skip
- [x] `test_tailor_worker.py`: tailoring uses baseline profile, not JD

### P1-T06 · E2E UI ✅
- [x] `static/app.js`: Evaluate tab, History tab, Profile tab
- [x] `static/index.html`: single-page app
- [x] Profile tab: PDF file picker replaces textarea input; extracted text shown as read-only preview

### P1-T07 · Multi-Profile CRUD + Profile-Scoped Evaluation ✅ (PR #17)
- [x] `0004_multi_profile.py`: add `name`/`created_at` to `baseline_profile`; add `profile_id` FK on `job_analyses` (SET NULL); drop `jd_hash` unique; add composite unique `(jd_hash, profile_id)`
- [x] `models/baseline_profile.py`: add `name`, `created_at` columns
- [x] `models/job_analysis.py`: add `profile_id` FK column
- [x] `schemas/profile.py`: `ProfileIn` adds `name`; new `ProfileUpdateIn`; `ProfileOut` adds `name`, `created_at`
- [x] `schemas/evaluate.py`: `EvaluateIn` adds `profile_id`; `HistoryItemOut` adds `profile_id`
- [x] `services/evaluator_v2.py`: full CRUD (`list_profiles`, `get_profile`, `create_profile`, `update_profile`, `delete_profile`); `evaluate_jd` resolves profile by `profile_id` or latest; cache scoped to `(jd_hash, profile_id)`
- [x] `api/profile.py`: `GET/POST/PUT/DELETE /api/profiles`; `POST /api/profiles/upload`; legacy singular endpoints preserved
- [x] `workers/tailor.py`: looks up profile by `job.profile_id` (falls back to latest)
- [x] `static/index.html` + `app.js`: Profile tab table + Add form; Evaluate tab profile selector dropdown
- [x] `tests/integration/v2/test_profiles_endpoint.py`: 14 tests covering CRUD, upload, cache isolation, legacy compat

---

## Phase 2 — Bulk Ingestion (in progress)

### P2-T01 · Bulk JD Evaluate endpoint
- [ ] `schemas/evaluate.py`: add `BulkEvaluateIn`, `BulkEvaluateResult`, `BulkEvaluateOut`
- [ ] `api/evaluate.py`: add `POST /api/evaluate/bulk`
  - Deduplicate by jd_hash
  - Trigger background tailoring per new needs_tailoring job
  - Return totals: `total`, `new`, `cached`
- [ ] Test: `tests/integration/v2/test_bulk_evaluate.py`
  - bulk returns correct totals
  - duplicate JDs in same batch are cached
  - needs_tailoring JDs trigger tailoring tasks

---

## Phase 3 — Roadmap (future)

- Crawler / n8n job ingestion pipeline
- Multi-user authentication
- PDF generation (weasyprint)
- LLM audit log (token cost / latency)
- Kubernetes deployment
