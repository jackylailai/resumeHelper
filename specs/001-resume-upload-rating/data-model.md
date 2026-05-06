# Data Model

**Scope**: Phase 1 — single user, 3 tables.
**Authoritative source**: `backend/app/models/` and `backend/alembic/versions/`.

---

## Tables

### `baseline_profile`
One row. The user's raw skills/experience text. Upserted, never appended.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `skills_text` | TEXT NOT NULL | Full baseline resume / skills list |
| `updated_at` | TIMESTAMPTZ | Set on every upsert |

---

### `job_analyses`
One row per unique JD (deduplicated by `jd_hash`). Scoring done once per unique
JD; re-submitting the same JD skips the LLM call and returns `cached: true`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` |
| `jd_hash` | VARCHAR(64) UNIQUE | SHA-256 of `canonicalize(jd_text)` |
| `jd_snippet` | TEXT | First 200 chars — for history list display |
| `jd_full_text` | TEXT NOT NULL | Full JD — used during tailoring |
| `score` | INTEGER | 0–100, CHECK constraint |
| `explanation` | TEXT | Plain-language LLM explanation |
| `strengths` | JSONB | Array of strength strings |
| `gaps` | JSONB | Array of gap strings |
| `threshold_met` | BOOLEAN | true if score ≥ 60 |
| `status` | VARCHAR(20) | `ready_to_submit` / `needs_tailoring` / `skip` |
| `can_submit` | BOOLEAN | true when a generated resume is ready |
| `skip_reason` | TEXT | Populated when status=skip |
| `created_at` | TIMESTAMPTZ | |

Index: `(created_at DESC)` for history list.

---

### `generated_resumes`
Many per `job_analysis`. Each row is one LLM-generated tailored resume.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `job_analysis_id` | UUID FK → `job_analyses.id` CASCADE DELETE | |
| `resume_text` | TEXT NOT NULL | Markdown-formatted tailored resume |
| `pdf_url` | TEXT | null in Phase 1 (weasyprint not installed) |
| `prompt_version` | VARCHAR(64) | LLM prompt version tag |
| `created_at` | TIMESTAMPTZ | |

Index: `(job_analysis_id, created_at DESC)` — latest resume first per JD.

---

## Hashing

`jd_hash = SHA-256(canonicalize(jd_text))`

`canonicalize(text)`:
1. Unicode NFC normalisation
2. Collapse all whitespace runs to single space
3. Strip leading/trailing whitespace

Implementation: `backend/app/services/hashing.py:jd_hash()`

---

## Three-Tier Thresholds

| Constant | Value | Meaning |
|----------|-------|---------|
| `THRESHOLD_HIGH` | 85 | score ≥ 85 → `ready_to_submit` |
| `THRESHOLD_MID` | 60 | 60 ≤ score < 85 → `needs_tailoring` |
| below mid | — | score < 60 → `skip` |

Source: `backend/app/models/job_analysis.py`

---

## Migrations

| File | Contents |
|------|---------|
| `0001_initial.py` | Empty baseline (pre-POC) |
| `0002_poc_schema.py` | `baseline_profile`, `job_analyses`, `generated_resumes` |
| `0003_three_tier_fields.py` | `status`, `can_submit`, `skip_reason`, `explanation`, `strengths`, `gaps` on `job_analyses` |

---

## Future Tables (Phase 3+)

| Table | Purpose |
|-------|---------|
| `users` | Multi-user support |
| `llm_audit_log` | Token cost / latency tracking per call |
