"""Web UI for reviewing matched (and unmatched) jobs.

The scrape/assess/notify pipeline runs in a separate process (`jobwatch worker`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from jobwatch.config import Config
from jobwatch.criteria import current_criteria, set_criteria_text
from jobwatch.db import make_engine, make_session_factory
from jobwatch.llm import make_llm_client
from jobwatch.models import Assessment, Job
from jobwatch.pipeline import assess_single

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def create_app(config: Config) -> FastAPI:
    engine = make_engine(config.database_url)
    session_factory = make_session_factory(engine)
    llm = make_llm_client(config.llm)

    app = FastAPI(title="jobwatch")

    @app.get("/", response_class=HTMLResponse)
    def list_jobs(request: Request, show: str = "matched"):
        with session_factory() as session:
            query = (
                select(Job)
                .options(selectinload(Job.all_assessments), selectinload(Job.active_assessment))
                .order_by(Job.scraped_at.desc())
                .limit(500)
            )
            if show in ("matched", "unmatched"):
                # Match on each job's current verdict, whichever criteria it was
                # last evaluated against — editing the criteria doesn't clear
                # this list, only reevaluating a job does.
                query = query.join(Assessment).where(
                    Assessment.invalidated_at.is_(None),
                    Assessment.matched if show == "matched" else ~Assessment.matched,
                )
            jobs = session.scalars(query).unique().all()
        return templates.TemplateResponse(
            request,
            "jobs.html",
            {"jobs": jobs, "show": show},
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: int):
        with session_factory() as session:
            job = session.get(
                Job,
                job_id,
                options=[selectinload(Job.all_assessments), selectinload(Job.active_assessment)],
            )
            if job is None:
                raise HTTPException(status_code=404)
        return templates.TemplateResponse(request, "job.html", {"job": job})

    @app.post("/jobs/{job_id}/reassess")
    def reassess(job_id: int):
        with session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise HTTPException(status_code=404)
            assess_single(session, llm, config, job)
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    @app.get("/criteria", response_class=HTMLResponse)
    def edit_criteria(request: Request, saved: bool = False):
        with session_factory() as session:
            text = current_criteria(session, config)
        return templates.TemplateResponse(
            request,
            "criteria.html",
            {"criteria_text": text, "saved": saved, "show": "criteria"},
        )

    @app.post("/criteria")
    def save_criteria(text: str = Form("")):
        with session_factory() as session:
            set_criteria_text(session, text)
        return RedirectResponse("/criteria?saved=true", status_code=303)

    return app
