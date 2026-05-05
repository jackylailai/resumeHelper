# Phase 1 Data Model: Resume Upload & Rating

All tables live in the default schema. Single-user mode means no `user_id`
column; if multi-user is introduced later, every table gains a non-null FK.

## Entity Overview

```
Resume ──< ResumeVersion ──< ResumeEvaluation
                  │
                  └─< EvaluationJob (1-1 with active or last evaluation)
```

- **Resume**: logical document the user maintains over time.
- **ResumeVersion**: one immutable upload (file + parsed text + hash).
- **ResumeEvaluation**: scored output for a (version, job_description) pair.
- **EvaluationJob**: lifecycle row driving async LLM evaluation.

## `resumes`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PK | `uuid7()` |
| `display_name` | `text` | not null | User-friendly label, default = first version's filename |
| `created_at` | `timestamptz` | not null, default `now()` | |
| `updated_at` | `timestamptz` | not null, default `now()` | Bumped when a new version is added |

## `resume_versions`

Immutable. One row per upload event.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PK | |
| `resume_id` | `uuid` | FK → `resumes.id`, not null, on delete cascade | |
| `version_number` | `int` | not null, unique with `resume_id` | Monotonic per resume, starts at 1 |
| `content_hash` | `char(64)` | not null, indexed | `sha256(canonical_text)` — used for dedupe (FR-008) |
| `file_hash` | `char(64)` | not null | `sha256(raw_bytes)` — distinct from `content_hash` to allow dedupe even if PDF metadata differs |
| `file_format` | `text` | not null, in (`pdf`, `docx`) | |
| `file_size_bytes` | `int` | not null, ≤ 10 485 760 | FR-002 enforced at API layer; check constraint defends against bypass |
| `storage_path` | `text` | not null | Relative to `STORAGE_DIR` |
| `parsed_text` | `text` | not null | Plain text extracted at upload time (FR-010) |
| `uploaded_at` | `timestamptz` | not null, default `now()` | |

**Indexes**: `(resume_id, version_number)` unique; `(content_hash)` for dedupe.

**Per-user version cap**: Edge case in spec sets a soft limit of 50 versions
per resume. Enforced at the service layer (oldest-first warning, hard reject
above cap). Not a DB constraint.

## `evaluation_cache`

Lookup table that satisfies the constitution's caching requirement without Redis.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `cache_key` | `char(64)` | PK | `sha256(content_hash || jd_hash || prompt_version)` |
| `evaluation_id` | `uuid` | FK → `resume_evaluations.id`, not null | |
| `created_at` | `timestamptz` | not null, default `now()` | |

A cache hit (FR-008, SC-006) returns the linked `ResumeEvaluation` directly.

## `resume_evaluations`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PK | |
| `resume_version_id` | `uuid` | FK → `resume_versions.id`, not null | |
| `job_description` | `text` | not null | The pasted JD (FR-011) |
| `jd_hash` | `char(64)` | not null, indexed | `sha256(canonical_jd)` |
| `score` | `smallint` | not null, check `0 <= score <= 100` | |
| `explanation` | `text` | not null | LLM prose |
| `strengths` | `jsonb` | not null, default `'[]'` | `string[]` |
| `gaps` | `jsonb` | not null, default `'[]'` | `string[]` |
| `prompt_version` | `text` | not null | e.g. `resume-fit-v1` |
| `model` | `text` | not null | e.g. `claude-sonnet-4-6` |
| `token_count_input` | `int` | nullable | For cost observability |
| `token_count_output` | `int` | nullable | |
| `latency_ms` | `int` | not null | End-to-end wall time |
| `created_at` | `timestamptz` | not null, default `now()` | |

**Indexes**: `(resume_version_id, created_at desc)` for history view (SC-005).

## `evaluation_jobs`

Drives the async lifecycle (FR-004, FR-009). State machine:

```
pending ──▶ running ──▶ succeeded
              │
              └─▶ failed
```

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PK | The `job_id` returned to clients |
| `resume_version_id` | `uuid` | FK → `resume_versions.id`, not null | |
| `jd_hash` | `char(64)` | not null | Lets a stale JD job be matched to a cached eval |
| `status` | `text` | not null, in (`pending`, `running`, `succeeded`, `failed`) | |
| `evaluation_id` | `uuid` | FK → `resume_evaluations.id`, nullable | Set on success |
| `failure_reason` | `text` | nullable | e.g. `worker_crashed`, `llm_unavailable`, `llm_invalid_score` |
| `created_at` | `timestamptz` | not null, default `now()` | |
| `started_at` | `timestamptz` | nullable | Set when status → `running` |
| `finished_at` | `timestamptz` | nullable | Set when status → `succeeded` or `failed` |

**Crash recovery**: on app startup, any row with `status='running'` is updated
to `failed` with `failure_reason='worker_crashed'`. Documented in research.md.

## State Vocabulary (UX consistency, Principle IV)

The tokens `pending`, `running`, `succeeded`, `failed` are the **only** values
used across:

- `evaluation_jobs.status`
- API response `meta.status`
- Future Discord agent replies

No surface-specific synonyms (`done`, `complete`, `error`) anywhere.

## Hashing Conventions

- `canonical_text` for `content_hash`: parsed plain text, NFC-normalized,
  whitespace-collapsed, trailing-trimmed. Defined in `services/hashing.py`.
- `canonical_jd`: same pipeline applied to the user-supplied JD.
- `cache_key`: `sha256(content_hash + "|" + jd_hash + "|" + prompt_version)`.
  Pipe separator avoids accidental collisions.
