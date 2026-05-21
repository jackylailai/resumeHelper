---
description: "Scope correction — what to keep, what to cut, what to add"
status: SUPERSEDED
---

# Scope Correction

> Historical note: this document predates durable `ai_jobs` and is no longer an
> implementation authority for runtime architecture. Tailoring now runs through
> backend durable workers, not n8n. `/api/callback` remains as a generic
> external resume delivery endpoint for optional future integrations.

## Context

Original spec was over-engineered for a single-user POC.
This document defines the actual boundaries and corrects the direction.

---

## The REAL core workflow (what actually matters)

```
Browser pastes JD
  → FastAPI: compute jd_hash → check job_analyses
      EXISTS → return cached score (no LLM call)
      NEW    → call LLM to score → insert job_analyses
  → score >= RESUME_GEN_THRESHOLD?
      NO  → return score only
      YES → POST n8n webhook { job_analysis_id, jd_full_text, baseline_skills }
              n8n calls LLM (with editable prompt) → generates tailored resume
              n8n POSTs back to POST /api/callback
              FastAPI inserts into generated_resumes (with prompt_version)
  → Browser receives { score, explanation, resume_text? }
```

Key property: same JD is scored only once (jd_hash dedup).
Same JD can produce multiple generated resumes by re-triggering n8n with a different prompt version.

---

## What to CUT (over-engineered for POC)

- **Resume versioning** — `resume_versions` table, version_number, version history UI
  - Why cut: single user uploading the same base resume repeatedly adds no value
- **Evaluation caching layer** — `evaluation_cache` table + cache_key logic
  - Why cut: POC doesn't need sub-second dedup; if JD is the same just don't re-submit
- **EvaluationJob / BackgroundTask complexity** — async job polling (202/job_id flow)
  - Why cut: POC is single-user, synchronous response is fine; no need for job queue
- **US3 compare endpoint** — section_diff, GET /api/resumes/{id}/compare
  - Why cut: never requested, no user need stated
- **Multi-resume management** — GET /api/resumes list, resume_id foreign keys
  - Why cut: single user, one baseline profile, no need to manage multiple resumes

---

## What to KEEP (already built, still useful)

- `POST /api/evaluate` — single endpoint: JD in → score + (maybe) generated resume out
- File parsing (pypdf / python-docx) for the baseline profile upload
- Hashing for JD dedup (skip re-evaluation if same JD seen before)
- LLM client abstraction (FakeLLMClient for dev, real LLM for prod)
- API envelope `{data, error, meta}`
- Simple upload UI (HTML + vanilla JS)

---

## What to ADD (the actual missing feature)

### 1. Baseline skills profile (one-time setup)
- User uploads their base resume / skills list ONCE
- Stored as plain text in DB (single row, or a flat file)
- Used as context for every resume generation call

### 2. Resume generation on high-score match
- If `score >= RESUME_GEN_THRESHOLD` → second LLM call:
  ```
  Prompt: "Given these skills: {baseline_skills}
           And this JD: {job_description}
           Write a tailored resume that matches the JD requirements
           using only skills the candidate actually has."
  ```
- Return generated resume text in response (or save to DB)

### 3. Simple job tracking (for POC)
- Store analyzed JDs so user can see history: which JDs were evaluated, scores, whether resume was generated
- Table: `job_analyses(id, jd_hash, jd_snippet, score, resume_generated, generated_resume_text, created_at)`

---

## Simplified DB schema (replace current 4-table design)

```sql
-- One-time baseline profile (single row, upserted)
CREATE TABLE baseline_profile (
    id          SERIAL PRIMARY KEY,
    skills_text TEXT        NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One record per unique JD (scored once, deduped by jd_hash)
CREATE TABLE job_analyses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jd_hash       VARCHAR(64) NOT NULL UNIQUE,
    jd_snippet    TEXT,                    -- first 200 chars, for list display
    jd_full_text  TEXT        NOT NULL,    -- full JD, needed for re-generation
    score         INTEGER CHECK (score BETWEEN 0 AND 100),
    threshold_met BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON job_analyses(created_at DESC);

-- Generated resumes: many per JD (prompt iteration via n8n)
CREATE TABLE generated_resumes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_analysis_id UUID NOT NULL REFERENCES job_analyses(id) ON DELETE CASCADE,
    resume_text     TEXT NOT NULL,
    prompt_version  VARCHAR(64),   -- maps to n8n workflow version / tag
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON generated_resumes(job_analysis_id, created_at DESC);
```

Rationale for splitting generated_resumes out:
- Same JD can be re-generated after tweaking the n8n prompt
- Each generation stored separately so you can compare outputs
- prompt_version tracks which n8n prompt produced which resume

---

## Simplified API surface (what's actually needed)

```
POST /api/profile              ← set/update baseline skills text
GET  /api/profile              ← get current baseline

POST /api/evaluate             ← score JD; if threshold met, fires n8n webhook
                                  response: { score, explanation, threshold_met,
                                              job_analysis_id }

POST /api/callback             ← n8n calls this when resume generation is done
                                  body: { job_analysis_id, resume_text, prompt_version }

GET  /api/history              ← list past analyses (jd_snippet, score, created_at)
GET  /api/history/{id}         ← one analysis + all generated_resumes for it
POST /api/history/{id}/regenerate ← re-trigger n8n for same JD (new prompt version)

GET  /api/health
```

---

## Threshold configuration

- `RESUME_GEN_THRESHOLD=60` — configurable in `.env`
- Below threshold: return score + explanation only, no LLM generation call
- At/above threshold: run generation, return both score + tailored resume text

---

## n8n verdict for this POC

**Use n8n for resume generation only (not for scoring).**

Split responsibilities:
| Step | Where | Why |
|------|-------|-----|
| Score JD (0-100) | FastAPI → LLM directly | Fast, synchronous, simple |
| Generate resume | FastAPI → n8n webhook → LLM | Prompt editable without code deploy |

n8n adds value specifically for generation because:
- Prompt for "rewrite resume to fit JD" benefits from iteration
- Can tweak, test, and compare outputs without touching Python code
- Built-in LLM nodes (no Python LLM client code needed for this step)
- Can add post-processing steps later (format as PDF, email, etc.)

n8n setup: run via `docker compose` alongside postgres. One extra service, manageable for POC.

---

## Files that need to be REWRITTEN (not just updated)

| File | Action |
|------|--------|
| `backend/app/models/` | Replace 4-table design with `baseline_profile` + `job_analyses` |
| `backend/alembic/versions/0001_initial.py` | Rewrite migration |
| `backend/app/api/resumes.py` | Rename/rewrite as `api/evaluate.py` |
| `backend/app/schemas/` | Simplify to `ProfileIn`, `EvaluateIn`, `EvaluateOut` |
| `backend/app/services/evaluator.py` | Add resume generation step |
| `backend/tests/integration/` | Replace US1/US2 tests with new flow tests |
| `static/app.js` + `upload.html` | Simplify: profile setup + JD input + result display |

## Files to KEEP AS-IS

| File | Reason |
|------|--------|
| `backend/app/services/parsing.py` | File parsing still needed for profile upload |
| `backend/app/services/hashing.py` | JD hash dedup still needed |
| `backend/app/services/llm/` | Protocol + FakeLLM + real client |
| `backend/app/api/envelope.py` | Envelope pattern still valid |
| `backend/app/config.py` | Settings pattern still valid |
| `backend/app/db.py` | SQLAlchemy setup still valid |
