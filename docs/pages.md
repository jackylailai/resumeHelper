# Pages - what each screen is for

The app's left sidebar is grouped by workflow stage. New users land on
**Evaluate**; stored data, scraping, and application tracking are one click
away.

## Evaluate - score one JD, see results

| Page | URL | What it does |
|------|-----|--------------|
| **Evaluate** | `/` | Paste a single JD. The default path scores synchronously; the optional async mode queues a durable evaluate job and polls status. Results route to `ready_to_submit`, `needs_tailoring`, or `skip`. |
| **History** | `/` (tab) | Every evaluation, newest first. Re-open a score to see explanation, strengths, gaps, tailoring status, and generated resume history. |
| **Submittable** | `/` (tab) | JDs that are ready to act on: high-score baseline matches and tailored drafts that passed the review gate. |

## Data - JDs and profiles the evaluator works against

| Page | URL | What it does |
|------|-----|--------------|
| **JD Database** | `/jobs.html` | Stored JDs from scraping or paste-to-store. Filter by source/status, inspect details, bulk-score rows, and move promising jobs to Applications. |
| **Profile** | `/` (tab) | Baseline resume profiles. Upload a PDF or paste skills text, then mark the default profile used by evaluation. |
| **Applications** | `/applications.html` | Tracker for jobs you decided to act on: planned, applied, interviewing, offer, rejected, or archived. |

## Pipeline - scheduled scraping

| Page | URL | What it does |
|------|-----|--------------|
| **Scrapes** | `/scrapes.html` | Schedule ingestion from 104, Yourator, LinkedIn, or all sources. Runs land in the JD Database with inserted/updated/skipped/failed/filtered counts. |

## Why this grouping

- **Evaluate is the immediate decision point.** It answers whether one JD is a
  match and whether resume work is needed.
- **Data is the source of truth.** Profiles, stored JDs, analyses, generated
  resumes, and application status are long-lived product state.
- **Pipeline is batch intake.** Scrapes bring in many JDs at a time before a
  user chooses what to score or pursue.

See [`docs/quickstart.md`](quickstart.md) for the first-evaluation flow and
[`docs/scrapers.md`](scrapers.md) for per-platform scraper mechanics.
