# Feature Specification: Resume Fit Evaluator

> Historical note: this document describes the original Phase 1 evaluator scope.
> The current product has grown to include JD scraping, a JD database, scrape
> scheduling, generated resume/PDF review, job opportunities, and application
> tracking. Use `specs/current-product-spec.md` as the current product spec.
> The sibling `data-model.md` and `contracts/openapi.yaml` files include current
> implementation deltas where useful for API/model traceability.

**Feature Branch**: `001-resume-upload-rating`
**Updated**: 2026-05-21 (rev 6)
**Status**: Phase 1 (implemented)
**Authoritative direction**: multi-profile CRUD + profile-scoped evaluation; uploaded PDFs persisted on disk; v1 dead code removed; Python 3.11 floor

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

### Story 1 — Manage Baseline Profiles (P1)

A user maintains a library of resume profiles (e.g., one per job family). Each
profile has a name and skills text extracted from a PDF. Profiles can be created,
listed, updated, and deleted. The legacy `/api/profile` singular endpoint is
preserved for backward compatibility.

**Acceptance Scenarios**:

1. **Given** a POST to `/api/profiles` with `skills_text` (and optional `name`), **Then** a new profile row is created and returned.
2. **Given** a GET to `/api/profiles`, **Then** all profiles are returned as a list (empty list if none).
3. **Given** a GET to `/api/profiles/{id}` for a valid ID, **Then** that profile is returned.
4. **Given** a GET to `/api/profiles/{id}` for a non-existent ID, **Then** a 404 is returned.
5. **Given** a PUT to `/api/profiles/{id}`, **Then** the profile's `skills_text` and/or `name` are updated.
6. **Given** a DELETE to `/api/profiles/{id}`, **Then** the profile is removed; a subsequent GET returns 404.
7. **Given** a POST to `/api/profiles/upload` with a PDF file (multipart) and optional `name`, **Then** text is extracted server-side (via pypdf), NUL bytes stripped, and a new profile is created.
8. **Given** `skills_text` contains NUL (`\x00`) bytes, **Then** they are silently stripped before persistence — no 500 crash.
9. **Given** a POST to the legacy `/api/profile`, **Then** a new profile row is created (same as `/api/profiles`).
10. **Given** a GET to the legacy `/api/profile`, **Then** the most recently created profile is returned.
11. **Given** a POST to `/api/profiles/upload`, **Then** the original PDF bytes are written to `${STORAGE_DIR}/profiles/<profile_id>/<utc-timestamp>.pdf` and the absolute path is returned on the response as `pdf_path` and saved on `baseline_profile.pdf_path`.

---

### Story 2 — Evaluate a Job Description (P1)

A user submits a job description and optionally selects which profile to
evaluate against. The system scores it and classifies the result into one
of three tiers. The cache is scoped to `(jd_hash, profile_id)` so the same
JD evaluated against different profiles produces independent results.

**Acceptance Scenarios**:

1. **Given** a profile exists and a POST to `/api/evaluate` with `jd_text`, **Then** the response includes `score`, `status`, `strengths`, `gaps`, and a human-readable `message`.
2. **Given** `profile_id` is specified in the request, **Then** that profile is used for evaluation.
3. **Given** `profile_id` is omitted, **Then** the most recently created profile is used.
4. **Given** the same JD + same `profile_id` is submitted twice, **Then** the second response has `cached: true` in `meta`.
5. **Given** the same JD is submitted with two different `profile_id` values, **Then** each produces an independent result — the second is NOT a cache hit.
6. **Given** no profile exists, **Then** a 404 with code `not_found` is returned.
7. **Given** `jd_text` is omitted, **Then** a 422 validation error is returned.
8. **Given** a score of 85+, **Then** `status` is `ready_to_submit` and no background tailoring is triggered.
9. **Given** a score of 60–84, **Then** `status` is `needs_tailoring` and a background tailoring task is enqueued using the profile that was used for scoring.
10. **Given** relevant proof points exist for the selected profile or globally, **Then** tailoring may use those proof points as supplemental source evidence and the generated resume records the selected proof point IDs.
11. **Given** a score below 60, **Then** `status` is `skip` and `skip_reason` explains why the job is a poor fit.

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

