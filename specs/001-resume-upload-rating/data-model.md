# Data Model

**Scope**: Single-user app with profiles, JD analyses, generated resumes,
stored job listings, and application tracking.
**Authoritative source**: `backend/app/models/` and `backend/alembic/versions/`.

---

## Tables

### `baseline_profile`

Resume/profile library. The first profile is default by default; only one row
should have `is_default=true`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `name` | VARCHAR(255) NULL | Display name |
| `skills_text` | TEXT NOT NULL | Baseline resume / skills text |
| `pdf_path` | TEXT NULL | Absolute path to uploaded source PDF |
| `is_default` | BOOLEAN NOT NULL | Preferred profile for omitted `profile_id` |
| `created_at` | TIMESTAMPTZ NULL | Added by multi-profile migration |
| `updated_at` | TIMESTAMPTZ NOT NULL | Updated on profile edits/default promotion |

### `job_analyses`

One row per unique `(jd_hash, profile_id)` evaluation.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `profile_id` | INTEGER FK NULL | `baseline_profile.id`, SET NULL on delete |
| `jd_hash` | VARCHAR(64) | SHA-256 of canonicalized JD text |
| `jd_snippet` | TEXT | First 200 chars for list display |
| `jd_full_text` | TEXT NOT NULL | Full JD used for tailoring |
| `score` | INTEGER | 0-100 |
| `explanation` | TEXT NULL | LLM explanation |
| `strengths` | JSONB NULL | Strength strings |
| `gaps` | JSONB NULL | Gap strings |
| `threshold_met` | BOOLEAN NOT NULL | true if score >= threshold |
| `status` | VARCHAR(20) | `ready_to_submit` / `needs_tailoring` / `skip` |
| `can_submit` | BOOLEAN NOT NULL | true when a generated resume is available |
| `skip_reason` | TEXT NULL | Populated for weak-fit rows |
| `created_at` | TIMESTAMPTZ NOT NULL | |

Unique constraint: `(jd_hash, profile_id)`.

### `generated_resumes`

Many per `job_analyses` row.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `job_analysis_id` | UUID FK | CASCADE DELETE |
| `resume_text` | TEXT NOT NULL | Tailored resume content |
| `pdf_url` | TEXT NULL | Local `/api/generated-resumes/{id}/pdf` or external URL |
| `prompt_version` | VARCHAR(64) NULL | LLM prompt version tag |
| `created_at` | TIMESTAMPTZ NOT NULL | |

### `job_listings`

Stored scraped JD rows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `source` | VARCHAR(32) NOT NULL | e.g. `104`, `yourator` |
| `source_id` | VARCHAR(128) NOT NULL | Per-source stable ID |
| `title` | TEXT NOT NULL | |
| `company` | TEXT NOT NULL | |
| `location` | TEXT NULL | |
| `url` | TEXT NOT NULL | Source URL |
| `description` | TEXT NOT NULL | Full JD text |
| `raw_json` | JSONB NULL | Raw scraper payload |
| `scraped_at` | TIMESTAMPTZ NOT NULL | |
| `job_analysis_id` | UUID FK NULL | SET NULL |

Unique constraint: `(source, source_id)`.

### `applications`

Tracked opportunities linked to a listing, analysis, and/or generated resume.

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
| `updated_at` | TIMESTAMPTZ NOT NULL | SQLAlchemy `onupdate` |

---

## Hashing

`jd_hash = SHA-256(canonicalize(jd_text))`

`canonicalize(text)`:

1. Unicode NFC normalization
2. Collapse whitespace runs to a single space
3. Strip leading/trailing whitespace

Implementation: `backend/app/services/hashing.py:jd_hash()`.

---

## Thresholds

| Constant | Value | Meaning |
|----------|-------|---------|
| `THRESHOLD_HIGH` | 85 | `ready_to_submit` |
| `THRESHOLD_MID` | 60 | `needs_tailoring` |
| below mid | <60 | `skip` |

Source: `backend/app/models/job_analysis.py`.

---

## Migrations

| File | Contents |
|------|----------|
| `0001_initial.py` | Empty baseline |
| `0002_poc_schema.py` | `baseline_profile`, `job_analyses`, `generated_resumes` |
| `0003_three_tier_fields.py` | Status, submit, explanation, strengths/gaps fields |
| `0004_multi_profile.py` | Multi-profile fields and `(jd_hash, profile_id)` uniqueness |
| `0005_pdf_path.py` | `baseline_profile.pdf_path` |
| `0006_job_listings.py` | `job_listings` |
| `0007_default_profile.py` | `baseline_profile.is_default` |
| `0008_applications.py` | `applications` |

---

## Future Tables

| Table | Purpose |
|-------|---------|
| `users` | Multi-user support |
| `llm_audit_log` | Token cost and latency tracing |
