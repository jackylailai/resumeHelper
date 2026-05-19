# Quickstart — your first evaluation in 5 minutes

> For developers extending the project, read [`readme.md`](../readme.md). This
> page is for users who want to evaluate a JD and get a tailored resume PDF.

## What this tool does

Resume Helper scores job descriptions against a baseline resume profile and
auto-tailors a resume when the match is borderline. Each JD is scored 0-100
and routed into one of three tiers:

| Score | Status | Behaviour |
|---|---|---|
| 85-100 | `ready_to_submit` | Send your baseline resume — strong match. |
| 60-84  | `needs_tailoring` | App generates a tailored draft in the background. |
| 0-59   | `skip`            | Score saved, but not recommended to apply. |

You can paste JDs one at a time on the Evaluate tab, or scrape ~100 JDs from
104 / Yourator / LinkedIn and bulk-evaluate them from the JD Database.

## First 5 minutes

### 1. Bring up the stack (one-time)
Container mode is the default — it bundles Postgres, the FastAPI app, and
the Claude CLI in one command. You need Docker running.

```bash
# One-time: get an OAuth token from your Claude subscription and put it in .env
claude setup-token            # prints a token, copy it
echo "CLAUDE_CODE_OAUTH_TOKEN=<paste here>" >> .env

# Start everything
./scripts/restart-docker.sh --full
```

Verify it's up:
```bash
./scripts/dev-verify.sh
```
You want `ok=true` on both `/api/health` and `/api/debug/claude-cli-ping`.

If you'd rather use an Anthropic API key instead of the subscription token,
set `ANTHROPIC_API_KEY=` and `LLM_BACKEND=anthropic` in `.env`. See
[`readme.md`](../readme.md#llm-backends) for the trade-off.

### 2. Open the app
- http://localhost:8000/ — Evaluate / History / Submittable / Profile
- http://localhost:8000/jobs.html — JD Database (stored JDs)
- http://localhost:8000/scrapes.html — kick off a scraper
- http://localhost:8000/applications.html — application tracker

### 3. Add your baseline profile

1. Click the **Profile** tab.
2. Click **+ Add Profile**.
3. Name it ("Backend Engineer Resume" or whatever).
4. Upload your resume PDF, then click **Preview Text** — confirm the
   extraction looks right.
5. Tick **Use as default profile** (so future Evaluates pick it up
   automatically).
6. Click **Save Profile**.

The PDF is stored under `~/resumeHelper_data/` on your host; only the
extracted text and a path live in the database.

### 4. Run your first evaluation

1. Back on the **Evaluate** tab, paste a full JD into the textarea.
2. Click **Evaluate**.
3. Wait \~10-30 seconds for the LLM scoring.
4. Read the score badge and the explanation/strengths/gaps panels.

What happens next depends on the tier:
- **85+ (`ready_to_submit`)** — you're done. Apply with your baseline.
- **60-84 (`needs_tailoring`)** — a tailoring run starts in the background.
  The page polls every 2 seconds and shows a green checkmark when the
  draft is ready. Click **View Resume** to open the tailored resume in a
  modal, then **Beautify** to render a styled HTML + PDF.
- **<60 (`skip`)** — the score and the explanation are kept on the History
  tab, but no tailoring runs.

## Next steps

- **Browse stored JDs**: the **JD Database** tab (or `/jobs.html`) lets you
  filter / search every JD that's been scraped or evaluated, then re-score
  in bulk. See it after you've run a scrape.
- **Bulk-load JDs from job boards**: open **Scrapes** (`/scrapes.html`),
  pick a source (104 / Yourator / LinkedIn / all), enter a keyword, and
  click **Run schedule**. Each platform has different mechanics — see
  [`docs/scrapers.md`](scrapers.md) for what's actually happening under
  the hood.
- **Track applications**: when you decide to apply, click **Add to
  tracker** on the JD detail page. The **Applications** tab (or
  `/applications.html`) is the kanban for planned / applied / interviewing
  / offer / rejected / archived.

## Common gotchas

- **"Health check failed" on first load** — the Claude CLI subprocess takes
  4-10 s to cold-start the first time you hit it. Click **Refresh** in the
  System Status panel after a few seconds; it should go green.
- **Tailored resume PDF download is empty** — `weasyprint` isn't installed
  by default. Either install it on the host (Pango deps needed on macOS,
  see `readme.md`) or POST a generated PDF URL back via
  `POST /api/callback`. The plain Markdown draft is always available.
- **JD is too long** — `/api/evaluate` rejects very long JDs (the prompt
  context limit). Trim the JD to the role section, or split a "full JD
  packet" into the actual responsibilities + requirements.
- **No baseline profile** — Evaluate refuses to score without one. Set up
  the Profile tab first.

## When something breaks

- `./scripts/dev-verify.sh` — quick health probe (API + DB + Claude CLI).
- Container logs: `docker compose -f docker-compose.app.yml logs -f app`.
- Test suite (covers the API contracts): `./scripts/test.sh`.
- Project layout, env vars, and dev-mode trade-offs:
  [`readme.md`](../readme.md) and [`CLAUDE.md`](../CLAUDE.md).
- Found a bug? Open an issue:
  https://github.com/jackylailai/resumeHelper/issues
