"""CLI entry points: `serve` (web UI) and `worker` (scheduled pipeline) are the
long-running modes; `sync-jobs` and `assess-jobs` run individual pipeline steps."""

from __future__ import annotations

from pathlib import Path

import click

from jobwatch.config import DEFAULT_CONFIG_PATH, load_config
from jobwatch.db import make_engine, make_session_factory

config_option = click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    envvar="JOBWATCH_CONFIG",
    show_default=True,
    help="Path to config.toml",
)


@click.group(help="Scrape LinkedIn jobs, assess with an LLM, notify on matches.")
def app() -> None:
    pass


@app.command()
@config_option
def serve(config_path: Path) -> None:
    """Run the web UI (no background pipeline; run `jobwatch worker` alongside)."""
    import uvicorn

    from jobwatch.web.app import create_app

    config = load_config(config_path)
    uvicorn.run(create_app(config), host=config.web.host, port=config.web.port)


@app.command()
@config_option
def worker(config_path: Path) -> None:
    """Run the scrape -> assess -> notify pipeline on a schedule, forever."""
    from datetime import UTC

    from apscheduler.schedulers.blocking import BlockingScheduler

    from jobwatch.llm import make_llm_client
    from jobwatch.models import utcnow
    from jobwatch.notify import make_notifier
    from jobwatch.pipeline import run_pipeline

    config = load_config(config_path)
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
@config_option
def sync_jobs(config_path: Path) -> None:
    """Pull new jobs from LinkedIn for every configured search (no assessment)."""
    from jobwatch.pipeline import sync_jobs as run_sync

    config = load_config(config_path)
    session_factory = make_session_factory(make_engine(config.database_url))
    with session_factory() as session:
        new = run_sync(session, config)
    click.echo(f"{new} new jobs")


@app.command("assess-jobs")
@click.argument("job_id", type=int, required=False)
@config_option
def assess_jobs(config_path: Path, job_id: int | None) -> None:
    """Assess stored jobs that lack a verdict for the current criteria (no scraping).

    With JOB_ID, (re-)assess just that job — even if it already has a verdict.
    Run without arguments after editing your criteria to re-analyse the whole backlog.
    """
    from jobwatch.llm import make_llm_client
    from jobwatch.pipeline import assess_pending, assess_single

    config = load_config(config_path)
    session_factory = make_session_factory(make_engine(config.database_url))
    llm = make_llm_client(config.llm)
    with session_factory() as session:
        if job_id is not None:
            try:
                verdict = assess_single(session, llm, config, job_id)
            except LookupError as exc:
                raise click.ClickException(str(exc)) from exc
            click.echo(
                f"Job {job_id}: {'matched' if verdict.matched else 'not matched'} "
                f"(score {verdict.score}/10) — {verdict.reasoning}"
            )
        else:
            count = assess_pending(session, llm, config)
            click.echo(f"Assessed {count} jobs")


@app.command("test-notify")
@config_option
def test_notify(config_path: Path) -> None:
    """Send a test notification to verify the webhook works."""
    from jobwatch.models import Job
    from jobwatch.notify import make_notifier

    config = load_config(config_path)
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
