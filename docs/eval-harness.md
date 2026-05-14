# Eval Harness

Issue #113 uses "eval harness" as a production guardrail for LLM behavior, not
as a loose prompt playground. The first implementation covers the scoring path:

```text
baseline profile + JD
  -> LLM evaluate output
  -> output contract validation
  -> application-owned score routing
  -> regression report
```

## Harness Boundaries

### 1. Output Contract Harness

The output contract validates one raw LLM response before application code uses
it. For the evaluate call, the accepted JSON shape is:

```json
{
  "score": 0,
  "explanation": "non-empty string",
  "strengths": ["non-empty string"],
  "gaps": ["non-empty string"]
}
```

The contract rejects:

- invalid JSON
- extra top-level fields
- missing or blank `explanation`
- `score` outside `0..100`
- non-list or blank-item `strengths` / `gaps`

This is implemented in `backend/app/services/llm/contracts.py` and is shared by
the Anthropic API and Claude CLI adapters.

### 2. Scenario / Routing Harness

The scenario harness is fixture-driven. Each fixture provides:

- `profile`
- `job_description`
- expected score range
- expected application status
- optional required terms in model output
- optional forbidden terms in model output

The first fixture set is deterministic and targets the fake backend:

```text
backend/evals/fixtures/evaluate_cases.json
```

The fake backend supports `[[score=N]]` markers, so CI can verify routing
without relying on real provider variance.

### 3. Report Harness

The CLI returns exit code `1` when any fixture fails and can write JSON or
Markdown reports for CI artifacts.

```bash
python -m backend.app.cli eval-harness --backend fake

python -m backend.app.cli eval-harness \
  --backend fake \
  --report-json artifacts/evals/evaluate.json \
  --report-md artifacts/evals/evaluate.md
```

Manual provider runs are supported for smoke checks:

```bash
python -m backend.app.cli eval-harness --backend configured
python -m backend.app.cli eval-harness --backend claude-cli
python -m backend.app.cli eval-harness --backend anthropic
```

Use fake backend results as CI gates. Real-provider runs are useful for manual
drift inspection, but should not be treated as stable pass/fail unless the
fixtures are designed for provider variance.

## CI Gate

Pull request CI runs the deterministic fake-backend harness before the broader
pytest suite:

```bash
python -m backend.app.cli eval-harness \
  --backend fake \
  --report-json artifacts/evals/evaluate.json \
  --report-md artifacts/evals/evaluate.md
```

The CI job uploads the JSON report, Markdown report, and raw command output as
the `eval-harness-report` artifact. On pull requests, the Markdown report is
also included in the automated CI comment before the standard SIT summary.

The fake backend is the required gate because it validates output contracts and
score routing without network calls or provider credentials. Manual real-backend
runs are still useful for drift review, but they are not deterministic enough to
block every PR.

## Not Yet Covered

The next harness layer should cover resume generation and factuality:

- tailor output must preserve baseline facts
- generated resume must not invent employers, dates, degrees, metrics, or skills
- every required baseline section should remain present
- proof-point retrieval should connect JD requirements to profile evidence
- beautified HTML should preserve source resume content while changing layout

Those checks require separate fixtures and source-of-truth comparisons, so they
are intentionally kept out of the first evaluate-routing harness.
