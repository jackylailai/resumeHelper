# Feature Specification: Resume Fit Evaluator

**Feature Branch**: `001-resume-upload-rating`
**Updated**: 2026-05-11 (rev 5)
**Status**: Phase 2.5 implementation in progress
**Authoritative direction**: multi-profile CRUD with default profile, profile-scoped evaluation, JD Database, application tracker, generated PDF download, and production readiness checks.

## Overview

A single-user tool that evaluates job descriptions against saved resume
profiles, scores them on a 0-100 scale, generates tailored resumes for good
matches, and tracks the application pipeline from planned through offer.

## Three-Tier Scoring Logic

| Score | Status | Action |
|-------|--------|--------|
| 85-100 | `ready_to_submit` | Return immediately; no tailoring needed |
| 60-84 | `needs_tailoring` | Trigger background tailoring |
| 0-59 | `skip` | Return immediately with a skip reason |

## User Stories

### Story 1 - Manage Baseline Profiles

A user maintains a library of resume profiles, such as one per job family. Each
profile has optional `name`, `skills_text`, persisted PDF path when created from
upload, and `is_default`.

**Acceptance Scenarios**:

1. `POST /api/profiles` with `skills_text`, optional `name`, and optional `is_default` creates a profile.
2. `GET /api/profiles` returns all profiles ordered with the default first.
3. `PUT /api/profiles/{id}` updates `skills_text`, `name`, and/or `is_default`.
4. Setting one profile as default clears the default flag from the others.
5. Creating the first profile makes it default automatically.
6. Deleting the default profile promotes the newest remaining profile.
7. `POST /api/profiles/upload/preview` extracts PDF text without creating a profile.
8. `POST /api/profiles/upload` accepts PDF plus optional reviewed `skills_text`, persists original bytes under `${STORAGE_DIR}/profiles/<profile_id>/<utc-timestamp>.pdf`, and saves `pdf_path`.
9. `GET /api/profiles/{id}/delete-impact` reports related job analysis and generated resume counts before delete.
10. Legacy `/api/profile` endpoints remain for compatibility and use the default profile fallback.

### Story 2 - Evaluate a Job Description

A user submits a job description and optionally selects a profile. The cache is
scoped to `(jd_hash, profile_id)` so the same JD can be evaluated independently
against different profiles.

**Acceptance Scenarios**:

1. `POST /api/evaluate` returns `score`, `status`, `strengths`, `gaps`, `message`, and `action`.
2. If `profile_id` is provided, that profile is used.
3. If `profile_id` is omitted, the default profile is used, falling back to latest profile.
4. Same JD + same profile returns `meta.cached=true` on repeat submission.
5. Same JD + different profile is not a cache hit.
6. No usable profile returns `404 not_found`.
7. Oversized JD text returns `400 jd_too_long`.
8. LLM unavailable/invalid output maps to `503 llm_unavailable` or `502 llm_invalid_output`.

### Story 3 - Bulk and Stored Listing Evaluation

A user scores several JDs at once or scores selected rows from the JD Database.

**Acceptance Scenarios**:

1. `POST /api/evaluate/bulk` accepts 1-100 JD texts and returns totals for `new`, `cached`, and `total`.
2. Duplicate JD texts in the same batch dedupe by content hash.
3. `POST /api/evaluate/by-listings` accepts up to 20 `job_listing_ids`, evaluates valid listings, links each successful `JobListing.job_analysis_id`, and returns per-row errors for invalid/missing listings.
4. `needs_tailoring` results queue background tailoring once for fresh evaluations.

### Story 4 - View History, Submittable Resumes, and PDFs

A user reviews scored JDs and generated resumes.

**Acceptance Scenarios**:

1. `GET /api/history` returns job analyses in reverse chronological order and grouped status metadata.
2. `GET /api/history/{id}` returns full JD text and generated resumes.
3. `GET /api/submittable` returns `can_submit=true` analyses with latest resume metadata.
4. `GET /api/generated-resumes/{id}/pdf` generates a local PDF on demand when missing and returns it as a file response.
5. `POST /api/callback` stores externally delivered resume text and preserves caller-supplied `pdf_url`; if absent, it generates a local PDF URL.

### Story 5 - Browse JD Database

A user browses stored scraped job listings before scoring.

**Acceptance Scenarios**:

1. `GET /api/job-listings` supports search, source filter, analyzed/status filter, sorting, pagination, and score-aware rows.
2. `GET /api/job-listings/{id}` returns the full description and raw JSON.
3. The UI can select a page of listings, score selected rows, score a pasted JD, and refresh row status.
4. A scored listing can be added to the application tracker.

