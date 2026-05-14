# Current Product Specification

**Status**: current main branch reference
**Updated**: 2026-05-11
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

State routing:

| Score | Status | Behavior |
|-------|--------|----------|
| 85-100 | `ready_to_submit` | Mark as potentially ready. |
| 60-84 | `needs_tailoring` | Queue or run tailoring. |
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

Tailoring must use baseline profile and structured data as source of truth.
Future proof point work (#77) should become an additional authoritative source.

### 6. Track Applications

The user can add promising listings to the application tracker and update
status/follow-up information.

The tracker is a user-owned pipeline, not an automated submission system. It
records intent and progress after a listing has been evaluated, reviewed as an
opportunity, or linked to a generated resume. Submittable is the upstream review
queue for strong matches and generated resumes; Applications is the downstream
tracker for jobs the user chooses to act on. Duplicate tracking requests for the
same listing or analysis should return the existing application row and may
update status, notes, or follow-up date.

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

### Structured Extraction Contract

Input spec:

- profile source text

Expected output:

- versioned structured profile JSON or Pydantic-compatible schema

Validation target:

- object shape is known
- unknown keys follow explicit policy
- source facts are not invented

### Beautify Contract

Input spec:

- generated resume Markdown
- style preset

Expected output:

- self-contained HTML document
- no scripts
- no external resources
- source facts preserved

## Current Gaps

Tracked in high-priority issues:

- #113: eval harness and stricter output constraints
- #114: AI engineering production maturity checklist
- #115: docs refresh

Known gaps:

- LLM output validation is incomplete outside evaluate and tailor checks.
- Tailoring factuality has a deterministic smoke harness; broader fixture
  coverage is still needed.
- Long-running work still relies partly on FastAPI BackgroundTasks.
- CI eval reports currently cover deterministic evaluate and tailor fixtures;
  extraction and beautify harnesses are still pending.
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
