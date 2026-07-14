"""CLI entry points: `worker` (awa task queue) is the long-running mode;
`sync-jobs` and `assess-jobs` run individual pipeline steps. The web UI is
served separately with `fastapi dev` (or uvicorn in Docker)."""

from __future__ import annotations

import asyncio

import click
import structlog

from jobwatch.criteria import get_criteria_text

log = structlog.get_logger()


@click.group(help="Scrape LinkedIn jobs, assess with an LLM, notify on matches.")
def app() -> None:
    pass


@app.command()
def worker() -> None:
    """Run the awa task-queue worker: syncs jobs every hour, forever."""
    from jobwatch.tasks import run_worker

    asyncio.run(run_worker())


@app.command("sync-jobs")
def sync_jobs_command() -> None:
    """Pull new jobs from LinkedIn for every configured search (no assessment)."""
    from jobwatch.db import session_maker
    from jobwatch.pipeline import sync_jobs

    with session_maker() as session:
        asyncio.run(sync_jobs(session))


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
    from jobwatch.db import session_maker
    from jobwatch.llm import make_llm_client
    from jobwatch.models import Job
    from jobwatch.pipeline import assess_pending, assess_single

    llm = make_llm_client()
    with session_maker() as session:
        if job_id is not None:
            criteria_text = get_criteria_text(session)
            assert criteria_text is not None

            job = session.get(Job, job_id)
            if job is None:
                raise click.ClickException(f"No job with id {job_id}")
            verdict = asyncio.run(assess_single(session, llm, job, criteria_text))
            click.echo(f"Job {job_id} scored {verdict.score}/5\n\n{verdict.reasoning}")
        else:
            count = asyncio.run(assess_pending(session, llm))
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
    )
    make_notifier().send_matches([fake], review_url=config.web.base_url)
    click.echo("Notification sent")
