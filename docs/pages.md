# Pages — what each tab is for

The app's left sidebar is grouped into three sections by purpose. New users
land on **Evaluate**; everything else is reachable from the sidebar.

## EVALUATE — score one JD, see results

| Page | URL | What it does |
|---|---|---|
| **Evaluate** | `/` | Paste a single JD. The LLM scores it against your selected baseline profile and routes the result into one of three tiers (`ready_to_submit` / `needs_tailoring` / `skip`). For `needs_tailoring`, a tailored resume draft is generated in the background. |
| **History** | `/` (tab) | Every evaluation you've ever run, newest first. Re-open any score to see the explanation, strengths, gaps, and tailored resume if one was generated. |
| **Submittable** | `/` (tab) | Just the JDs that scored `ready_to_submit` (85+). The shortlist of "you can apply with your baseline as-is". |

## DATA — the JDs and the resumes the evaluator works against

| Page | URL | What it does |
|---|---|---|
| **JD Database** | `/jobs.html` | Every stored JD — anything scraped or pasted-to-store. Filter by source / status, page through results, bulk-score a selection against the current profile, bulk-delete stale rows. |
| **Profile** | `/` (tab) | Your baseline resume(s). Upload a PDF or paste skills text. The evaluator scores JDs against the *default* profile unless you pick another. |
| **Applications** | `/applications.html` | Kanban tracker for JDs you've decided to apply to: planned / applied / interviewing / offer / rejected / archived. Add a JD here from its detail page on `/jobs.html`. |

## PIPELINE — scheduled scraping

| Page | URL | What it does |
|---|---|---|
| **Scrapes** | `/scrapes.html` | Schedule a scrape against 104 / Yourator / LinkedIn (or all). Pick a keyword, optional filters, and a row limit; runs land in the JD Database. The lower table shows past runs with stats (inserted / updated / skipped / failed / filtered). |

## Why this grouping

- **Evaluate is per-JD, now.** You're paying for one LLM call and getting one
  result. History and Submittable are just views over those results.
- **Data is everything the evaluator reads from or writes to.** Profiles,
  stored JDs, application status — long-lived state.
- **Pipeline is scheduled batch work.** Scrapes pulls dozens of JDs at a
  time into Data, separate from any specific evaluation.

See [`docs/quickstart.md`](quickstart.md) for the end-to-end first-evaluation
flow, and [`docs/scrapers.md`](scrapers.md) for how each platform is scraped.
