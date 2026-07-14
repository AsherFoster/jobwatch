# jobwatch

Scrapes LinkedIn job postings on a schedule, scores each one against your
criteria with an LLM, and pings a Discord webhook when something matches.
Jobs are stored in full (Postgres), so they can be re-assessed if the
criteria change.

Scraping uses JobSpy's anonymous LinkedIn view — no logged-in account at
risk of a ban. Expected scale is a few hundred jobs per day across a handful
of searches.

## Todos

- [x] Fix alembic foreign key hack, maybe postgres time?
- [x] Add company context from Google search
- [ ] LLM-generated search queries
- [ ] Refine LLM analysis
- [ ] Multiple job indexers
- [ ] Multi-user support

## Getting started

```bash
docker compose up -d              # Postgres
uv run alembic upgrade heads      # create the schema
uv run fastapi dev                # web UI (app path comes from pyproject.toml)
uv run jobwatch worker            # scheduled pipeline (separate process)
```

`ENVIRONMENT` must be one of `production`, `development`, or `test`. Every
command needs it set, except `pytest` (conftest.py forces it to `test`).

The `Dockerfile` builds an image that serves the web UI with uvicorn;
`docker-compose.yml` currently only runs Postgres.

### Config

Config is layered TOML, deep-merged in order: `config.toml` (checked-in
defaults) → `config.{ENVIRONMENT}.toml` → `config.local.toml` (gitignored —
put your webhook URL and API keys there). See `src/jobwatch/config.py` for
the schema.

## The web UI

The UI is at http://localhost:8000 — matched jobs by default, with
unmatched/all tabs for auditing. Jobs and every LLM verdict are stored in
Postgres.

The criteria text — free-form, e.g. "positives: python. negatives: data
analysis" — is edited on the **Settings** tab (`/settings`); it lives in the
database and starts blank.

The searches also live in the database (one `user_searches` row per search —
see the `UserSearch` model), and are managed on the same **Settings** tab.
Each search is just a term and a location: sources pull as many results as
the job board allows, looking back as far as the search's last found job.

### Your own ratings, bookmarks, and applied marks

Each job's page has controls for *your* take, separate from the LLM's verdict:
a 1-5 star rating, a **Save** bookmark (saved jobs get their own tab), and a
**Mark applied** toggle. These live in the `user_job_state` table
(`UserJobState` in `models.py`) — one mutable row per job, unlike the
append-only assessment history. Ratings are stored with an eye to eventually
feeding them back into the LLM prompt as examples, but nothing uses them for
that yet.

## CLI

```bash
uv run fastapi dev                 # web UI (no pipeline); Docker serves it with uvicorn
uv run jobwatch worker             # scrape → assess → notify on a schedule, forever
uv run jobwatch sync-jobs          # pull new jobs from LinkedIn (no assessment)
uv run jobwatch assess-jobs        # assess stored jobs
uv run jobwatch assess-jobs 42     # (re)assess a single job by ID
uv run jobwatch test-notify        # verify the Discord webhook
```

## How re-analysis works

Saving new criteria on `/settings` only affects jobs assessed from then on — it does **not**
retroactively re-run the backlog, so it's safe to tweak criteria without
burning LLM calls on every stored job. To refresh a specific job's verdict
against the current criteria, use the **Reevaluate** button on its page, or
`jobwatch assess-jobs 42`. A job's older verdicts aren't deleted when it's
reevaluated — they're kept, marked as superseded, so you can see how the
verdict changed. Jobs are only ever *notified* once, so re-analysis won't
re-ping you about jobs you've seen.

## Database schema changes

See `migrations` skill

## LLM providers

The provider is set with `[llm] provider` and `model` in config. The
`LLMClient` protocol in `src/jobwatch/llm/__init__.py` is the seam for
adding providers.

- `gemini` (the default) — `uv sync --extra gemini`, set `[gemini] api_key`.
  Uses the Interactions API with a JSON-schema response format, so the
  verdict is schema-constrained.
- `ollama` — set `[ollama] base_url`.
- `apple_fm` — Apple's on-device Foundation Models (Apple Silicon,
  macOS 26+). `uv sync --extra apple-fm`; no API key, and `model` is ignored
  (there's a single system model).
- `anthropic` — `uv sync --extra anthropic`, set `[anthropic] api_key`.
  The client exists but job assessment is not implemented yet.

Company descriptions (a one-sentence blurb generated the first time a
company is seen — see `CompanyDetails`) always use Gemini with Google
Search, regardless of the assessment provider.

## Development

```bash
uv run pytest         # tests (needs Postgres running)
uv run ruff check .   # lint
uv run ruff format .  # format
uv run ty check       # types
```
