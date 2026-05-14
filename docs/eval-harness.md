# Eval Harness

Issue #113 uses "eval harness" as a production guardrail for LLM behavior, not
as a loose prompt playground. The current implementation covers two paths:

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

### 3. Scenario / Routing Harness

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

### 4. Tailor Factuality Harness

The tailor harness checks generated resume Markdown against source-of-truth
facts. Each fixture provides:

- `baseline_text`
- `job_description`
- `score`
- `gaps`
- optional `structured_data`
- `required_facts`
- `forbidden_facts`

The deterministic fixture set lives at:

```text
backend/evals/fixtures/tailor_cases.json
```

Required facts must appear in `tailored_resume`. Forbidden facts must not appear
in `tailored_resume`. This is a smoke-level factuality guard: it catches dropped
key facts and obvious fabrications, while deeper proof-point checks are tracked
separately.

### 5. Report Harness

Both CLIs return exit code `1` when any fixture fails and can write JSON or
Markdown reports for CI artifacts.

```bash
python -m backend.app.cli eval-harness --backend fake
python -m backend.app.cli tailor-harness --backend fake
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

- structured extraction schemas and source-fact preservation
- beautified HTML source preservation and rendering safety
- proof-point retrieval connecting JD requirements to profile evidence
- provider/model replay across prompt versions
- broader factuality fixtures for multi-job work histories and CJK profiles
