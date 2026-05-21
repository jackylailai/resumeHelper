# Data Model

**Scope**: historical Phase 1 model plus current single-user product deltas.
The current product reference is `specs/current-product-spec.md`.
**Authoritative source**: `backend/app/models/` and `backend/alembic/versions/`.

---

## Current Core Tables

### `baseline_profile`

Stores resume/profile source material. The app supports multiple profiles and
one default profile.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `name` | VARCHAR(255) NULL | Display name |
| `skills_text` | TEXT NOT NULL | Source resume/profile text |
| `structured_data` | JSONB NULL | Extracted structured profile data |
| `pdf_path` | TEXT NULL | Persisted source PDF path |
| `is_default` | BOOLEAN NOT NULL | Default profile fallback |
| `created_at` | TIMESTAMPTZ NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

### `job_analyses`

Stores the result of scoring one JD against one profile.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `profile_id` | INTEGER FK NULL | `baseline_profile.id`, SET NULL on profile delete |
| `jd_hash` | VARCHAR(64) | SHA-256 of canonicalized JD text |
| `jd_snippet` | TEXT | Short display text |
| `jd_full_text` | TEXT NOT NULL | Full JD used for tailoring |
| `score` | INTEGER | 0-100 |
| `explanation` | TEXT NULL | LLM explanation |
| `strengths` | JSONB NULL | Strength strings |
| `gaps` | JSONB NULL | Gap strings |
| `threshold_met` | BOOLEAN NOT NULL | Score >= configured threshold |
| `status` | VARCHAR(20) | `ready_to_submit`, `needs_tailoring`, `skip` |
| `can_submit` | BOOLEAN NOT NULL | True when reviewable material exists |
| `skip_reason` | TEXT NULL | Weak-fit reason |
| `prompt_version` | VARCHAR(64) NULL | Prompt version used for evaluation |
| `created_at` | TIMESTAMPTZ NOT NULL | |

Unique constraint: `(jd_hash, profile_id)`.

API responses for evaluate/history include the latest related
`tailoring_job_id` and `tailoring_status` when tailoring has been queued.

### `ai_jobs`

Stores durable state for AI work. The #71 backend slice uses `kind=tailor` for
resume tailoring work linked to a job analysis; later slices may use the same
table for asynchronous evaluation work.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | Public job ID returned to clients |
| `kind` | VARCHAR(40) | `tailor`, `evaluate`, `evaluate_bulk`, `evaluate_listing`, `evaluate_pending_listings` |
| `status` | VARCHAR(20) | `queued`, `running`, `retry_wait`, `cancel_requested`, `cancelled`, `succeeded`, `failed` |
| `parent_job_id` | UUID FK NULL | Optional parent `ai_jobs.id` for future batch jobs |
| `dedupe_key` | VARCHAR(255) NULL UNIQUE | Idempotency key, e.g. `tailor:{job_analysis_id}` |
| `priority` | INTEGER NOT NULL | Higher priority is claimed first |
| `run_after` | TIMESTAMPTZ NOT NULL | Earliest claim time for queue/retry |
| `attempts` | INTEGER NOT NULL | Worker attempts so far |
| `max_attempts` | INTEGER NOT NULL | Retry ceiling |
| `locked_by` | VARCHAR(128) NULL | Worker identifier when claimed |
| `locked_at` | TIMESTAMPTZ NULL | Claim timestamp |
| `job_analysis_id` | UUID FK NULL | Parent `job_analyses.id`, SET NULL |
| `profile_id` | INTEGER FK NULL | Related profile when applicable |
| `job_listing_id` | UUID FK NULL | Related listing when applicable |
| `generated_resume_id` | UUID FK NULL | Output resume for successful tailoring |
| `prompt_version` | VARCHAR(64) NULL | Prompt version used by the job |
| `request_id` | VARCHAR(64) NULL | API request correlation id |
| `input_payload` | JSONB NOT NULL | Durable job input metadata |
| `result_payload` | JSONB NULL | Successful job metadata |
| `error_code` | VARCHAR(64) NULL | Stable failure code |
| `error_message` | TEXT NULL | Readable failure message |
| `progress_current` | INTEGER NOT NULL | Completed step count |
| `progress_total` | INTEGER NULL | Optional total steps |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |
| `started_at` | TIMESTAMPTZ NULL | |
| `finished_at` | TIMESTAMPTZ NULL | |

Indexes:

- unique `dedupe_key` for idempotent tailoring enqueue.
- `(status, run_after, priority, created_at)` for worker pickup and operational views.
- `job_analysis_id`, `job_listing_id`, `profile_id`, `request_id`, and
  `generated_resume_id` for linking API responses and diagnostics.

### `generated_resumes`

