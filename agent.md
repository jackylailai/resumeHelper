# Agent Roles — resumeHelper

This file defines how Claude Code agents should behave when working on this project.
Each role has a specific responsibility and must not exceed its scope.

---

## Roles

### Planner
**Responsibility**: Understand the goal, break it into tasks, define acceptance criteria.

- Read `specs/` before writing any code
- Read `scope-correction.md` to stay within POC boundaries
- Output: ordered task list with file paths and acceptance criteria
- Must NOT write implementation code
- Must flag scope creep (anything not in `scope-correction.md`) before proceeding

**Trigger**: When starting a new feature or when requirements are unclear.

---

### Executor
**Responsibility**: Implement exactly what Planner specified — no more, no less.

- Follow TDD: write the test first, confirm RED, then implement until GREEN
- One commit per logical unit (test + implementation together)
- Must work on a feature branch, never directly on `main`
- Must NOT refactor unrelated code while implementing
- Reference `scope-correction.md` to avoid re-introducing cut features

**Trigger**: After Planner has produced a task list.

---

### Reviewer
**Responsibility**: Check code quality, security, and scope before PR merge.

Pre-push checklist (MUST pass before any push or PR):
- [ ] No real secrets in any tracked file (`.env`, API keys, tokens, passwords)
- [ ] No secrets in git commit messages or comments
- [ ] `.gitignore` covers `.env`, `*.key`, `backend/storage/`, `__pycache__/`
- [ ] No dead code or commented-out blocks added
- [ ] No features outside `scope-correction.md` crept in
- [ ] `ruff check backend/app` passes (no new errors)
- [ ] All new code has at least one test

**Trigger**: Before every push and before opening a PR.

---

### Testing
**Responsibility**: Verify tests cover the change and run clean.

- Unit tests first (`backend/tests/unit/`) — no DB needed
- Integration tests second (`backend/tests/integration/`) — requires postgres container
- New behaviour = new test (no exceptions)
- If a test is RED for a known reason (DB not up), say so explicitly
- Coverage gate: `pytest --cov=backend/app --cov-fail-under=85`

**Trigger**: After Executor commits, before Reviewer approves.

---

## PR Workflow

1. All work happens on a feature branch (`feat/`, `fix/`, `chore/`)
2. Reviewer runs the pre-push checklist
3. Push branch to `origin`
4. **Run e2e smoke test and post results as PR comment** (if server can start):
   ```bash
   # Start server first
   docker compose up -d postgres && uvicorn backend.app.main:app --reload

   # Run checks and auto-post to PR comment
   ./scripts/e2e-check.sh --pr <pr_number>
   ```
   Results appear as a PR comment with ✅/❌ per endpoint so user can verify
   feature behaviour matches expectations before merging.
4. Open PR with:
   - **Title**: short summary (≤70 chars)
   - **Body** (required sections):
     ```
     ## Planner — what was planned
     ## Executor — what was implemented
     ## Reviewer — issues found / checks passed
     ## Testing — which tests run, results
     ```
5. Every response/summary to the user must include those same four sections
6. User reviews and approves before merge to `main`
6. Never force-push to `main`

---

## LLM Backend

This project uses the local `claude` CLI (Claude Code subscription) as the LLM backend.
No separate Anthropic API key required.

Pattern (see `backend/app/services/llm/claude_cli.py`):
```python
result = subprocess.run(
    ["claude", "--print", "-p", prompt],
    capture_output=True, text=True, timeout=60
)
```

Prompt files live in `modes/` (career-ops pattern):
- `modes/score.md` — JD scoring prompt
- `modes/generate.md` — resume generation prompt

---

## Scope Boundaries

Read `specs/001-resume-upload-rating/scope-correction.md` before every session.
If in doubt about whether a feature belongs: it doesn't. Ask first.
