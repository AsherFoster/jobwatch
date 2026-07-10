"""CLI entry points: `serve` (web UI) and `worker` (scheduled pipeline) are the
long-running modes; `sync-jobs` and `assess-jobs` run individual pipeline steps."""

from __future__ import annotations

import click

from jobwatch.config import load_config
from jobwatch.db import make_engine, make_session_factory


@click.group(help="Scrape LinkedIn jobs, assess with an LLM, notify on matches.")
def app() -> None:
    pass


@app.command()
def serve() -> None:
    """Run the web UI (no background pipeline; run `jobwatch worker` alongside)."""
    import uvicorn

    from jobwatch.web.app import create_app

    config = load_config()
    uvicorn.run(create_app(config), host=config.web.host, port=config.web.port)


@app.command()
def worker() -> None:
    """Run the scrape -> assess -> notify pipeline on a schedule, forever."""
    from datetime import UTC

    from apscheduler.schedulers.blocking import BlockingScheduler

    from jobwatch.llm import make_llm_client
    from jobwatch.models import utcnow
    from jobwatch.notify import make_notifier
    from jobwatch.pipeline import run_pipeline

    config = load_config()
    session_factory = make_session_factory(make_engine(config.database_url))

    def pipeline_tick() -> None:
        with session_factory() as session:
            run_pipeline(session, config, make_llm_client(config.llm), make_notifier(config))

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
def sync_jobs() -> None:
    """Pull new jobs from LinkedIn for every configured search (no assessment)."""
    from jobwatch.pipeline import sync_jobs as run_sync

    config = load_config()
    session_factory = make_session_factory(make_engine(config.database_url))
    with session_factory() as session:
        new = run_sync(session, config)
    click.echo(f"{new} new jobs")


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
    from jobwatch.llm import make_llm_client
    from jobwatch.models import Job
    from jobwatch.pipeline import assess_pending, assess_single

    config = load_config()
    llm = make_llm_client(config.llm)
    session_factory = make_session_factory(make_engine(config.database_url))
    with session_factory() as session:
        if job_id is not None:
            job = session.get(Job, job_id)
            if job is None:
                raise click.ClickException(f"No job with id {job_id}")
            verdict = assess_single(session, llm, config, job)
            click.echo(
                f"Job {job_id}: {'matched' if verdict.matched else 'not matched'} "
                f"(score {verdict.score}/10) — {verdict.reasoning}"
            )
        else:
            count = assess_pending(session, llm, config)
            click.echo(f"Assessed {count} jobs")


@app.command("test-notify")
def test_notify() -> None:
    """Send a test notification to verify the webhook works."""
    from jobwatch.models import Job
    from jobwatch.notify import make_notifier

    config = load_config()
    fake = Job(
        title="Test notification",
        company="jobwatch",
        location="Nowhere",
        url="https://example.com",
        external_id="test",
        search_name="test",
    )
    make_notifier(config).send_matches([fake], review_url=config.web.base_url)
    click.echo("Notification sent")


if __name__ == "__main__":
    app()