Stores generated tailored resume content and PDF-related links.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `job_analysis_id` | UUID FK | CASCADE DELETE |
| `resume_text` | TEXT NOT NULL | Generated resume content |
| `pdf_url` | TEXT NULL | External URL or local `/api/generated-resumes/{id}/pdf` |
| `html_url` | TEXT NULL | Beautified HTML artifact when present |
| `latest_revision_id` | UUID NULL | Latest resume revision when present |
| `prompt_version` | VARCHAR(64) NULL | Prompt version tag |
| `proof_point_ids` | JSONB NOT NULL | Selected proof point UUID strings used as tailoring evidence |
| `created_at` | TIMESTAMPTZ NOT NULL | |

### `proof_points`

Stores reusable achievement evidence for tailoring. Rows can be profile-scoped
or global (`profile_id` is NULL).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `profile_id` | INTEGER FK NULL | `baseline_profile.id`, SET NULL on profile delete |
| `title` | VARCHAR(255) NOT NULL | Short achievement label |
| `context` | TEXT NULL | Project or role context |
| `metrics` | TEXT NULL | Quantified evidence |
| `skills` | JSONB NOT NULL | Skill terms |
| `tags` | JSONB NOT NULL | User tags |
| `situation` | TEXT NULL | STAR situation |
| `task` | TEXT NULL | STAR task |
| `action` | TEXT NULL | STAR action |
| `result` | TEXT NULL | STAR result |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

### `job_listings`

Stores scraped or imported job listings.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `source` | VARCHAR(32) NOT NULL | `104`, `yourator`, `linkedin`, etc. |
| `source_id` | VARCHAR(128) NOT NULL | Per-source stable ID |
| `title` | TEXT NOT NULL | |
| `company` | TEXT NOT NULL | |
| `location` | TEXT NULL | |
| `url` | TEXT NOT NULL | Source URL |
| `description` | TEXT NOT NULL | Full JD text |
| `raw_json` | JSONB NULL | Raw scraper payload |
| `scraped_at` | TIMESTAMPTZ NOT NULL | |
| `job_analysis_id` | UUID FK NULL | Linked evaluation, SET NULL |

Unique constraint: `(source, source_id)`.

### `applications`

Tracks user application intent and progress. This is a pipeline tracker, not an
automated submission table.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `job_listing_id` | UUID FK NULL | SET NULL |
| `job_analysis_id` | UUID FK NULL | SET NULL |
| `generated_resume_id` | UUID FK NULL | SET NULL |
| `status` | VARCHAR(20) NOT NULL | `planned`, `applied`, `interviewing`, `rejected`, `offer`, `archived` |
| `follow_up_date` | DATE NULL | |
| `notes` | TEXT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

### `scrape_runs`

Tracks scraper execution for API/UI/CLI/cron flows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `source` | VARCHAR | Requested source selector |
| `keyword` | TEXT | Search keyword |
| `status` | VARCHAR | `queued`, `running`, `cancel_requested`, `cancelled`, `succeeded`, `partial`, `failed` |
| `created_at` / `started_at` / `finished_at` | TIMESTAMPTZ NULL | Run timestamps |

---

## Supporting Tables

| Table | Purpose |
|-------|---------|
| `resume_beautifications` | HTML/PDF beautification output metadata |
| `generated_resume_revisions` | Reviewable revisions of generated resumes |

---

## Hashing

`jd_hash = SHA-256(canonicalize(jd_text))`

`canonicalize(text)`:

1. Unicode NFC normalization
2. Collapse whitespace runs to a single space
3. Strip leading/trailing whitespace

Implementation: `backend/app/services/hashing.py:jd_hash()`.

---

## Migrations

| Revision | File | Contents |
|----------|------|----------|
| `0001` | `0001_initial.py` | Empty baseline |
| `0002` | `0002_poc_schema.py` | `baseline_profile`, `job_analyses`, `generated_resumes` |
| `0003` | `0003_three_tier_fields.py` | Status, submit, explanation, strengths/gaps |
| `0004` | `0004_multi_profile.py` | Multi-profile fields and profile-scoped JD cache |
| `0005` | `0005_pdf_path.py` | Profile PDF path |
| `0006` | `0006_job_listings.py` | JD Database listings |
| `0007` | `0007_profile_default.py` | Default profile flag |
| `0008` | `0007_applications.py` | Application tracker table |
| `0009` | `0009_resume_beautification.py` | Beautification artifacts |
| `0010` | `0010_baseline_structured_data.py` | Structured profile data |
| `0011` | `0011_scrape_runs.py` | Scrape run tracking |
| `0012` | `0012_generated_resume_revisions.py` | Resume revisions |
| `0013` | `0013_scrape_run_cancellation.py` | Scrape cancellation state |
| `0019` | `0019_proof_points.py` | Proof point library |
| `0020` | `0020_generated_resume_proof_points.py` | Generated resume proof point attribution |
| `0021` | `0021_ai_jobs.py` | Durable AI job queue state |

---

## Future Tables

| Table | Purpose |
|-------|---------|
| `users` | Multi-user support |
| `llm_audit_log` | Token cost, latency, and prompt/model tracing |
