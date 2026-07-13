I'm tired of trawling through hundreds of jobs on linkedin every day, looking for the odd one that is at all relevant. This problem is, in theory, easy to automate: regularly check for new job postings, use an LLM to assess them against my criteria, and then alert me if they match.

## Checking for new job listings

LinkedIn _does not like_ scraping, and I need to work around this - without putting my account at risk of a ban.

To do this, I want to use an anonymous view of jobs, most likely with speedyapply/JobSpy.

Expected scope: ~200 jobs per day, across 2-3 searches (eg "software engineer in Denmark")

These jobs should be saved in full, supporting re-analysis if the requirements change.

## Assessing jobs

Given the text of a job description, this tool needs to decide if it's worth my time to review - and an LLM is the best tool for this job.

For cost reasons, and since this isn't performance-critical, this will be run against Ollama running on an M1 Macbook.

I'll define requirements in text that gets provided to the LLM (think "positives: python. negatives: data analysis")

## Notify me

Any time a new job is found, I'll need alerting. This could be done with either a Discord webhook, or potentially WebPush.

I'll want one push notification even if multiple jobs are found: I should be able to go to a web page where I can see all the matched jobs (and unmatched, to audit)

## Tech

Assume this is hosted in Docker on a M1 Macbook. LLM is running in Ollama (ideally use an abstraction if I want to swap it for Anthropic etc)

Code should be written in Python, using modern tools like uv, ty, and ruff.


## Getting started

```bash
cp config.example.toml config.toml   # then edit: webhook URL, LLM
uv sync
uv run fastapi dev                   # web UI (app path comes from pyproject.toml)
uv run jobwatch worker               # scheduled pipeline (separate process)
```

Or in Docker (the intended deployment — runs `web` and `worker` as separate
services):

```bash
docker compose up -d --build
```

The UI is at http://localhost:8000 — matched jobs by default, with unmatched/all
tabs for auditing. Jobs and every LLM verdict are stored in `data/jobwatch.db`.
The criteria text is edited on the **Settings** tab (`/settings`); it lives in
the database and starts blank — there's no config.toml seed for it.

The searches also live in the database (a `settings` row named `searches`
holding a JSON list — see `src/jobwatch/searches.py`), and are managed on the
same **Settings** tab.

### Your own ratings, bookmarks, and applied marks

Each job's page has controls for *your* take, separate from the LLM's verdict:
a 1-5 star rating, a **Save** bookmark (saved jobs get their own tab), and a
**Mark applied** toggle. These live in the `user_job_state` table
(`UserJobState` in `models.py`) — one mutable row per job, unlike the
append-only assessment history. Ratings are stored with an eye to eventually feeding them back
into the LLM prompt as examples, but nothing uses them for that yet.

### CLI

```bash
uv run fastapi dev                 # web UI (no pipeline); Docker serves it with uvicorn
uv run jobwatch worker             # scrape → assess → notify on a schedule, forever
uv run jobwatch sync-jobs          # pull new jobs from LinkedIn (no assessment)
uv run jobwatch assess-jobs        # assess stored jobs
uv run jobwatch assess-jobs 42     # (re)assess a single job by ID
uv run jobwatch test-notify        # verify the Discord webhook
```

### How re-analysis works

Saving new criteria on `/settings` only affects jobs assessed from then on — it does **not**
retroactively re-run the backlog, so it's safe to tweak criteria without
burning LLM calls on every stored job. To refresh a specific job's verdict
against the current criteria, use the **Reevaluate** button on its page, or
`jobwatch assess-jobs 42`. A job's older verdicts aren't deleted when it's
reevaluated — they're kept, marked as superseded, so you can see how the
verdict changed. Jobs are only ever *notified* once, so re-analysis won't
re-ping you about jobs you've seen.

### Database schema changes

See `migrations` skill

### Swapping the LLM

Set `[llm] provider = "anthropic"` and `model = "claude-haiku-4-5"` (install the
extra with `uv sync --extra anthropic`, API key via `[anthropic] api_key` or
`$ANTHROPIC_API_KEY`). The `LLMClient` protocol in `src/jobwatch/llm.py` is the
seam for adding other providers.

For Gemini, set `[llm] provider = "gemini"` and `model = "gemini-2.5-flash"`
(install the extra with `uv sync --extra gemini`, API key via `[gemini]
api_key` or `$GEMINI_API_KEY`). This provider uses the Interactions API with a
JSON-schema response format, so the verdict is schema-constrained.

On Apple Silicon (macOS 26+), set `[llm] provider = "apple_fm"` to use Apple's
on-device Foundation Models (install with `uv sync --extra apple-fm`; no API
key, and `model` is ignored — there's a single system model). This provider
uses the SDK's guided generation (`@fm.generable`), so the verdict is
schema-constrained rather than parsed out of free-form JSON.

### Development

```bash
uv run pytest        # tests
uv run ruff check .  # lint
uv run ty check      # types
```
