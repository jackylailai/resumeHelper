# AI Workflow Showcase

This is the demo-facing view of the AI workflow work. It is a product and
engineering showcase sheet, not a backlog.

Last updated: 2026-05-21

## One-Line Pitch

Resume Helper is not a chatbot wrapper. It is an application-owned AI workflow
for job search execution: collect JDs, score fit, queue durable resume work,
review generated materials, and track application decisions.

```text
profile + JD
  -> validated scoring contract
  -> deterministic application state
  -> durable evaluate/tailor jobs
  -> factuality and HTML safety checks
  -> audit metadata and CI harness reports
  -> human review before submission
```

## Demo Path

| Step | Screen / command | What to point out |
|------|------------------|-------------------|
| 1 | `/` System Status + Profile selector | The app knows whether DB/LLM dependencies are ready before running AI work. |
| 2 | Evaluate one pasted JD | The default path is fast and synchronous for a clean demo. |
| 3 | Check **Async job** and evaluate again | Evaluation can be queued and polled through `GET /api/jobs/{job_id}`. |
| 4 | Use a 60-84 score JD | The result queues a durable tailoring job instead of hiding background work. |
| 5 | Open generated resume, Beautify, download PDF | Resume output stays reviewable before submission. |
| 6 | `/jobs.html` -> Add to tracker | Scored opportunities flow into the long-lived application tracker. |
| 7 | CI PR comment / harness artifacts | AI behavior is covered by deterministic fixture reports, not manual inspection alone. |

## Show-Off Inventory

| Capability | What to show | Proof in repo | Status |
|------------|--------------|---------------|--------|
| Contract-first evaluate | LLM score output must include `score`, `explanation`, `strengths`, and `gaps`; invalid output fails closed. | `backend/app/services/llm/contracts.py`, `backend/tests/unit/test_llm_contracts.py` | Done |
| Application-owned routing | The model returns a score, but app code decides `ready_to_submit`, `needs_tailoring`, or `skip`. | `backend/app/services/evaluator_v2.py`, `backend/app/models/job_analysis.py` | Done |
| Durable async evaluate | `POST /api/evaluate/jobs` and `POST /api/evaluate?async=true` create `ai_jobs.kind=evaluate`; the UI can poll the job. | `backend/app/api/evaluate.py`, `backend/app/workers/job_queue.py`, `backend/tests/integration/v2/test_async_evaluate_jobs.py` | Done |
| Durable tailoring | Mid-score evaluations queue `ai_jobs.kind=tailor` with retry/error/cancel state. | `backend/app/services/job_queue.py`, `backend/app/workers/tailor.py`, `backend/tests/integration/v2/test_three_tier_evaluate.py` | Done |
| Deterministic harnesses | CI runs fake-backend evaluate, tailor, extract, and beautify fixtures and uploads reports. | `.github/workflows/pr-review.yml`, `backend/evals/fixtures/`, `docs/eval-harness.md` | Done |
| LLM audit log | Production LLM calls write backend, model, prompt version, hashes, latency, tokens, status, and typed error metadata. | `backend/app/models/llm_audit_log.py`, `backend/app/services/llm/audit.py`, `backend/tests/integration/v2/test_llm_audit_log.py` | Done |
| Tailor factuality harness | Generated resume fixtures check required baseline facts and forbidden hallucinated facts. | `backend/app/services/tailor_harness.py`, `backend/evals/fixtures/tailor_cases.json` | Done |
| Proof point attribution | Tailoring can pull relevant profile/global proof points and store selected `proof_point_ids`. | `backend/app/services/proof_points.py`, `backend/tests/integration/v2/test_tailoring_proof_points.py` | Foundation done |
| Prompt/model lifecycle | Prompt versions are per step, source hashes are reportable, and evaluate prompt replay exists. | `docs/prompts.md`, `backend/app/services/llm/prompt_registry.py`, `backend/app/services/prompt_replay.py` | Done |
| Structured extraction contract | Profile extraction uses a known schema and rejects unknown top-level or nested keys. | `backend/evals/fixtures/extract_cases.json`, `backend/app/api/profile.py` | Done |
| Beautify HTML contract | Beautified resume HTML must be complete, self-contained, script-free, and free of known hallucinated facts. | `backend/evals/fixtures/beautify_cases.json`, `backend/app/api/beautify.py` | Done |
| Cost and privacy guardrails | Batch AI work has item/token/cost limits, provider-call switches, and metadata-first logging. | `backend/app/services/ai_guardrails.py`, `readme.md` | Done |
| Security backstops | Prompt-injection boundary, SSRF guard, rate limits, and production auth hardening are documented and tested. | `docs/ai-workflow/README.md`, `backend/app/services/http/safe_client.py`, `backend/app/rate_limit.py` | Done |
| Human review boundary | The system prepares materials and tracks applications, but does not submit applications automatically. | `specs/current-product-spec.md`, `docs/ai-workflow/README.md` | Done |

## Demo Commands

Deterministic evaluate harness:

```bash
python -m backend.app.cli eval-harness \
  --backend fake \
  --report-json artifacts/evals/evaluate.json \
  --report-md artifacts/evals/evaluate.md
```

Tailor factuality harness:

```bash
python -m backend.app.cli tailor-harness \
  --backend fake \
  --report-json artifacts/evals/tailor.json \
  --report-md artifacts/evals/tailor.md
```

Prompt registry and replay:

```bash
python -m backend.app.cli prompt-registry

python -m backend.app.cli prompt-replay \
  --backend fake \
  --old-prompt-version resume-fit-v1 \
  --new-prompt-version resume-fit-v2 \
  --report-md artifacts/evals/prompt-replay.md
```

Focused tests for the showoff surface:

```bash
python -m pytest backend/tests/unit/test_llm_contracts.py -q
python -m pytest backend/tests/integration/v2/test_async_evaluate_jobs.py -q
python -m pytest backend/tests/integration/v2/test_llm_audit_log.py -q
python -m pytest backend/tests/integration/v2/test_tailoring_proof_points.py -q
```

## Completed Foundation Issues

| Issue | Result | PR |
|-------|--------|----|
| #124 | Deterministic AI eval harness in CI | #130 |
| #125 | LLM audit log for production calls | #131 |
| #126 | Tailoring factuality contract and regression harness | #132 |
| #127 | Structured extraction and beautify output contracts | #133 |
| #128 | Prompt/model lifecycle tracking and replay support | #134 |
| #129 | Cost, quota, and privacy guardrails for batch AI workflows | #135 |
| #71 | Durable background jobs for tailoring and async single-JD evaluate | #176, #178 |
| #175 | Removed active n8n dependency from the core app path | #177 |

## Remaining Show-Off Gaps

| Gap | Why it matters |
|-----|----------------|
| Proof point UX polish | The backend attribution foundation exists, but the editing/ranking UX can become more demo-friendly. |
| Audit/job browser | The API and DB have the state, but a dedicated operations screen would make traceability easier to show live. |
| Broader factuality corpus | The factuality harness is useful, but more role-specific fixtures would make resume safety claims stronger. |
| One-click URL workflow | Scrape + evaluate + tailor is present in pieces; a single guided URL-to-reviewed-resume flow would be a stronger demo. |
