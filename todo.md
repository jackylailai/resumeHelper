# TODO: Resume Evaluation & Tailoring System

**Status**: Planning Phase  
**Updated**: 2026-05-05  
**Owner**: Next Agent

---

## 📋 Overview

Three-tier classification system for job matching:
1. **85+**: High match → ready to submit (no resume changes)
2. **60-84**: Medium match → tailor resume via n8n → LLM → subagent
3. **<60**: Low match → skip, record reason

---

## 🏗️ Architecture: n8n → CLI Agent → LLM

### Workflow

```
FastAPI /api/evaluate
  ↓
LLM Score JD (via Claude CLI)
  ↓
if score >= 60 → trigger n8n webhook
  ↓
n8n Webhook Receives: { job_analysis_id, jd_full_text, baseline_skills }
  ↓
Call Local CLI Agent (subagent)
  ├─ Input: resume (baseline_skills) + jd_full_text + score
  ├─ Task: Analyze gaps, suggest changes
  ├─ Call Claude LLM → "What should we change to match this JD?"
  └─ Output: { tailoring_suggestions, tailored_resume }
  ↓
n8n Markdown → PDF
  ↓
n8n POST /api/callback
  └─ { job_analysis_id, resume_text, pdf_url, prompt_version }
```

### Key: Subagent Role

**Subagent (CLI Agent) responsibilities:**
- Takes: baseline resume + JD + current score
- Analyzes: Skills gaps, missing keywords, experience alignment
- Calls: Claude LLM with prompt: `"Given this resume and JD (score: X), what specific changes would improve the match?"`
- Returns: Structured suggestions + Tailored resume text

---

## 📊 Database Schema

```sql
-- Main job analysis tracking
CREATE TABLE job_analyses (
    id              UUID PRIMARY KEY,
    jd_hash         VARCHAR(64) NOT NULL UNIQUE,
    jd_snippet      TEXT,
    jd_full_text    TEXT NOT NULL,
    
    score           INTEGER CHECK (score BETWEEN 0 AND 100),
    explanation     TEXT,
    strengths       TEXT[],
    gaps            TEXT[],
    
    -- Critical: Three-tier status
    status          VARCHAR(20) NOT NULL,
    -- Values: 'ready_to_submit' | 'needs_tailoring' | 'skip'
    
    can_submit      BOOLEAN NOT NULL DEFAULT false,
    skip_reason     TEXT,  -- Why we skipped
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Generated resumes (multiple versions per JD)
CREATE TABLE generated_resumes (
    id              UUID PRIMARY KEY,
    job_analysis_id UUID NOT NULL REFERENCES job_analyses(id) ON DELETE CASCADE,
    
    resume_text     TEXT NOT NULL,  -- Tailored resume
    pdf_url         TEXT,           -- Generated PDF path
    
    prompt_version  VARCHAR(64),    -- Track which prompt version created this
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- View for quick access to submittable resumes
CREATE VIEW submittable_resumes AS
SELECT 
    ja.id,
    ja.score,
    ja.jd_snippet,
    COALESCE(gr.resume_text, '') as resume,
    gr.pdf_url,
    ja.created_at
FROM job_analyses ja
LEFT JOIN generated_resumes gr ON ja.id = gr.job_analysis_id
WHERE ja.status = 'ready_to_submit'
ORDER BY ja.created_at DESC;
```

---

## 🔄 API Endpoints to Implement

### 1. POST /api/evaluate
**Input:** `{ jd_text: string }`  
**Flow:**
- Score JD via LLM (sync)
- Check score threshold
- If score >= 85: Mark as `ready_to_submit`, return immediately
- If 60 <= score < 85: Mark as `needs_tailoring`, trigger n8n webhook
- If score < 60: Mark as `skip`, return reason

**Response:**
```json
{
  "job_analysis_id": "uuid",
  "score": 72,
  "status": "needs_tailoring" | "ready_to_submit" | "skip",
  "message": "...",
  "action": "tailoring" | "none" | "skip"
}
```

### 2. POST /api/callback
**Input:** `{ job_analysis_id, resume_text, pdf_url, prompt_version }`  
**Flow:**
- n8n calls this after tailoring is complete
- Save GeneratedResume record
- Mark JobAnalysis as `can_submit = true`

