# Prompt Registry

Prompt versions are labels, but each active label is now tied to a canonical
template file and a SHA-256 source hash.

Print the active registry:

```bash
python -m backend.app.cli prompt-registry
python -m backend.app.cli prompt-registry --json
```

Current canonical prompt sources:

| Step | Default Version | Env Var | Source |
|------|-----------------|---------|--------|
| evaluate | `resume-fit-v1` | `LLM_EVALUATE_PROMPT_VERSION` | `modes/score.md` |
| tailor | `tailor-v1` | `LLM_TAILOR_PROMPT_VERSION` | `modes/generate.md` |
| extract | `extract-v1` | `LLM_EXTRACT_PROMPT_VERSION` | `modes/extract.md` |
| beautify | `beautify-v1` | `LLM_BEAUTIFY_PROMPT_VERSION` | `modes/beautify.md` |

`LLM_PROMPT_VERSION` remains a backward-compatible fallback for evaluate when
`LLM_EVALUATE_PROMPT_VERSION` is blank.

The same template files are used by both `claude_cli` and `anthropic`. The
stored audit metadata should be read as:

```text
workflow_step + prompt_version + prompt_hash + backend + model
```

That combination tells you which logical prompt label was used, which exact
template bytes were active, and which provider/model executed it.

To compare prompt text between two versions, compare the source files between
the commits that introduced those versions:

```bash
git diff <old_commit>..<new_commit> -- modes/score.md
```

To compare behavior, run prompt replay:

```bash
python -m backend.app.cli prompt-replay \
  --backend fake \
  --old-prompt-version resume-fit-v1 \
  --new-prompt-version resume-fit-v2 \
  --report-md artifacts/evals/prompt-replay.md
```
