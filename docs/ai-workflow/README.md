# AI Workflow Engineering

Resume Helper is designed as a deterministic AI workflow system, not a generic
chatbot. The application owns the job-search flow, persists state, validates LLM
outputs, and keeps human review in front of real-world submission.

## Workflow Model

```text
baseline profile + job description
  -> evaluate fit
  -> route by score
  -> optionally tailor resume
  -> optionally beautify and render PDF
  -> human review
  -> application tracking
```

The LLM is used as a bounded step inside this workflow. It can score, explain,
extract, rewrite, and format content, but application code decides state
transitions such as `ready_to_submit`, `needs_tailoring`, and `skip`.

## Core AI Engineering Concepts

### Output Contract

The project treats each LLM response as an **output contract**: a named schema,
validation policy, and failure behavior for a specific LLM step.

Related terms:

- **Structured output**: asking the model to return a known data shape, usually
  JSON.
- **Output schema**: the formal shape of that data, for example a Pydantic
  model or JSON Schema.
- **Contract-first LLM integration**: application code validates model output
  before using it.
- **Schema-validated generation**: generated content is accepted only after it
  passes schema and safety checks.

For example, the evaluate step expects:

```json
{
  "score": 75,
  "explanation": "Short assessment.",
  "strengths": ["Relevant backend experience"],
  "gaps": ["Missing explicit cloud requirement"]
}
```

Invalid JSON, missing fields, out-of-range scores, blank explanations, or
malformed lists should fail closed instead of silently affecting product state.

### Eval Harness

An **eval harness** is a repeatable test runner for AI behavior. It uses fixture
cases with known inputs and expected behavior, then produces a pass/fail report.

In this project, the harness currently focuses on:

- baseline profile + JD input
- LLM evaluate output
- output contract validation
- score range checks
- deterministic score routing
- tailored resume output validation
- required and forbidden fact checks for generated Markdown
- JSON/Markdown report artifacts

The deterministic `fake` backend is the CI gate because it is stable and does
not require provider credentials. Real LLM backends can be run manually to
inspect model drift.

### Observability And Audit Trail

AI workflow observability means the project can explain what happened after the
fact without logging sensitive resume or JD text by default.

Target metadata for each LLM call:

- request ID or job ID
- workflow step: evaluate, tailor, extract, beautify
- backend and model
- prompt version
- input hash and output hash
- latency
- token counts
- approximate cost where available
- success or typed error code

This turns AI behavior from a black box into an auditable product workflow.

### Egress Policy (SSRF guard)

Every outbound HTTP request that touches user or external input (`scraper_104`,
`scraper_yourator`, `scraper_linkedin`, and the upcoming #74 URL workflow)
flows through `backend/app/services/http/safe_client.py::safe_async_client`.
The guard transport:

- Resolves the target host before each request and refuses if any address
  is loopback, RFC 1918 (`10/8`, `172.16/12`, `192.168/16`), link-local
  (`169.254/16` including cloud-instance metadata), multicast, reserved,
  or unspecified (`0.0.0.0` / `::`).
- Re-applies the same check on every redirect hop (the check sits at the
  `AsyncBaseTransport` layer, so httpx routes each hop back through it).
- Refuses non-HTTP(S) schemes.
- Bounds response body size via `max_response_bytes` (default 10 MB).

Residual risk: DNS rebinding. A hostile resolver can answer the pre-check
with a public IP and the connection with an internal IP. Closing this
requires pinning the resolved IP and forwarding the original `Host` header,
which is out of scope for #137. Document this limitation wherever the
client is given an attacker-supplied URL.

### Factuality Guardrails

Resume generation is higher risk than scoring because it produces material a
user may submit. The system should verify that tailored resumes do not invent:

- employers
- job titles
- dates
- degrees
- certifications
- language scores
- metrics
- skills not present in baseline or proof points

Prompt instructions are useful, but they are not enough. The workflow needs
fixtures, required-fact checks, forbidden-fact checks, and typed failures.

## Current Implementation

Implemented AI workflow foundations:

- configurable LLM backend: fake, Claude CLI, Anthropic API
- deterministic fake backend for tests
- evaluate output contract for score, explanation, strengths, and gaps
- tailor output contract for suggestions and generated Markdown
- structured extraction schema with unknown-key rejection
- beautify HTML contract for complete, self-contained, script-free documents
- application-owned score routing
- profile-scoped JD evaluation cache
- generated resume review before submission
- structured JSON API error envelopes with request IDs
- eval harness CLI for deterministic evaluate cases
- tailor harness CLI for deterministic factuality smoke cases
- CI gate for deterministic evaluate and tailor fixtures
- persisted LLM audit logs for evaluate, tailor, structured extraction, and
  beautify calls

For a concise demo-oriented view of what is ready to show, see
[SHOWCASE.md](SHOWCASE.md).

Known gaps:

- tailoring factuality coverage is still smoke-level and needs broader fixtures
- long-running AI work still needs durable job state
- cost, quota, and privacy guardrails need product-level enforcement

## LLM Audit Log

Production LLM calls write one `llm_audit_logs` row on success or failure. The
row is intentionally metadata-first:

- `request_id`
- workflow step: `evaluate`, `tailor`, `extract`, or `beautify`
- backend and model
- prompt version
- input and output hashes
- latency
- token counts when the provider returns them
- success/failure status and typed error code
- links to profile, job analysis, generated resume, or beautification rows

The audit table does not store full resume or JD text by default. The hashes are
enough to correlate repeated inputs and outputs without turning the audit trail
into another sensitive content store.

## Roadmap

Recommended implementation order:

1. **CI eval harness**
   Run deterministic eval fixtures on every AI-related PR and upload JSON /
   Markdown reports.

2. **LLM audit log**
   Persist backend, model, prompt version, hashes, latency, tokens, status, and
   typed error codes for every LLM call.

3. **Tailoring factuality harness**
   Validate generated resume Markdown against required and forbidden facts.
   Current status: implemented as a deterministic smoke harness.

4. **Extraction and beautify contracts**
   Add typed schemas for structured extraction and safety checks for HTML/PDF
   generation.
   Current status: implemented for the LLM adapters and API persistence path.

5. **Prompt/model lifecycle**
   Version prompts per workflow step and support replay or comparison across
   versions.

6. **Durable jobs and cost guardrails**
   Move long-running AI work into persisted jobs with limits, retry, progress,
   cancellation, and budget controls.

## Issue Map

- #113: LLM eval harness and stricter output constraints
- #114: AI engineering production maturity checklist
- #124: deterministic AI eval harness in CI
- #125: LLM audit log
- #126: tailoring factuality contract and regression harness
- #127: structured extraction and beautify output contracts
- #128: prompt/model lifecycle tracking and replay support
- #129: cost, quota, and privacy guardrails
- #71: durable background job queue
- #77: proof point and achievement library

## Positioning

This project should be presented as an AI workflow product with:

- deterministic orchestration
- contract-first LLM calls
- eval-driven prompt/model changes
- auditable LLM metadata
- factuality checks for generated resumes
- human review before submission

The key engineering claim is simple: LLMs are useful inside the workflow, but
the application owns correctness, state, traceability, and user control.
