---
description: "Scope correction — what to keep, what to cut, what to add"
status: ACTIVE
---

# Scope Correction

## Context

Original spec was over-engineered for a single-user POC.
This document defines the actual boundaries and corrects the direction.

---

## The REAL core workflow (what actually matters)

```
User has a baseline skills profile (stored once)
  ↓
User pastes a JD → POST /api/evaluate
  ↓
LLM scores the fit (0–100)
  ↓
score >= RESUME_GEN_THRESHOLD (e.g. 60)?
  YES → LLM generates a tailored resume from baseline skills + JD
  NO  → Return low score only, no resume generated
  ↓
Store: jd_hash, score, threshold_met, generated_resume (nullable), timestamp
```

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
-- One-time baseline profile (single row)
CREATE TABLE baseline_profile (
    id          SERIAL PRIMARY KEY,
    skills_text TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- History of analyzed JDs
CREATE TABLE job_analyses (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jd_hash               VARCHAR(64) NOT NULL,
    jd_snippet            TEXT,           -- first 200 chars for display
    score                 INTEGER,
    threshold_met         BOOLEAN NOT NULL DEFAULT false,
    generated_resume_text TEXT,           -- null if score below threshold
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON job_analyses(jd_hash);
CREATE INDEX ON job_analyses(created_at DESC);
```

---

## Simplified API surface (what's actually needed)

```
POST /api/profile          ← set/update baseline skills (text or file)
GET  /api/profile          ← get current baseline

POST /api/evaluate         ← score JD against baseline
                               if score >= threshold → also generate resume
                               response: { score, explanation, generated_resume? }

GET  /api/history          ← list past analyses (jd_snippet, score, created_at)
GET  /api/history/{id}     ← get one analysis with full generated resume

GET  /api/health
```

---

## Threshold configuration

- `RESUME_GEN_THRESHOLD=60` — configurable in `.env`
- Below threshold: return score + explanation only, no LLM generation call
- At/above threshold: run generation, return both score + tailored resume text

---

## n8n verdict for this POC

**Skip n8n.** Reasons:
- Single user, no workflow complexity that needs visual editing
- n8n adds infra overhead (another service to run)
- Direct LLM call from Python is simpler and debuggable
- If workflow becomes multi-step in future (email, Slack notify, multiple LLMs) → add n8n then

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
