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
| `GET /api/profile` | `test_profile_endpoint.py` | ✅ |
| `POST /api/evaluate` | `test_evaluate_endpoint.py` | ✅ |
| `POST /api/callback` | `test_callback_endpoint.py` | ✅ |
| `GET /api/history` | `test_history_endpoint.py` | ✅ |
| `GET /api/history/{id}` | `test_history_detail.py` | ✅ |
| `GET /api/submittable` | `test_submittable_endpoint.py` | ✅ |

### P1-T05 · Three-tier logic tests ✅
- [x] `test_three_tier_evaluate.py`: ready_to_submit / needs_tailoring / skip
- [x] `test_tailor_worker.py`: tailoring uses baseline profile, not JD

### P1-T06 · E2E UI ✅
- [x] `static/app.js`: Evaluate tab, History tab, Profile tab
- [x] `static/index.html`: single-page app

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
