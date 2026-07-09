"""Web UI for reviewing matched (and unmatched) jobs, plus the background scheduler."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from jobwatch.config import Config
from jobwatch.db import make_engine, make_session_factory
from jobwatch.llm import make_llm_client
from jobwatch.models import Assessment, Job
from jobwatch.notify import make_notifier
from jobwatch.pipeline import run_pipeline

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def create_app(config: Config, with_scheduler: bool = True) -> FastAPI:
    engine = make_engine(config.database_url)
    session_factory = make_session_factory(engine)

    def pipeline_tick() -> None:
        with session_factory() as session:
            try:
                run_pipeline(session, config, make_llm_client(config.llm), make_notifier(config))
            except Exception:
                logger.exception("Pipeline run failed")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        scheduler = None
        if with_scheduler:
            # Explicit UTC avoids tzlocal(), which fails on POSIX-style TZ
            # values (e.g. "CEST-2"); interval jobs don't need local time.
            scheduler = BackgroundScheduler(timezone=UTC)
            scheduler.add_job(
                pipeline_tick,
                "interval",
                minutes=config.schedule.interval_minutes,
                next_run_time=None,  # first run happens on the interval, not at startup
                max_instances=1,
                coalesce=True,
            )
            scheduler.start()
            logger.info("Scheduler started: every %d min", config.schedule.interval_minutes)
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="jobwatch", lifespan=lifespan)
    fingerprint = config.criteria.fingerprint(config.llm.model)

    @app.get("/", response_class=HTMLResponse)
    def list_jobs(request: Request, show: str = "matched"):
        query = (
            select(Job)
            .options(selectinload(Job.assessments))
            .order_by(Job.scraped_at.desc())
            .limit(500)
        )
        if show in ("matched", "unmatched"):
            query = query.join(Assessment).where(
                Assessment.criteria_fingerprint == fingerprint,
                Assessment.matched if show == "matched" else ~Assessment.matched,
            )
        with session_factory() as session:
            jobs = session.scalars(query).unique().all()
        return templates.TemplateResponse(
            request,
            "jobs.html",
            {"jobs": jobs, "show": show, "fingerprint": fingerprint},
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: int):
        with session_factory() as session:
            job = session.get(Job, job_id, options=[selectinload(Job.assessments)])
        if job is None:
            raise HTTPException(status_code=404)
        return templates.TemplateResponse(request, "job.html", {"job": job})

    return app
