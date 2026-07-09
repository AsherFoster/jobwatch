"""CLI entry points: `jobwatch serve` is the main long-running mode."""

from __future__ import annotations

import structlogg
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

structlog.basicConfig(level=structlog.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@click.group(help="Scrape LinkedIn jobs, assess with an LLM, notify on matches.")
def app() -> None:
    pass


@app.command()
@config_option
def serve(config_path: Path) -> None:
    """Run the web UI with the scrape/assess/notify pipeline on a schedule."""
    import uvicorn

    from jobwatch.web.app import create_app

    config = load_config(config_path)
    uvicorn.run(create_app(config), host=config.web.host, port=config.web.port)


@app.command()
@config_option
def run_once(config_path: Path) -> None:
    """Run one full scrape -> assess -> notify cycle and exit."""
    from jobwatch.llm import make_llm_client
    from jobwatch.notify import make_notifier
    from jobwatch.pipeline import run_pipeline

    config = load_config(config_path)
    session_factory = make_session_factory(make_engine(config.database_url))
    with session_factory() as session:
        result = run_pipeline(session, config, make_llm_client(config.llm), make_notifier(config))
    click.echo(
        f"{result.new_jobs} new jobs, {result.assessed} assessed, {len(result.notified)} notified"
    )


@app.command()
@config_option
def assess(config_path: Path) -> None:
    """Assess stored jobs that lack a verdict for the current criteria (no scraping).

    Run this after editing your criteria to re-analyse the whole backlog.
    """
    from jobwatch.llm import make_llm_client
    from jobwatch.pipeline import assess_pending

    config = load_config(config_path)
    session_factory = make_session_factory(make_engine(config.database_url))
    with session_factory() as session:
        count = assess_pending(session, make_llm_client(config.llm), config)
    click.echo(f"Assessed {count} jobs")


@app.command()
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
