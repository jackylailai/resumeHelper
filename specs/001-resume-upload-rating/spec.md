# Feature Specification: Resume Fit Evaluator

**Feature Branch**: `001-resume-upload-rating`
**Updated**: 2026-05-06 (rev 2)
**Status**: Phase 1 (implemented)
**Authoritative direction**: `feat/e2e-ui` three-tier evaluation flow

## Overview

A single-user tool that evaluates job descriptions against a saved baseline
resume profile and scores them on a 0–100 scale. Jobs are classified into
three tiers that determine the next action automatically.

## Three-Tier Scoring Logic

| Score | Status | Action |
|-------|--------|--------|
| 85–100 | `ready_to_submit` | Return immediately — no tailoring needed |
| 60–84 | `needs_tailoring` | Trigger background tailoring via Claude API |
| 0–59 | `skip` | Return immediately with a skip reason |

## User Stories

### Story 1 — Set Up Baseline Profile (P1)

A user saves their resume as the baseline profile via PDF upload or raw text.
All JD evaluations compare against this profile.

**Acceptance Scenarios**:

1. **Given** a POST to `/api/profile` with `skills_text`, **Then** the profile is
   saved (upserted) and the full profile is returned.
2. **Given** a second POST to `/api/profile`, **Then** the previous profile is
   replaced — there is only ever one baseline.
3. **Given** a GET to `/api/profile` before any profile exists, **Then** a 404
   with code `not_found` is returned.
4. **Given** a POST to `/api/profile/upload` with a PDF file (multipart), **Then**
   text is extracted server-side (via pypdf), NUL bytes stripped, and the profile
   is upserted identically to scenario 1.
5. **Given** `skills_text` contains NUL (`\x00`) bytes, **Then** they are silently
   stripped before persistence — no 500 crash.

---

### Story 2 — Evaluate a Job Description (P1)

A user submits a job description. The system scores it against the baseline
and classifies the result into one of the three tiers.

**Acceptance Scenarios**:

1. **Given** a baseline profile exists and a POST to `/api/evaluate` with
   `jd_text`, **Then** the response includes `score`, `status`, `strengths`,
   `gaps`, and a human-readable `message`.
2. **Given** the same JD is submitted twice, **Then** the second response has
   `cached: true` in `meta` and the LLM is not called again.
3. **Given** no baseline profile exists, **Then** a 404 with code `not_found`
   is returned.
4. **Given** `jd_text` is omitted, **Then** a 422 validation error is returned.
5. **Given** a score of 85+, **Then** `status` is `ready_to_submit` and no
   background tailoring is triggered.
6. **Given** a score of 60–84, **Then** `status` is `needs_tailoring` and a
   background tailoring task is enqueued using the saved baseline profile.
7. **Given** a score below 60, **Then** `status` is `skip` and `skip_reason`
   explains why the job is a poor fit.

---

### Story 3 — Bulk Evaluate Multiple JDs (P2)

A user submits multiple JDs in one request. The system evaluates each,
deduplicates by content hash, and returns a summary.

**Acceptance Scenarios**:

1. **Given** a list of JD texts, **Then** each is scored and the response
   includes per-JD results plus totals for `new`, `cached`, and `total`.
2. **Given** duplicate JD texts in the batch, **Then** only one LLM call is
   made per unique JD — subsequent duplicates return `cached: true`.
3. **Given** a `needs_tailoring` JD in the batch, **Then** a background
   tailoring task is triggered exactly once for that JD.

---

### Story 4 — View History and Submittable Resumes (P1)

A user reviews all evaluated JDs and sees which ones are ready to submit
(with generated resumes attached).

**Acceptance Scenarios**:

1. **Given** one or more evaluations exist, **Then** GET `/api/history` returns
   all job analyses in reverse-chronological order, grouped by status.
2. **Given** a job analysis ID, **Then** GET `/api/history/{id}` returns the
   full JD, score, status, and any generated resumes.
3. **Given** tailoring has completed for a JD, **Then** it appears in GET
   `/api/submittable` with `can_submit: true` and the resume text attached.

---

## Functional Requirements

- **FR-001**: System MUST accept and store a single baseline profile via raw text (`POST /api/profile`) or PDF upload (`POST /api/profile/upload`); NUL bytes are stripped before storage.
- **FR-002**: System MUST deduplicate JDs by SHA-256 hash of canonicalized text; re-submitting the same JD skips the LLM call.
- **FR-003**: System MUST score each JD 0–100 and classify it into one of three tiers: `ready_to_submit`, `needs_tailoring`, or `skip`.
- **FR-004**: System MUST trigger background tailoring for `needs_tailoring` jobs using the saved baseline profile text, not the JD.
- **FR-005**: System MUST store generated resumes per job analysis with the LLM prompt version.
- **FR-006**: System MUST expose history (all evaluations) and a submittable list (can_submit=true with resume attached).
- **FR-007**: System MUST accept external resume delivery via POST `/api/callback` (e.g., from n8n or a CI pipeline).
- **FR-008**: System MUST accept bulk JD evaluation (list of texts) in a single request, deduplicated and summarized.
- **FR-009**: No authentication or multi-user support required. Single-user tool.
- **FR-010**: PDF generation is out of scope for Phase 1; `pdf_url` is null.

## Key Entities

- **BaselineProfile**: One row. `skills_text` (TEXT). Upserted on each POST.
- **JobAnalysis**: One row per unique JD (`jd_hash` UNIQUE). Stores score, status, strengths, gaps, can_submit, skip_reason.
- **GeneratedResume**: Many per JobAnalysis. `resume_text`, `pdf_url` (null), `prompt_version`.

## Success Criteria

- **SC-001**: Evaluate a JD in under 30 s under normal conditions.
- **SC-002**: Duplicate JD submission returns cached result in under 1 s.
- **SC-003**: `needs_tailoring` jobs produce a generated resume in the background without blocking the HTTP response.
- **SC-004**: All evaluated JDs visible in history with correct status.
- **SC-005**: Submittable list shows only `can_submit=true` jobs with resume text.

## Out of Scope (Phase 1)

- Resume versioning
- Async job polling (`job_id`)
- Compare endpoint
- Multi-user authentication
- PDF generation (weasyprint not installed)
- Real crawler / n8n ingestion (stubs exist for callback)