- **FR-001**: System MUST support multiple baseline profiles with full CRUD (`GET/POST/PUT/DELETE /api/profiles`); legacy `/api/profile` singular endpoints preserved for backward compatibility.
- **FR-002**: System MUST accept profile creation via raw text (`POST /api/profiles`) or PDF upload (`POST /api/profiles/upload`); NUL bytes are stripped before storage.
- **FR-003**: System MUST deduplicate JDs by SHA-256 hash of canonicalized text scoped to `(jd_hash, profile_id)`; re-submitting the same JD+profile combination skips the LLM call.
- **FR-004**: System MUST score each JD 0–100 and classify it into one of three tiers: `ready_to_submit`, `needs_tailoring`, or `skip`.
- **FR-005**: System MUST trigger background tailoring for `needs_tailoring` jobs using the specific profile used at evaluation time (stored as `profile_id` on `JobAnalysis`).
- **FR-006**: System MUST store generated resumes per job analysis with the LLM prompt version and selected proof point IDs.
- **FR-007**: System MUST expose history (all evaluations) and a submittable list (can_submit=true with resume attached).
- **FR-008**: System MUST accept external resume delivery via POST `/api/callback` (e.g., from n8n or a CI pipeline).
- **FR-009**: System MUST accept bulk JD evaluation (list of texts) in a single request, deduplicated and summarized.
- **FR-010**: No authentication or multi-user support required. Single-user tool.
- **FR-011**: PDF generation is out of scope for Phase 1; `pdf_url` is null.
- **FR-012**: System MUST persist uploaded profile PDFs on local disk and store the absolute path on `baseline_profile.pdf_path`. Path scheme is `${STORAGE_DIR}/profiles/<profile_id>/<utc-timestamp>.pdf`. Multiple uploads against the same profile accumulate as separate timestamped files; the latest path is what lives on the row. S3 is deferred to a later phase — column type is plain TEXT so the migration is path-scheme-only.
- **FR-013** (Phase 2.5): Scrape endpoints (`POST /api/scrape/run`, `POST /api/scrape/control/start`) and the CLI `scrape` command MUST accept an optional `must_contain` list of terms with `match_mode` (`all` | `any`) and `regex` flag. When set, listings whose JD `description` does not match are dropped after `fetch_detail()` and counted on `ScrapeRun.skipped_by_filter`; the pipeline over-fetches up to `min(limit * 3, 200)` candidates from the source to satisfy `limit` matches when possible. Default (`must_contain` unset) preserves prior behaviour.

## Key Entities

- **BaselineProfile**: Many rows. `id`, `name` (optional), `skills_text` (TEXT), `pdf_path` (TEXT, optional — set when created via PDF upload), `created_at`, `updated_at`. Created via POST; no upsert — each call creates a new row.
- **JobAnalysis**: One row per unique `(jd_hash, profile_id)` pair. Stores score, status, strengths, gaps, can_submit, skip_reason, `profile_id` FK (SET NULL on profile delete).
- **GeneratedResume**: Many per JobAnalysis. `resume_text`, `pdf_url`, `prompt_version`, `proof_point_ids`.
- **ProofPoint**: User-maintained achievement evidence. May be linked to one profile or global; includes title, context, metrics, skills, tags, and STAR fields. Relevant proof points can be selected for tailoring prompts.
- **JobListing** (Phase 2.5): One row per scraped JD. `source` (`104`/`yourator`/`linkedin`), `source_id` (per-platform job id), `title`, `company`, `location`, `url`, `description` (full JD), `raw_json`, `scraped_at`, `job_analysis_id` FK (SET NULL). Unique on `(source, source_id)`.

## Success Criteria

- **SC-001**: Evaluate a JD in under 30 s under normal conditions.
- **SC-002**: Duplicate JD submission returns cached result in under 1 s.
- **SC-003**: `needs_tailoring` jobs produce a generated resume in the background without blocking the HTTP response, with selected proof point attribution when proof points were used.
- **SC-004**: All evaluated JDs visible in history with correct status.
- **SC-005**: Submittable list shows only `can_submit=true` jobs with resume text.
- **SC-006** (Phase 2.5): A single CLI run scrapes ~100 JDs across 104 / Yourator / LinkedIn into `job_listings`, deduped by `(source, source_id)`.
- **SC-007** (Phase 2.5): Each scraped JobListing produces exactly one JobAnalysis (via the existing three-tier evaluator) and `needs_tailoring` rows trigger background tailoring without manual intervention.

## Out of Scope (Phase 1)

- Resume versioning
- Async job polling (`job_id`)
- Compare endpoint
- Multi-user authentication
- PDF generation (weasyprint not installed)
- Real crawler / n8n ingestion (stubs exist for callback)
