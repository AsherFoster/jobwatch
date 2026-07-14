"""awa task queue: task definitions and the worker runtime.

Tasks are plain dataclasses; awa stores them in Postgres (in the `awa`
schema, managed by `client.migrate()`, separate from Alembic) and its
leader-elected scheduler fires the periodic ones.
"""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass

import awa
import structlog
from sqlalchemy.engine import make_url

from jobwatch.config import config
from jobwatch.db import session_maker
from jobwatch.pipeline import sync_jobs

log = structlog.getLogger(__name__)

SYNC_JOBS_CRON = "0 * * * *"


@dataclass
class SyncJobs:
    """Run every configured search against every source and store unseen jobs."""


def awa_database_url() -> str:
    """config.database_url without the SQLAlchemy driver suffix — awa's
    Rust core wants a plain postgres:// URL."""
    url = make_url(config.database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(f"The worker requires Postgres; got {url.get_backend_name()!r}")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def make_client() -> awa.AsyncClient:
    """Build the awa client with every task handler and schedule registered."""
    client = awa.AsyncClient(awa_database_url())

    @client.task(SyncJobs)
    async def handle_sync_jobs(job: awa.Job[SyncJobs]) -> None:
        with session_maker() as session:
            await sync_jobs(session)

    client.periodic("sync_jobs", SYNC_JOBS_CRON, SyncJobs, SyncJobs())
    return client


async def run_worker() -> None:
    """Run the worker until SIGINT/SIGTERM."""
    client = make_client()
    await client.migrate()
    await client.start([("default", 1)])
    log.info("Worker started", sync_jobs_cron=SYNC_JOBS_CRON)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    log.info("Shutting down")
    await client.shutdown()
    await client.close()
