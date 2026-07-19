"""awa task queue: task definitions and the worker runtime.

Tasks are plain dataclasses; awa stores them in Postgres (in the `awa`
schema, managed by `client.migrate()`, separate from Alembic) and its
leader-elected scheduler fires the periodic ones.
"""

from __future__ import annotations

import asyncio
import signal

import awa
import structlog
from sqlalchemy.engine import make_url

from jobwatch.config import config
from jobwatch.db import session_maker
from jobwatch.llm import make_llm_client
from jobwatch.models import Job
from jobwatch.pipeline.assess import assess_single
from jobwatch.pipeline.sync_companies import load_company_details
from jobwatch.pipeline.sync_jobs import sync_jobs
from jobwatch.task_kinds import AssessJob, LoadCompanyDetails, SyncJobs

log = structlog.get_logger()

SYNC_JOBS_CRON = "0 * * * *"


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
    llm = make_llm_client()

    @client.task(SyncJobs)
    async def handle_sync_jobs(job: awa.Job[SyncJobs]) -> None:
        with session_maker() as session:
            await sync_jobs(session)

    @client.task(AssessJob)
    async def handle_assess_job(job: awa.Job[AssessJob]) -> None:
        with session_maker() as session:
            stored = session.get_one(Job, job.args.job_id)
            assert stored.active_assessment is None, f"Job {stored.id} already assessed"
            criteria_text = stored.search.user.criteria_text
            await assess_single(session, llm, stored, criteria_text)
            session.commit()

    @client.task(LoadCompanyDetails)
    async def handle_load_company_details(job: awa.Job[LoadCompanyDetails]) -> None:
        with session_maker() as session:
            await load_company_details(session, job.args.company_id)
            session.commit()

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
