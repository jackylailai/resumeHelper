# Product Roadmap

This roadmap reflects the current main branch after the crawler, JD database,
application tracking, and scrape scheduling work. Older Phase 1 documents remain
as historical context, but this file is the current planning reference.

## Current System

The app is a single-user AI workflow tool for job search execution.

Implemented:

- Baseline profiles and profile-scoped evaluation.
- JD paste and bulk evaluation.
- Three-tier status routing:
  - `ready_to_submit`
  - `needs_tailoring`
  - `skip`
- Generated resume drafts and PDF/HTML beautification.
- JD database and browser.
- Scrapers for 104, Yourator, and LinkedIn guest jobs.
- Scrape run history with cancellation states.
- Controllable scrape scheduling UI and cron wrapper.
- Batch evaluation of stored job listings.
- Recommended opportunities and application tracker.
- Structured JSON error envelopes and request IDs.

## High-Priority Near Term

| Issue | Theme | Why it matters |
|-------|-------|----------------|
| #113 | LLM eval harness and stricter output constraints | Prevent prompt/model/parser changes from silently degrading recommendations or resume output. |
| #114 | AI engineering production maturity checklist | Define production-readiness criteria for LLM workflow reliability. |
| #115 | README and current product specs refresh | Keep the product/spec baseline aligned with main. |

## Product Work

| Issue | Theme | Notes |
|-------|-------|-------|
| #74 | One-click job URL to scored tailored PDF | Product-mainline flow: paste URL, fetch JD, score, tailor, produce PDF for review. |
| #77 | Proof point and achievement library | CRUD exists and tailoring now uses selected evidence; ranking refinements and UI controls remain. |

## Architecture Work

| Issue | Theme | Notes |
|-------|-------|-------|
| #71 | Durable background job queue | In progress for tailoring: evaluate/history expose `tailoring_job_id` + `tailoring_status`, `/api/jobs/{job_id}` exposes status/result/error/progress, and the frontend polls durable job state before loading history. Backend queue hardening must preserve restart safety. |

## AI Engineering Maturity Targets

The target architecture treats LLM calls as typed workflow steps:

```text
input spec
  -> prompt/model version
  -> LLM call
  -> output schema validation
  -> deterministic application state transition
  -> audit trail and report
```

Required capabilities:

- Eval harness with golden fixtures and regression reports.
- Output contracts for evaluate, tailor, structured extraction, and beautify.
- Factuality checks for tailored resumes.
- Prompt/model versioning with audit metadata.
- Observability for latency, token usage, errors, and request IDs.
- Durable job state for long-running LLM work, starting with tailoring jobs.
- Human review gate before application submission.
- Cost, quota, and privacy controls.

## Suggested Sequence

1. Finish #115 so documentation reflects current main.
2. Implement #113 as the first AI engineering hardening slice.
3. Use #113 results to guide #74 and #77 safely.
4. Implement #71 once long-running work needs stronger reliability guarantees.
5. Continue #114 as an umbrella checklist until all readiness items are mapped
   to code, docs, or follow-up issues.

## Historical Notes

- The original Phase 1 spec lives in
  `specs/001-resume-upload-rating/spec.md`.
- That spec is useful for early evaluator behavior, but no longer describes the
  full product surface.
- The current product reference is `specs/current-product-spec.md`.
