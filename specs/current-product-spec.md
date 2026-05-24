# Current Product Specification

**Status**: current main branch reference
**Updated**: 2026-05-21
**Scope**: single-user job search workflow with LLM-assisted scoring,
tailoring, PDF review, scraping, and application tracking

## Product Definition

Resume Helper helps one user decide which jobs are worth applying to and prepare
reviewable application materials.

It is not a generic chatbot. It is a deterministic workflow system that uses
LLMs in bounded steps:

```text
profile + JD
  -> evaluate
  -> route by score
  -> optionally tailor resume
  -> optionally beautify/PDF
  -> human review
  -> application tracking
```

The main UI separates producer and consumer views:

```text
Scrapes -> JD Database -> Evaluate / Batch Score -> Opportunities / Submittable -> Applications
```

## Core Entities

### BaselineProfile

Stores resume/profile source material.

Important fields:

- `id`
- `name`
- `skills_text`
- `structured_data`
- `pdf_path`
- `is_default`

### JobAnalysis

Stores the result of scoring one JD against one profile.

Important fields:

- `jd_hash`
- `profile_id`
- `score`
- `status`
- `strengths`
- `gaps`
- `threshold_met`
- `can_submit`
- `skip_reason`
- `prompt_version`

### GeneratedResume

Stores generated tailored resume content and PDF-related links.

### AIJob

Tracks durable background AI work. `kind=tailor` represents tailoring for a
`needs_tailoring` analysis; `kind=evaluate` represents async single-JD
evaluation.

Important fields:

- `id`
- `kind`
- `job_analysis_id`
- `status`
- `result_payload`
- `error_code`
- `error_message`
- progress fields

Statuses include:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

### JobListing

Stores scraped or imported job listings.

Important fields:

- `source`
- `source_id`
- `title`
- `company`
- `location`
- `url`
- `description`
- `raw_json`
- `job_analysis_id`

### ScrapeRun

Tracks scraper execution.

Statuses:

- `queued`
- `running`
- `cancel_requested`
- `cancelled`
- `succeeded`
- `partial`
- `failed`

### Application

Tracks user application intent and progress for recommended jobs.

Important fields:

- `job_listing_id`
- `job_analysis_id`
- `generated_resume_id`
- `status`
- `follow_up_date`
- `notes`

Statuses include:

- `planned`
- `applied`
- `interviewing`
- `rejected`
- `offer`
- `archived`

### ProofPoint

Stores reusable achievement evidence for future resume tailoring.

Important fields:

- `profile_id`
- `title`
- `context`
- `metrics`
- `skills`
- `tags`
- STAR fields: `situation`, `task`, `action`, `result`

The first implementation exposes CRUD APIs. Tailoring now selects relevant
profile/global proof points for needs-tailoring jobs, injects them into the
tailor prompt as supplemental evidence, and stores selected IDs on
`GeneratedResume.proof_point_ids`.

## Main User Flows

### 1. Manage Profiles

The user can create, edit, delete, upload, and set default profiles. Profiles
can include free-form text and structured profile JSON.

### 2. Evaluate A JD

Input:

- profile ID or default profile
- JD text
- prompt version
- configured LLM backend/model

Output:

- score `0..100`
- explanation
- strengths
- gaps
- `tailoring_job_id` and `tailoring_status` when tailoring is queued

`POST /api/evaluate` is synchronous by default. Async single-JD evaluation is
available through `POST /api/evaluate/jobs`; `POST /api/evaluate?async=true` is
an alias for the same durable job path. Both async entry points create an
`ai_jobs` row with `kind=evaluate` and return HTTP 202 with the same job
envelope returned by `GET /api/jobs/{job_id}`.

State routing:

| Score | Status | Behavior |
|-------|--------|----------|
| 85-100 | `ready_to_submit` | Mark as potentially ready. |
| 60-84 | `needs_tailoring` | Queue durable tailoring and return job status metadata. |
| 0-59 | `skip` | Keep result with skip reason. |

The LLM provides the score and explanation. Application code owns the status
routing.

### 3. Scrape Job Listings

Supported source selectors:

- `104`
- `yourator`
- `linkedin`
- `all` = 104 + Yourator
- `all_with_linkedin` = 104 + Yourator + LinkedIn

Scrapers can run through:

- API
- Scrapes UI
- CLI
- cron wrapper

The UI supports:

- keyword/source/limit controls
- active scrape status
- stop current runs
- stop and run a new keyword
- optional evaluate-after-scrape

### 4. Evaluate Stored Listings

Stored listings can be batch evaluated. Recommended jobs then surface in the
opportunities/application views.

### 5. Tailor And Review Resume

For `needs_tailoring`, the system generates a tailored resume draft. The user
must review the output before submitting to any platform.