### Story 6 - Track Applications

A user tracks applications created from scored listings or linked analyses.

**Acceptance Scenarios**:

1. `POST /api/applications` requires at least one of `job_listing_id`, `job_analysis_id`, or `generated_resume_id`.
2. Creating an application hydrates company/title/source URL/score/PDF URL from linked records when available.
3. Duplicate creates for the same listing or analysis return the existing row with `meta.existing=true` and update supplied status/follow-up/notes.
4. `GET /api/applications` supports `q`, `status`, `sort_by`, `sort_dir`, `limit`, and `offset`.
5. `PATCH /api/applications/{id}` updates `status`, `follow_up_date`, and/or `notes`.
6. Allowed statuses are `planned`, `applied`, `interviewing`, `rejected`, `offer`, and `archived`.

### Story 7 - Operability and Guardrails

The app remains locally friendly but can run behind a production reverse proxy.

**Acceptance Scenarios**:

1. `GET /api/health` returns checks, counts, liveness, readiness, `can_evaluate`, and next actions.
2. `GET /api/health/live` returns process liveness.
3. `GET /api/health/ready` returns HTTP 503 when DB or required LLM config is not ready.
4. Production config rejects wildcard CORS.
5. Optional write auth protects non-GET `/api/*` routes with bearer token or basic auth.
6. Every response carries `X-Request-ID`; error envelopes include request context for debugging.

## Functional Requirements

- **FR-001**: System MUST support multiple baseline profiles with full CRUD and one default profile.
- **FR-002**: System MUST support profile creation from raw text, PDF preview, and PDF upload with optional reviewed text override.
- **FR-003**: System MUST deduplicate evaluations by SHA-256 hash of canonicalized JD text scoped to `(jd_hash, profile_id)`.
- **FR-004**: System MUST score each JD 0-100 and classify it as `ready_to_submit`, `needs_tailoring`, or `skip`.
- **FR-005**: System MUST trigger background tailoring for fresh `needs_tailoring` jobs using the profile tied to the analysis.
- **FR-006**: System MUST store generated resumes per job analysis with prompt version and PDF URL.
- **FR-007**: System MUST expose history, submittable list, and generated PDF download.
- **FR-008**: System MUST accept external resume delivery via `POST /api/callback`.
- **FR-009**: System MUST accept bulk JD evaluation and stored listing evaluation.
- **FR-010**: System MUST expose stored JD listings with filters, pagination, and analysis status.
- **FR-011**: System MUST expose an application tracker with create/list/update behavior.
- **FR-012**: System MUST expose liveness/readiness health checks.
- **FR-013**: System MUST reject wildcard CORS in production mode.
- **FR-014**: System MAY protect write operations with management auth.
- **FR-015**: Multi-user accounts, async job polling, and resume version comparison remain out of scope.

## Key Entities

- **BaselineProfile**: `id`, `name`, `skills_text`, `pdf_path`, `is_default`, `created_at`, `updated_at`.
- **JobAnalysis**: one row per `(jd_hash, profile_id)` pair. Stores JD text, score, status, strengths, gaps, skip reason, `can_submit`, and `profile_id` FK.
- **GeneratedResume**: many per JobAnalysis. Stores resume text, prompt version, and generated or external PDF URL.
- **JobListing**: one row per scraped JD. Unique by `(source, source_id)` and optionally linked to `job_analysis_id`.
- **Application**: tracked opportunity linked to a listing, analysis, and/or generated resume; stores status, follow-up date, notes, and timestamps.

## Success Criteria

- **SC-001**: Evaluate a single JD in under 30 seconds under normal LLM conditions.
- **SC-002**: Duplicate JD+profile submission returns cached result in under 1 second.
- **SC-003**: `needs_tailoring` jobs produce a generated resume without blocking the HTTP response.
- **SC-004**: History and submittable views show correct status and latest resume/PDF metadata.
- **SC-005**: JD Database batch scoring links successful listings to analyses and reports row-level failures.
- **SC-006**: Application tracker can create, filter, sort, and update tracked opportunities.
- **SC-007**: Readiness endpoint reports dependency/config failure with HTTP 503.

## Out of Scope

- Multi-user authentication/account model
- Celery/Redis async queue and job polling API
- Resume version comparison UI
- LinkedIn scraper completion
- Cloud blob storage for PDFs
