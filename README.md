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

---

## Getting started

```bash
cp config.example.toml config.toml   # then edit: searches, criteria, webhook URL
uv sync
uv run jobwatch serve                # web UI + hourly pipeline
```

Or in Docker (the intended deployment):

```bash
docker compose up -d --build
```

The UI is at http://localhost:8000 — matched jobs by default, with unmatched/all
tabs for auditing. Jobs and every LLM verdict are stored in `data/jobwatch.db`.

### CLI

```bash
uv run jobwatch run-once      # one scrape → assess → notify cycle
uv run jobwatch assess        # (re)assess stored jobs without scraping
uv run jobwatch test-notify   # verify the Discord webhook
```

### How re-analysis works

Each verdict is keyed by a fingerprint of the criteria text + model. Editing
`[criteria]` (or switching model) makes every stored job "pending" again, and the
next pipeline run or `jobwatch assess` re-evaluates the backlog. Jobs are only
ever *notified* once, so re-analysis won't re-ping you about jobs you've seen.

### Swapping the LLM

Set `[llm] provider = "anthropic"` and `model = "claude-haiku-4-5"` (install the
extra with `uv sync --extra anthropic`, API key via `api_key` or
`$ANTHROPIC_API_KEY`). The `LLMClient` protocol in `src/jobwatch/llm.py` is the
seam for adding other providers.

### Development

```bash
uv run pytest        # tests
uv run ruff check .  # lint
uv run ty check      # types
```