Tailoring is represented as durable job state. Evaluate/history responses expose
`tailoring_job_id` and `tailoring_status`. The frontend polls
`GET /api/jobs/{job_id}` until the job reaches `succeeded`, `failed`, or
`cancelled`. On `succeeded`, the frontend reloads
`GET /api/history/{job_analysis_id}` to fetch the generated resume. On
`failed` or `cancelled`, the UI shows the readable job error state and leaves
the history fallback available for responses that do not include a durable job
ID.

Tailoring must use baseline profile and structured data as source of truth.
Proof points are available as a managed evidence library and should become an
additional authoritative source once retrieval is connected to the tailoring
prompt.

### 6. Track Applications

The user can add promising listings to the application tracker and update
status/follow-up information.

The tracker is a user-owned pipeline, not an automated submission system. It
records intent and progress after a listing has been evaluated, reviewed as an
opportunity, or linked to a generated resume. Opportunities and Applications
live on separate pages: Opportunities (`/opportunities.html`) is the review
queue of high-fit untracked JDs; Applications (`/applications.html`) is the
downstream tracker for jobs the user chooses to act on. Duplicate tracking
requests for the same listing or analysis should return the existing
application row and may update status, notes, or follow-up date.

## LLM Flow And Spec Requirements

### Evaluate Contract

Input spec:

- baseline profile text
- JD text
- prompt version

Expected output:

```json
{
  "score": 75,
  "explanation": "Short assessment.",
  "strengths": ["Relevant backend experience"],
  "gaps": ["Missing explicit cloud requirement"]
}
```

Validation requirements:

- `score` must be integer `0..100`
- `explanation` must be non-empty and bounded
- `strengths` must be `list[str]`
- `gaps` must be `list[str]`
- invalid output fails closed with `llm_invalid_output`

### Tailor Contract

Input spec:

- baseline profile text
- optional structured profile data
- JD text
- score
- gaps

Expected output:

```json
{
  "tailoring_suggestions": ["Relevant source-preserving edits"],
  "tailored_resume": "Markdown resume text"
}
```

Validation requirements:

- output is non-empty
- output is JSON with no unexpected fields
- `tailored_resume` is non-empty and bounded
- `tailored_resume` has no code fence or assistant preamble
- `tailoring_suggestions` is a bounded `list[str]`
- no invented employer/date/metric/certification/degree/skill
- key baseline facts are preserved

### Durable AI Job Contract

`POST /api/evaluate` returns `tailoring_job_id` and `tailoring_status` when a
`needs_tailoring` analysis queues resume generation. `GET /api/history` and
`GET /api/history/{job_analysis_id}` also expose the latest tailoring job
metadata for the analysis.

`POST /api/evaluate/jobs` creates a durable `kind=evaluate` job. `POST
/api/evaluate?async=true` is an alias. Successful evaluate jobs return
`result_payload` with:

- `cached`
- `job_analysis_id`
- `tailoring_job_id`
- `tailoring_status`
- `evaluation` matching the synchronous `EvaluateOut` response shape

If `evaluation.status` is `needs_tailoring`, the evaluate worker may enqueue a
durable `kind=tailor` job after evaluation completes.

`GET /api/jobs/{job_id}` returns:

- job identity, `kind`, and `job_analysis_id`
- `status`: `queued`, `running`, `succeeded`, `failed`, or `cancelled`
- `result_payload` for successful job metadata
- `error_code` and `error_message` for failed jobs
- progress fields suitable for simple polling UI text

Clients treat only `succeeded`, `failed`, and `cancelled` as terminal.

### Structured Extraction Contract

Input spec:

- profile source text

Expected output:

Known top-level profile JSON keys:

- `personal`
- `summary`
- `work_experience`
- `education`
- `languages`
- `certifications`
- `skills`
- `personal_qualities`

Validation requirements:

- object shape is known
- unknown top-level or nested keys are rejected
- blank string values are rejected
- source facts are not invented

### Beautify Contract

Input spec:

- generated resume Markdown
- style preset

Expected output:

- self-contained HTML document
- no scripts
- no external resources
- no markdown code fences or assistant preambles
- source facts preserved
- known hallucinated facts rejected when absent from source Markdown

## Current Gaps

Tracked in high-priority issues:

- #113: eval harness and stricter output constraints
- #114: AI engineering production maturity checklist
- #115: docs refresh

Known gaps:

- Deeper source-fact validation is incomplete outside the current contract and
  fixture checks.
- Tailoring factuality has a deterministic smoke harness; broader fixture
  coverage is still needed.
- Durable AI job state is specified for #71; backend queue hardening must
  preserve restart-safe status transitions and progress reporting for both
  tailoring and async single-JD evaluate jobs.
- CI eval reports cover deterministic evaluate, tailor, structured extraction,
  and beautify fixtures.
- Audit logs capture prompt/model metadata for production LLM calls, but there
  is no user-facing audit browser yet.

## Non-Goals For Current Scope

- Fully autonomous job application submission.
- Multi-user account system.
- Browser automation against employer portals.
- Replacing human review for resume/PDF output.

## Human Review Policy

The app may recommend applying, generate tailored materials, and provide source
links. It must not submit applications automatically without explicit user
review and action.
