# Quickstart - your first evaluation in 5 minutes

> For developers extending the project, read [`readme.md`](../readme.md). This
> page is for users who want to evaluate a JD and get a reviewable resume draft.

## What this tool does

Resume Helper scores job descriptions against a baseline resume profile and
auto-tailors a resume when the match is promising but not quite ready. Each JD
is scored 0-100 and routed into one of three tiers:

| Score | Status | Behaviour |
|-------|--------|-----------|
| 85-100 | `ready_to_submit` | Strong match; review and apply with the baseline profile. |
| 60-84 | `needs_tailoring` | Queue a durable tailoring job and review the generated draft. |
| 0-59 | `skip` | Save the score and explanation, but do not recommend applying. |

You can paste one JD on the Evaluate tab, score stored listings from the JD
Database, or scrape JDs from 104 / Yourator / LinkedIn before evaluating them.

## First 5 minutes

### 1. Bring up the stack

Container mode is the default. It bundles Postgres, the FastAPI app, and the
Claude CLI path in one command. Docker must be running.

```bash
# One-time: get an OAuth token from your Claude subscription and put it in .env
claude setup-token
echo "CLAUDE_CODE_OAUTH_TOKEN=<paste here>" >> .env

# Start everything
./scripts/restart-docker.sh --full
```

Verify readiness:

```bash
./scripts/dev-verify.sh
```

You want `ok=true` on both `/api/health` and `/api/debug/claude-cli-ping`.

If you prefer an Anthropic API key instead of the subscription token, set
`ANTHROPIC_API_KEY=` and `LLM_BACKEND=anthropic` in `.env`.

### 2. Open the app

- http://localhost:8000/ - Evaluate / History / Submittable / Profile
- http://localhost:8000/jobs.html - JD Database
- http://localhost:8000/scrapes.html - scraper control
- http://localhost:8000/applications.html - application tracker

### 3. Add your baseline profile

1. Click the **Profile** tab.
2. Click **+ Add Profile**.
3. Name it, for example "Backend Engineer Resume".
4. Upload your resume PDF, then click **Preview Text** and confirm the
   extraction looks right.
5. Tick **Use as default profile**.
6. Click **Save Profile**.

The PDF is stored under `~/resumeHelper_data/` on the host; extracted text and a
file path live in the database.

### 4. Run your first evaluation

1. Back on the **Evaluate** tab, paste a full JD into the textarea.
2. Click **Evaluate**.
3. For the simplest demo, leave **Async job** unchecked. To show durable job
   polling, check **Async job** before clicking Evaluate.
4. Read the score badge, explanation, strengths, and gaps.

What happens next:

| Result | What to do |
|--------|------------|
| `ready_to_submit` | Review the baseline resume and add the job to the tracker if you want to apply. |
| `needs_tailoring` | Wait for the durable tailoring job to finish, then open the resume modal and review the draft. |
| `skip` | Keep the history entry as a record; no resume is generated. |

### 5. Review the generated resume

For `needs_tailoring`, the page polls every 2 seconds and shows a ready state
when the draft is available. Click **View Resume** to open the Markdown draft,
then use **Beautify** to render styled HTML and PDF output.

## Next steps

- **Browse stored JDs**: use `/jobs.html` to search, filter, inspect, and
  bulk-score listings.
- **Bulk-load JDs from job boards**: open `/scrapes.html`, choose a source and
  keyword, then run a schedule. See [`docs/scrapers.md`](scrapers.md) for
  per-platform mechanics.
- **Track applications**: add promising listings to the tracker and manage
  planned / applied / interviewing / offer / rejected / archived states.
- **Show the engineering story**: open
  [`docs/ai-workflow/SHOWCASE.md`](ai-workflow/SHOWCASE.md) for the demo script
  and proof points.

## Common gotchas

- **Health check failed on first load**: the Claude CLI subprocess can take a
  few seconds to cold-start. Click **Refresh** in System Status.
- **Tailored resume PDF download is empty**: `weasyprint` and its native
  dependencies must be installed for local PDF rendering.
- **JD is too long**: `/api/evaluate` rejects very long JDs. Trim the posting to
  the responsibilities and requirements.
- **No baseline profile**: Evaluate refuses to score without one. Set up the
  Profile tab first.

## When something breaks

- `./scripts/dev-verify.sh` - quick health probe.
- `docker compose -f docker-compose.app.yml logs -f app` - container logs.
- `./scripts/test.sh` - API contract and integration tests.
- [`readme.md`](../readme.md) - project layout and developer commands.
- [`CLAUDE.md`](../CLAUDE.md) - local development notes.
