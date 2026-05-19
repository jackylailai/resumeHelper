## Summary

- Briefly describe the change.

## Verification

- [ ] `python -m backend.app.cli eval-harness --backend fake`
- [ ] `python -m backend.app.cli tailor-harness --backend fake`
- [ ] `python -m backend.app.cli extract-harness --backend fake`
- [ ] `python -m backend.app.cli beautify-harness --backend fake`
- [ ] `python -m pytest backend/tests/unit/ backend/tests/integration/v2/`

## AI Prompt / Model Changes

If this PR changes a prompt, model, LLM output contract, score routing rule, or
LLM validation policy, include an eval report delta:

- [ ] Not applicable
- [ ] Prompt/model/output-contract change includes harness results
- [ ] Prompt comparison uses `python -m backend.app.cli prompt-replay --backend fake --old-prompt-version <old> --new-prompt-version <new>`
