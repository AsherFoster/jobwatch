"""Web UI for reviewing matched (and unmatched) jobs.

The scrape/assess/notify pipeline runs in a separate process (`jobwatch worker`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from jobwatch.config import Config
from jobwatch.db import make_engine, make_session_factory
from jobwatch.models import Assessment, Job

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def create_app(config: Config) -> FastAPI:
    engine = make_engine(config.database_url)
    session_factory = make_session_factory(engine)

    app = FastAPI(title="jobwatch")
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