**Response:**
```json
{ "id": "resume_uuid", "status": "success" }
```

### 3. GET /api/history
**Response:** All analyses grouped by status
```json
{
  "ready_to_submit": [...],
  "needs_tailoring": [...],
  "skip": [...],
  "total": 42,
  "submittable_count": 15
}
```

### 4. GET /api/submittable
**Response:** All resumes marked `can_submit = true`
```json
{
  "count": 15,
  "resumes": [
    {
      "id": "uuid",
      "score": 85,
      "jd_snippet": "Backend Engineer...",
      "pdf_url": "s3://bucket/resume.pdf",
      "created_at": "2026-05-05T10:00:00Z"
    },
    ...
  ]
}
```

### 5. GET /api/history/{id}
**Response:** Single job analysis + all its generated resumes
```json
{
  "job_analysis": { ... },
  "generated_resumes": [
    { "id", "resume_text", "pdf_url", "created_at" },
    ...
  ]
}
```

---

## 🎨 Frontend Logic (Next Agent)

1. **Evaluation View:**
   - Paste JD → Click "Evaluate"
   - Show score immediately
   - If `status == 'needs_tailoring'`: Show loading spinner, poll `/api/history/{id}` every 2s
   - If `status == 'ready_to_submit'`: Show ✅ and download button
   - If `status == 'skip'`: Show ⏭️ and skip reason

2. **Submittable Resumes View:**
   - GET `/api/submittable`
   - Display as table: Score | JD Snippet | PDF Download
   - Allow bulk export/download

3. **History View:**
   - GET `/api/history`
   - Show three tabs: Ready (✅) | Tailoring (⏳) | Skipped (⏭️)

---

## 🛠️ n8n Workflow: Resume Tailoring (JSON Template)

```json
{
  "name": "Tailor Resume for JD (via Subagent)",
  "nodes": [
    {
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "method": "POST",
      "path": "tailor-resume"
    },
    {
      "name": "Call Local CLI Agent",
      "type": "n8n-nodes-base.executeCommand",
      "command": "python -m resume_agent.cli",
      "args": [
        "--jd={{ $json.jd_full_text }}",
        "--resume={{ $json.baseline_skills }}",
        "--score={{ $json.score }}",
        "--format=json"
      ]
    },
    {
      "name": "Parse Subagent Output",
      "type": "n8n-nodes-base.code",
      "code": "return JSON.parse(data[0].body)"
    },
    {
      "name": "Convert to PDF",
      "type": "n8n-nodes-base.pdf",
      "input": "{{ $json.tailored_resume }}"
    },
    {
      "name": "Upload PDF (optional S3)",
      "type": "n8n-nodes-base.aws",
      "bucket": "resumehelper-pdfs",
      "key": "{{ $json.job_analysis_id }}-{{ now() }}.pdf"
    },
    {
      "name": "Callback to FastAPI",
      "type": "n8n-nodes-base.httpRequest",
      "method": "POST",
      "url": "http://host.docker.internal:8000/api/callback",
      "body": {
        "job_analysis_id": "{{ $json.job_analysis_id }}",
        "resume_text": "{{ $json.tailored_resume }}",
        "pdf_url": "{{ $json.pdf_url }}",
        "prompt_version": "v1"
      }
    }
  ]
}
```

---

## 📝 Implementation Checklist

### Phase 1: Backend (FastAPI)

- [ ] Update `JobAnalysis` model with `status` and `can_submit` fields
- [ ] Create migration: `alembic revision --autogenerate -m "add_status_field"`
- [ ] Implement `/api/evaluate` endpoint with three-tier logic
  - [ ] Add threshold constants: `THRESHOLD_HIGH=85`, `THRESHOLD_MID=60`
  - [ ] Handle `ready_to_submit` case
  - [ ] Handle `needs_tailoring` case (trigger n8n)
  - [ ] Handle `skip` case
- [ ] Implement `/api/callback` endpoint
- [ ] Implement `/api/history` endpoint
- [ ] Implement `/api/submittable` endpoint
- [ ] Implement `/api/history/{id}` endpoint
- [ ] Add tests: `backend/tests/integration/test_evaluate_three_tier.py`

