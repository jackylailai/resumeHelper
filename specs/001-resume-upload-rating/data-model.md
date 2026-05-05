# Data Model

**Scope**: Phase 1 POC — single user, 3 tables.
See `scope-correction.md` for what was cut and why.

---

## Tables

### `baseline_profile`
One row. The user's raw skills/experience text. Upserted, never appended.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `skills_text` | TEXT NOT NULL | Full baseline resume / skills list |
| `updated_at` | TIMESTAMPTZ | Updated on every upsert |

---

### `job_analyses`
One row per unique JD (deduplicated by `jd_hash`). Scoring done once;
same JD submitted again skips the LLM call.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` |
| `jd_hash` | VARCHAR(64) UNIQUE | SHA-256 of `canonicalize(jd_text)` |
| `jd_snippet` | TEXT | First 200 chars — history list display |
| `jd_full_text` | TEXT NOT NULL | Full JD — needed for re-generation |
| `score` | INTEGER | 0–100 CHECK constraint |
| `threshold_met` | BOOLEAN | true if score ≥ `RESUME_GEN_THRESHOLD` |
| `created_at` | TIMESTAMPTZ | |

Index: `(created_at DESC)` for history list.

---

### `generated_resumes`
Many per `job_analysis`. Each row is one LLM-generated resume for a JD.
Multiple rows exist when the user re-triggers generation after tweaking the n8n prompt.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `job_analysis_id` | UUID FK → `job_analyses.id` CASCADE DELETE | |
| `resume_text` | TEXT NOT NULL | Markdown-formatted resume |
| `prompt_version` | VARCHAR(64) | Maps to n8n workflow version tag |
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

## Future Tables (Phase 3, see `specs/roadmap.md`)

| Table | Purpose |
|-------|---------|
| `users` | Multi-user support |
| `celery_tasks` | Async job tracking (replace n8n callback) |
| `llm_audit_log` | Token cost / latency tracking per call |
