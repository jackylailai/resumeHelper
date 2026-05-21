# AI Engineering Readiness

Status: current as of 2026-05-21

This document tracks production readiness for Resume Helper's LLM workflow.
The product is workflow-first: application code owns orchestration, state
transitions, persistence, validation, auditability, and user review. LLMs are
bounded providers inside specific steps.

## Workflow Boundary

Current canonical flow:

```text
baseline profile + job description
  -> evaluate (sync by default, async job when selected)
  -> application-owned score routing
  -> optional durable tailor job
  -> optional beautify/PDF
  -> human review
  -> application tracking
```

LLMs may score, summarize, extract, tailor, or transform. They must not own
arbitrary next-step decisions, submit applications, or mutate workflow state
outside typed application code.

## Readiness Checklist

| Area | Target state | Current state | Owner issue |
|------|--------------|---------------|-------------|
| Deterministic orchestration | App-owned flow, score routing, review gates, and status transitions | Mostly implemented for evaluate/tailor/beautify/application tracking; one-click URL flow is still separate work | #74 |
| Explicit input specs | Every LLM call documents required inputs, optional inputs, source of truth, and prompt version | Documented in `docs/ai-workflow/README.md`, `docs/eval-harness.md`, `docs/prompts.md`, and `specs/current-product-spec.md`; proof point retrieval is connected to tailoring and generated resumes store selected proof point IDs | #77 |
| Explicit output specs | Every LLM output has a schema and fail-closed validation policy | Implemented for evaluate, tailor, structured extraction, and beautify | #113, #126, #127 |
| Eval harness and regression reporting | Deterministic fixtures run in CI and produce reviewable reports | CI runs evaluate, tailor, extract, and beautify fake-backend harnesses and uploads reports | #113, #124, #126, #127 |
| Prompt and model lifecycle | Versions, model/backend metadata, prompt source, and replay path are persisted or reportable | Per-step prompt versions, prompt source paths, prompt source hashes, audit metadata, and evaluate prompt replay are implemented | #128 |
| Observability and audit trail | Every LLM call records request ID, workflow step, model/backend, prompt metadata, hashes, latency, tokens, result status, and typed error | Metadata-first `llm_audit_logs` are implemented; no dedicated audit browser yet | #125, #128 |
| Factuality and safety guardrails | Tailored resumes preserve source facts; beautify cannot add scripts/external resources; prompt injection is neutralized | Prompt trust boundaries, output contracts, smoke-level factuality harnesses, and proof-point prompt attribution are implemented; broader source-fact coverage remains | #139, #126, #127, #77 |
| Durable jobs and reliability | Long-running AI work is persisted with queued/running/succeeded/failed/cancelled states, retry/backoff, and restart behavior | Implemented for async single-JD evaluate jobs and tailoring jobs through `ai_jobs`; scrape runs are also persisted | #71 |
| Cost, quota, and latency controls | Batch workflows have limits, budget preflight, token/cost capture, and provider-call guardrails | Batch quota and privacy guardrails are implemented; token/cost capture exists when provider metadata is available | #129 |
| Security and privacy | Secrets stay out of repo/UI/logs; outbound fetches are constrained; sensitive content is not duplicated into logs by default | SSRF controls, rate limits, surface hardening, provider-call guardrails, and metadata-first audit logs are implemented | #137, #138, #140 |

## PR Expectations

Any PR that changes a prompt, model, LLM output contract, scoring threshold,
routing rule, validation policy, or LLM input source must include:

- which workflow step is affected
- before/after prompt version or model behavior
- deterministic harness results
- prompt replay results when evaluating prompt behavior
- notes on factuality, privacy, and audit metadata impact

The pull request template contains the required checklist. CI also runs the
deterministic AI harnesses on every PR.

## Current Open Work

Recommended next implementation order:

1. #77: finish proof point library UX and ranking refinements.
2. #74: build one-click job URL -> scored tailored PDF workflow.
3. #38: continue crawler/evaluator scale-out work as needed.

## Closed Foundation Work

- #113: eval harness and stricter output constraints.
- #124: deterministic AI harnesses in CI.
- #125: LLM audit log.
- #126: tailoring factuality contract and regression harness.
- #127: structured extraction and beautify output contracts.
- #128: prompt/model lifecycle tracking and replay support.
- #129: cost, quota, and privacy guardrails for batch AI workflows.
- #71: durable background job queue for tailoring and async single-JD evaluate.
- #137: SSRF protections for outbound HTTP.
- #138: rate limiting and DoS protection for LLM-triggering endpoints.
- #139: prompt injection trust boundary for untrusted text.
- #140: container, debug endpoint, and PDF download hardening.