### Phase 2: Subagent (CLI Agent)

- [ ] Create `backend/resume_agent/cli.py`
  - [ ] Parse args: `--jd`, `--resume`, `--score`, `--format`
  - [ ] Call Claude LLM with structured prompt
  - [ ] Analyze gaps between resume and JD
  - [ ] Generate suggestions + tailored resume
  - [ ] Output as JSON
- [ ] Create `backend/resume_agent/prompts/tailor.md`
  - [ ] Prompt: "Given resume, JD, and current score, suggest specific changes"
  - [ ] Include examples of good tailoring
- [ ] Create unit tests: `backend/tests/unit/test_resume_agent.py`

### Phase 3: n8n Workflow

- [ ] Create n8n workflow JSON
- [ ] Test webhook trigger
- [ ] Test CLI agent invocation
- [ ] Test PDF generation
- [ ] Test callback to FastAPI
- [ ] Document export at: `specs/n8n-workflows/tailor-resume-v1.json`

### Phase 4: Frontend

- [ ] Rewrite `static/app.js` for three-tier UI
- [ ] Implement evaluation form
- [ ] Implement loading/polling logic
- [ ] Implement submittable resumes view
- [ ] Add download buttons for PDFs

### Phase 5: Testing & Documentation

- [ ] Integration test: Full flow (evaluate → tailor → callback)
- [ ] Update README with quickstart
- [ ] Document n8n setup steps

---

## 🔗 Key Files to Modify

| File | Action | Reason |
|------|--------|--------|
| `backend/app/models/job_analysis.py` | Update schema | Add `status`, `can_submit`, `skip_reason` |
| `backend/app/api/evaluate.py` | Rewrite | Implement three-tier logic |
| `backend/app/services/evaluator_v2.py` | Update | Add n8n trigger logic |
| `backend/resume_agent/cli.py` | Create | Subagent CLI interface |
| `backend/resume_agent/prompts/tailor.md` | Create | Prompt for resume tailoring |
| `static/app.js` | Rewrite | Three-tier UI, polling logic |
| `specs/n8n-workflows/tailor-resume-v1.json` | Create | n8n workflow export |

---

## 🎯 Next Agent Tasks

**When you take over:**

1. **Read this file first** → Understand the three-tier system
2. **Check database**: Ensure migrations are applied
3. **Start with Phase 1**: Implement backend endpoints
4. **Then Phase 2**: Create CLI agent (subagent)
5. **Then Phase 3**: Setup n8n workflow
6. **Finally Phase 4**: Update frontend

**Questions to answer before implementing:**
- Where to store PDFs? (S3, local storage, or just in-memory?)
- Should we email tailored resumes or just provide download links?
- Do we need WebSocket for real-time updates, or is polling OK?
- Should subagent be a separate Python package or part of `backend/app/`?

---

## 📌 Critical Design Decisions

✅ **Why three-tier?**
- 85+: Skip unnecessary work (don't modify perfect matches)
- 60-84: Add value (tailor where it helps)
- <60: Respect user time (don't waste effort on bad fits)

✅ **Why use subagent?**
- Separation of concerns: n8n orchestrates, CLI agent analyzes
- Easier to test and iterate on the tailoring logic
- Can run locally without n8n being the "brains"
- Supports future multi-agent orchestration

✅ **Why async n8n?**
- Don't block API response waiting for LLM
- User gets immediate feedback on score
- Tailored resume comes later (poll or notify)
- Scales better under load

---

## 📚 Related Specs

- Main spec: `specs/001-resume-upload-rating/scope-correction.md`
- API design: `specs/001-resume-upload-rating/api.md` (to be created)
- Data model: `specs/001-resume-upload-rating/data-model.md`
- Roadmap: `specs/roadmap.md`

---

## 💬 Questions for Discussion

1. Should the subagent suggest changes incrementally, or all at once?
2. Do we want to track which suggestions were applied by the user?
3. Should we version prompts (v1, v2, etc.) to compare outputs?
4. What if n8n webhook fails? Should we retry automatically?

