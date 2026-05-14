# AI Workflow Showcase

This file tracks the AI workflow work that is ready to demonstrate. It is a
product and engineering brag sheet, not a roadmap.

Last updated: 2026-05-14

## Demo Story

Resume Helper is not a chatbot wrapper. It is an application-owned AI workflow:

```text
profile + JD
  -> validated LLM scoring output
  -> deterministic score routing
  -> audited production LLM call
  -> validated tailoring output
  -> factuality smoke checks
  -> validated structured extraction / beautify output
  -> human review before submission
```

The important claim is that LLMs are bounded implementation details. The app
owns schemas, routing, persistence, auditability, and failure behavior.

## Show-Off Inventory

| Capability | What To Show | Proof In Repo | Status |
|------------|--------------|---------------|--------|
| Contract-first evaluate | LLM score output must be JSON with `score`, `explanation`, `strengths`, and `gaps`; bad output fails closed. | `backend/app/services/llm/contracts.py`, `backend/tests/unit/test_llm_contracts.py` | Done |
| Application-owned routing | Model returns score, but app decides `ready_to_submit`, `needs_tailoring`, or `skip`. | `backend/app/services/eval_harness.py`, `backend/app/models/job_analysis.py` | Done |
| Deterministic eval harness | CI runs fake-backend fixtures and posts Markdown/JSON reports. | `backend/evals/fixtures/evaluate_cases.json`, `.github/workflows/pr-review.yml`, `docs/eval-harness.md` | Done |
| LLM audit log | Production LLM calls write backend, model, prompt version, hashes, latency, tokens, status, and typed error metadata. | `backend/app/models/llm_audit_log.py`, `backend/app/services/llm/audit.py`, `backend/tests/integration/v2/test_llm_audit_log.py` | Done |
| Tailor output contract | Generated resume output must be structured JSON with suggestions and Markdown resume text. | `backend/app/services/llm/contracts.py`, `backend/app/workers/tailor.py` | Done |
| Tailor factuality harness | Generated resume fixtures check required baseline facts and forbidden hallucinated facts. | `backend/app/services/tailor_harness.py`, `backend/evals/fixtures/tailor_cases.json` | Done |
| Structured extraction contract | Profile extraction uses a known schema and rejects unknown top-level or nested keys. | `backend/evals/fixtures/extract_cases.json`, `backend/app/api/profile.py` | Done |
| Beautify HTML contract | Beautified resume HTML must be complete, self-contained, script-free, and free of known hallucinated facts. | `backend/evals/fixtures/beautify_cases.json`, `backend/app/api/beautify.py` | Done |
| CI visibility | Pull request comments include AI harness reports before SIT results. | `.github/workflows/pr-review.yml` | Done |
| Human review boundary | The system can generate and prepare materials, but it does not submit applications automatically. | `specs/current-product-spec.md`, `docs/ai-workflow/README.md` | Done |

## Demo Commands

Deterministic evaluate harness:

```bash
python -m backend.app.cli eval-harness \
  --backend fake \
  --report-json artifacts/evals/evaluate.json \
  --report-md artifacts/evals/evaluate.md
```

Deterministic tailor factuality harness:

```bash
python -m backend.app.cli tailor-harness \
  --backend fake \
  --report-json artifacts/evals/tailor.json \
  --report-md artifacts/evals/tailor.md
```

Focused contract tests:

```bash
python -m pytest backend/tests/unit/test_llm_contracts.py -q
```

Audit log integration test:

```bash
python -m pytest backend/tests/integration/v2/test_llm_audit_log.py -q
```

## Completed AI Workflow Issues

| Issue | Result | PR |
|-------|--------|----|
| #124 | Deterministic AI eval harness in CI | #130 |
| #125 | LLM audit log for production calls | #131 |
| #126 | Tailoring factuality contract and regression harness | #132 |
| #127 | Structured extraction and beautify output contracts | #133 |

## Remaining Show-Off Gaps

| Issue | Why It Matters |
|-------|----------------|
| #128 | Prompt/model lifecycle tracking will make prompt changes replayable and comparable. |
| #129 | Cost, quota, and privacy guardrails will make batch AI runs safer to operate. |
| #71 | Durable background jobs will make long-running AI work observable, retryable, and cancellable. |
| #77 | Proof-point library will connect JD requirements to source evidence before tailoring. |
