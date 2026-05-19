# Eval Harness

Issue #113 uses "eval harness" as a production guardrail for LLM behavior, not
as a loose prompt playground. The current implementation covers these paths:

```text
baseline profile + JD
  -> LLM evaluate output
  -> output contract validation
  -> application-owned score routing
  -> regression report

baseline profile + JD + gaps
  -> LLM tailor output
  -> output contract validation
  -> required / forbidden fact checks
  -> regression report

free-form profile text
  -> LLM structured extraction output
  -> schema validation with unknown-key rejection
  -> persisted structured profile state

tailored resume Markdown
  -> LLM beautify HTML output
  -> HTML safety and factuality validation
  -> saved HTML/PDF artifacts
```

## Harness Boundaries

### 1. Evaluate Output Contract

The evaluate contract validates one raw LLM scoring response before application
code uses it. The accepted JSON shape is:

```json
{
  "score": 0,
  "explanation": "non-empty string",
  "strengths": ["non-empty string"],
  "gaps": ["non-empty string"]
}
```

The contract rejects invalid JSON, extra fields, missing or blank explanations,
scores outside `0..100`, and malformed `strengths` / `gaps` lists.

### 2. Tailor Output Contract

The tailor contract validates generated resume output before it can be persisted:

```json
{
  "tailoring_suggestions": ["non-empty string"],
  "tailored_resume": "full Markdown resume"
}
```

The contract rejects invalid JSON, extra fields, missing resume text, blank
suggestions, code fences inside `tailored_resume`, and assistant preambles such
as "Here is...".

This is implemented in `backend/app/services/llm/contracts.py` and is shared by
the Anthropic API and Claude CLI adapters. The background tailoring worker also
validates any client result before creating a `GeneratedResume`.

### 3. Structured Extraction Contract

Structured extraction validates profile JSON before it is persisted to
`BaselineProfile.structured_data`. The schema is versioned in code as
`StructuredExtractionOutputContract` and accepts only these top-level keys:

- `personal`
- `summary`
- `work_experience`
- `education`
- `languages`
- `certifications`
- `skills`
- `personal_qualities`

Unknown-key policy: reject. Extra top-level or nested keys fail closed as
`llm_invalid_output`, rather than being silently stored as profile facts.

Deterministic fixtures live at:

```text
backend/evals/fixtures/extract_cases.json
```

### 4. Beautify HTML Contract

Beautify HTML is treated as **untrusted output of the LLM**. The validator
in `backend/app/services/llm/contracts.py` is the single trust boundary
before the bytes reach a browser or weasyprint. It rejects:

- incomplete HTML documents
- markdown code fences
- `<script>` and other unsafe resource tags (`<iframe>`, `<object>`,
  `<embed>`, `<img>`, `<video>`, `<audio>`, `<source>`, `<link>`)
- external CSS/fonts/images/scripts, including `@import`, `@font-face`,
  `url()`, `src`, and `srcset` — including escape- and comment-obfuscated
  forms like `\40 font-face` or `/*x*/@import` (#136)
- any attribute starting with `on` (event handlers — `onclick`, `onerror`,
  `onload`, ...) regardless of tag
- `javascript:`, `vbscript:`, and `data:` schemes in `href` / `xlink:href`
  / `formaction` / `action` / `poster` attributes
- known hallucinated facts that are not present in the source Markdown

What the contract does **not** promise: it does not vouch for content
semantics. Two safe HTML documents can both satisfy the contract while
saying different things — factuality is a separate guarantee enforced by
the tailor harness and forbidden-facts list.

Deterministic fixtures live at:

```text
backend/evals/fixtures/beautify_cases.json
```

### 5. Scenario / Routing Harness

The evaluate scenario harness is fixture-driven. Each fixture provides:

- `profile`
- `job_description`
- expected score range
- expected application status
- optional required terms in model output
- optional forbidden terms in model output

The deterministic fixture set lives at:

```text
backend/evals/fixtures/evaluate_cases.json
```

The fake backend supports `[[score=N]]` markers, so CI can verify routing
without relying on provider variance.

### 6. Tailor Factuality Harness

The tailor harness checks generated resume Markdown against source-of-truth
facts. Each fixture provides:

- `baseline_text`
- `job_description`
- `score`
- `gaps`
- optional `structured_data`
- optional `proof_points`
- `required_facts`
- `forbidden_facts`
- `jd_only_terms`

The deterministic fixture set lives at:

```text
backend/evals/fixtures/tailor_cases.json
```

Required facts must appear in `tailored_resume`. Forbidden facts must not appear
in `tailored_resume`. Terms listed in `jd_only_terms` are rejected when they
appear in the generated resume without matching evidence in the baseline profile
or `proof_points`. This is a smoke-level factuality guard: it catches dropped key
facts, obvious fabrications, and common JD-only skill injection.

### 7. Report Harness

Harness CLIs return exit code `1` when any fixture fails and can write JSON or
Markdown reports for CI artifacts.

```bash
python -m backend.app.cli eval-harness --backend fake
python -m backend.app.cli tailor-harness --backend fake
python -m backend.app.cli extract-harness --backend fake
python -m backend.app.cli beautify-harness --backend fake
```

```bash
python -m backend.app.cli eval-harness \
  --backend fake \
  --report-json artifacts/evals/evaluate.json \
  --report-md artifacts/evals/evaluate.md

python -m backend.app.cli tailor-harness \
  --backend fake \
  --report-json artifacts/evals/tailor.json \
  --report-md artifacts/evals/tailor.md

python -m backend.app.cli extract-harness \
  --backend fake \
  --report-json artifacts/evals/extract.json \
  --report-md artifacts/evals/extract.md

python -m backend.app.cli beautify-harness \
  --backend fake \
  --report-json artifacts/evals/beautify.json \
  --report-md artifacts/evals/beautify.md
```

Manual provider runs are supported for smoke checks:

```bash
python -m backend.app.cli eval-harness --backend configured
python -m backend.app.cli eval-harness --backend claude-cli
python -m backend.app.cli eval-harness --backend anthropic

python -m backend.app.cli tailor-harness --backend configured
python -m backend.app.cli tailor-harness --backend claude-cli
python -m backend.app.cli tailor-harness --backend anthropic
```

Use fake backend results as CI gates. Real-provider runs are useful for manual
drift inspection, but should not be treated as stable pass/fail unless the
fixtures are designed for provider variance.

## CI Gate

Pull request CI runs both deterministic fake-backend harnesses before pytest:

```bash
python -m backend.app.cli eval-harness \
  --backend fake \
  --report-json artifacts/evals/evaluate.json \
  --report-md artifacts/evals/evaluate.md

python -m backend.app.cli tailor-harness \
  --backend fake \
  --report-json artifacts/evals/tailor.json \
  --report-md artifacts/evals/tailor.md
```

The CI job uploads JSON reports, Markdown reports, and raw command output as the
`ai-harness-reports` artifact. On pull requests, all Markdown reports are
included in the automated CI comment before the standard SIT summary.

## Not Yet Covered

The next harness layers should cover:

- proof-point retrieval connecting JD requirements to profile evidence
- provider/model replay across prompt versions
- broader factuality fixtures for multi-job work histories and CJK profiles
