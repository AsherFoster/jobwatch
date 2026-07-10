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
uv run jobwatch serve                # web UI
uv run jobwatch worker               # scheduled pipeline (separate process)
```

Or in Docker (the intended deployment — runs `web` and `worker` as separate
services):

```bash
docker compose up -d --build
```

The UI is at http://localhost:8000 — matched jobs by default, with unmatched/all
tabs for auditing. Jobs and every LLM verdict are stored in `data/jobwatch.db`.
The criteria text is edited on the **Criteria** tab (`/criteria`); it lives in
the database and starts blank — there's no config.toml seed for it.

The searches also live in the database (a `settings` row named `searches`
holding a JSON list — see `src/jobwatch/searches.py`), not in config.toml.
There's no UI for them yet: on a database that predates this, migration 0003
copies them out of config.toml; otherwise seed the row with:

```bash
uv run python -c "
from jobwatch.db import session_maker
from jobwatch.searches import SearchConfig, set_searches
with session_maker() as s:
    set_searches(s, [SearchConfig(name='swe-denmark', search_term='software engineer', location='Denmark')])
"
```

### CLI

```bash
uv run jobwatch serve              # web UI (no pipeline)
uv run jobwatch worker             # scrape → assess → notify on a schedule, forever
uv run jobwatch sync-jobs          # pull new jobs from LinkedIn (no assessment)
uv run jobwatch assess-jobs        # assess stored jobs
uv run jobwatch assess-jobs 42     # (re)assess a single job by ID
uv run jobwatch test-notify        # verify the Discord webhook
```

### How re-analysis works

Saving new criteria on `/criteria` only affects jobs assessed from then on — it does **not**
retroactively re-run the backlog, so it's safe to tweak criteria without
burning LLM calls on every stored job. To refresh a specific job's verdict
against the current criteria, use the **Reevaluate** button on its page, or
`jobwatch assess-jobs 42`. A job's older verdicts aren't deleted when it's
reevaluated — they're kept, marked as superseded, so you can see how the
verdict changed. Jobs are only ever *notified* once, so re-analysis won't
re-ping you about jobs you've seen.

### Database schema changes

A brand new database is created straight from `src/jobwatch/models.py` (via
`Base.metadata.create_all()` on first run) — no migration involved. Alembic
(`src/jobwatch/migrations/`) only comes in when a schema change needs to be
applied to a database that already exists, since `create_all()` can add new
tables but won't alter existing ones. It's run manually, not automatically on
startup:

```bash
uv run alembic upgrade head    # apply pending migrations to your deployed DB
```

This picks up the same `config.toml` (or `JOBWATCH_CONFIG`) jobwatch itself
reads. There's no "baseline" migration recreating table history — `models.py`
+ `create_all()` already covers a fresh database, so each migration here only
needs to describe the delta for a database that predates it.

To add a schema change: edit `models.py`, then write a migration by hand
(`uv run alembic revision -m "..."`) — sqlite's limited `ALTER TABLE` support
means most non-trivial changes need `op.batch_alter_table(...)`.

### Swapping the LLM

Set `[llm] provider = "anthropic"` and `model = "claude-haiku-4-5"` (install the
extra with `uv sync --extra anthropic`, API key via `api_key` or
`$ANTHROPIC_API_KEY`). The `LLMClient` protocol in `src/jobwatch/llm.py` is the
seam for adding other providers.

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
