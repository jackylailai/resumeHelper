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

This project defaults to the local `claude` CLI as the LLM backend. Host runs can
reuse an interactive Claude login. Docker runs cannot see the host login unless
credentials are mounted, so the app container must receive `ANTHROPIC_API_KEY`
or use `LLM_BACKEND=anthropic` with the same key.

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

If `/api/evaluate` returns `llm_unavailable` with `Invalid API key` or
`claude CLI failed`, check the app container first:
```bash
docker exec resumehelper-app sh -c 'test -n "$ANTHROPIC_API_KEY" && echo key-present || echo key-missing'
docker exec resumehelper-app sh -c 'echo hello | claude --print'
```
For `docker-compose.app.yml`, put `ANTHROPIC_API_KEY=...` in `.env` and restart
the app container. The compose file passes the key through explicitly.

---

## Scope Boundaries

Read `specs/001-resume-upload-rating/scope-correction.md` before every session.
If in doubt about whether a feature belongs: it doesn't. Ask first.

---

## End-of-Process Discord Notification

At the end of every task or process — whenever work is complete and there is meaningful
feedback to share — Claude **must** send a summary to Discord.

**When to trigger**
- A feature, fix, or chore is fully implemented (files written, committed, or PR opened)
- A test run finishes (pass or fail)
- An investigation concludes with findings
- Any multi-step process reaches a natural stopping point

**When NOT to trigger**
- Mid-task (only at the end, not after every small step)
- The output is purely a one-line answer with no follow-up action needed
- The previous message in the session already sent a Discord notification for the same result

**Format** (keep it short — aim for ≤ 8 lines):

```
[role] short title

✅/⚠️/❌  one-line outcome

• What changed / what was found
• Key numbers (score, test count, lines changed, etc.)
• Blockers or next step if any

Branch: <branch>  |  PR: #<n> or "not pushed yet"
```

**How to send**

Use the Discord MCP reply tool with:
- `chat_id`: `1241933442434732128`
- `message`: the formatted summary above
- Do **not** set `reply_to` — send as a top-level message

Example call (pseudo-code):
```
mcp__plugin_discord_discord__reply(
    chat_id="1241933442434732128",
    message="[Executor] feat/e2e-ui — UI complete\n\n✅ Static files rewritten ...",
)
```

If the Discord tool call fails (network error, permission), log the error in the
conversation but do **not** retry in a loop — skip and continue.
