"""CLI entry points: `serve` (web UI) and `worker` (scheduled pipeline) are the
long-running modes; `sync-jobs` and `assess-jobs` run individual pipeline steps."""

from __future__ import annotations

import click
import structlog

from jobwatch.criteria import get_criteria_text

log = structlog.get_logger()


@click.group(help="Scrape LinkedIn jobs, assess with an LLM, notify on matches.")
def app() -> None:
    pass


@app.command()
def serve() -> None:
    """Run the web UI (no background pipeline; run `jobwatch worker` alongside)."""
    import uvicorn

    from jobwatch.web.app import app

    uvicorn.run(app)


@app.command()
def worker() -> None:
    """Run the scrape -> assess -> notify pipeline on a schedule, forever."""
    from datetime import UTC

    from apscheduler.schedulers.blocking import BlockingScheduler

    from jobwatch.config import config
    from jobwatch.db import session_maker
    from jobwatch.llm import make_llm_client
    from jobwatch.models import utcnow
    from jobwatch.pipeline import run_pipeline

    def pipeline_tick() -> None:
        with session_maker() as session:
            run_pipeline(session, make_llm_client(config.llm))

    # Explicit UTC avoids tzlocal(), which fails on POSIX-style TZ values
    # (e.g. "CEST-2"); interval jobs don't need local time.
    scheduler = BlockingScheduler(timezone=UTC)
    scheduler.add_job(
        pipeline_tick,
        "interval",
        minutes=config.schedule.interval_minutes,
        next_run_time=utcnow(),  # first run at startup, then on the interval
        max_instances=1,
        coalesce=True,
    )
    click.echo(f"Worker started: pipeline every {config.schedule.interval_minutes} min")
    scheduler.start()


@app.command("sync-jobs")
def sync_jobs_command() -> None:
    """Pull new jobs from LinkedIn for every configured search (no assessment)."""
    from jobwatch.db import session_maker
    from jobwatch.pipeline import sync_jobs

    with session_maker() as session:
        sync_jobs(session)


@app.command("assess-jobs")
@click.argument("job_id", type=int, required=False)
def assess_jobs(job_id: int | None) -> None:
    """Assess stored jobs that have never been assessed (no scraping).

    With JOB_ID, (re-)assess just that job against the current criteria — even
    if it already has a verdict; the old verdict is kept as history, not lost.
    Editing the criteria (web UI, /criteria) does NOT re-queue already-assessed
    jobs — run this with a JOB_ID (or use the web UI's "Reevaluate" button) to
    refresh a specific job on demand.
    """
    from jobwatch.config import config
    from jobwatch.db import session_maker
    from jobwatch.llm import make_llm_client
    from jobwatch.models import Job
    from jobwatch.pipeline import assess_pending, assess_single

    llm = make_llm_client(config.llm)
    with session_maker() as session:
        if job_id is not None:
            criteria_text = get_criteria_text(session)
            assert criteria_text is not None

            job = session.get(Job, job_id)
            if job is None:
                raise click.ClickException(f"No job with id {job_id}")
            verdict = assess_single(session, llm, job, criteria_text)
            click.echo(
                f"Job {job_id}: {'matched' if verdict.matched else 'not matched'} "
                f"(score {verdict.score}/10) — {verdict.reasoning}"
            )
        else:
            count = assess_pending(session, llm)
            click.echo(f"Assessed {count} jobs")


@app.command("test-notify")
def test_notify() -> None:
    """Send a test notification to verify the webhook works."""
    from jobwatch.config import config
    from jobwatch.models import Job
    from jobwatch.notify import make_notifier

    fake = Job(
        title="Test notification",
        company="jobwatch",
        location="Nowhere",
        url="https://example.com",
        external_id="test",
        search_name="test",
    )
    make_notifier().send_matches([fake], review_url=config.web.base_url)
    click.echo("Notification sent")


@app.command("init")
def init() -> None:
    """Create the database schema and stamp it at the latest migration."""
    from jobwatch.db import init_db, session_maker

    with session_maker() as session:
        init_db(session.connection())
        session.commit()
    click.echo("Database initialized")


if __name__ == "__main__":
    app()
