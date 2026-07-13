"""Web UI for reviewing matched (and unmatched) jobs.

The scrape/assess/notify pipeline runs in a separate process (`jobwatch worker`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from jobwatch.criteria import get_criteria_text, set_criteria_text
from jobwatch.db import get_session
from jobwatch.llm import make_llm_client
from jobwatch.models import MATCHED_MIN_SCORE, Assessment, Job, UserJobState, UserSearch, utcnow
from jobwatch.pipeline import assess_single
from jobwatch.user_state import set_job_applied, set_job_bookmarked, set_job_rating

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


SessionDep = Annotated[Session, Depends(get_session)]


def get_job(job_id: int, session: SessionDep) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404)
    return job


JobDep = Annotated[Job, Depends(get_job)]


app = FastAPI(title="jobwatch")


@app.get("/", response_class=HTMLResponse)
def list_jobs(request: Request, session: SessionDep, show: str = "matched"):
    query = (
        select(Job)
        .options(
            selectinload(Job.all_assessments),
            selectinload(Job.active_assessment),
            selectinload(Job.user_state),
            selectinload(Job.search),
        )
        .order_by(Job.scraped_at.desc())
        .limit(500)
    )
    if show in ("matched", "unmatched"):
        # Match on each job's current verdict, whichever criteria it was
        # last evaluated against — editing the criteria doesn't clear
        # this list, only reevaluating a job does.
        query = query.join(Assessment).where(
            Assessment.invalidated_at.is_(None),
            Assessment.score >= MATCHED_MIN_SCORE
            if show == "matched"
            else Assessment.score < MATCHED_MIN_SCORE,
        )
    elif show == "saved":
        query = query.join(Job.user_state).where(UserJobState.bookmarked_at.is_not(None))
    jobs = session.scalars(query).unique().all()
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {"jobs": jobs, "show": show},
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job: JobDep):
    return templates.TemplateResponse(request, "job.html", {"job": job})


@app.put("/jobs/{job_id}/rating")
def rate_job(job: JobDep, session: SessionDep, rating: Annotated[int, Form(ge=1, le=5)]):
    set_job_rating(job, rating)
    session.commit()
    return Response(status_code=204)


@app.delete("/jobs/{job_id}/rating")
def clear_rating(job: JobDep, session: SessionDep):
    set_job_rating(job, None)
    session.commit()
    return Response(status_code=204)


@app.put("/jobs/{job_id}/bookmark")
@app.delete("/jobs/{job_id}/bookmark")
def bookmark_job(request: Request, job: JobDep, session: SessionDep):
    set_job_bookmarked(job, request.method == "PUT")
    session.commit()
    return Response(status_code=204)


@app.put("/jobs/{job_id}/applied")
@app.delete("/jobs/{job_id}/applied")
def mark_applied(request: Request, job: JobDep, session: SessionDep):
    set_job_applied(job, request.method == "PUT")
    session.commit()
    return Response(status_code=204)


@app.post("/jobs/{job_id}/reassess")
async def reassess(job: JobDep, session: SessionDep):
    if assessment := job.active_assessment:
        assessment.invalidated_at = utcnow()
        session.expire(job, ["active_assessment"])

    llm = make_llm_client()
    await assess_single(
        session,
        llm,
        job,
        criteria_text=get_criteria_text(session),
    )

    session.commit()
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request, session: SessionDep, saved: str = ""):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "criteria_text": get_criteria_text(session),
            "searches": session.scalars(select(UserSearch).order_by(UserSearch.id)).all(),
            "saved": saved,
            "show": "settings",
        },
    )


@app.get("/criteria")
def criteria_redirect():
    return RedirectResponse("/settings", status_code=301)


@app.post("/settings/criteria")
def save_criteria(session: SessionDep, text: str = Form("")):
    set_criteria_text(session, text)
    return RedirectResponse("/settings?saved=criteria", status_code=303)


def search_form(
    search_term: Annotated[str, Form()],
    location: Annotated[str, Form()],
) -> UserSearch:
    return UserSearch(search_term=search_term, location=location)


SearchFormDep = Annotated[UserSearch, Depends(search_form)]


def get_user_search(search_id: int, session: SessionDep) -> UserSearch:
    row = session.get(UserSearch, search_id)
    if row is None:
        raise HTTPException(status_code=404)
    return row


UserSearchDep = Annotated[UserSearch, Depends(get_user_search)]


@app.post("/settings/searches")
def add_search(session: SessionDep, search: SearchFormDep):
    session.add(search)
    session.commit()
    return RedirectResponse("/settings?saved=searches", status_code=303)


@app.post("/settings/searches/{search_id}")
def update_search(row: UserSearchDep, session: SessionDep, search: SearchFormDep):
    row.search_term = search.search_term
    row.location = search.location
    session.commit()
    return RedirectResponse("/settings?saved=searches", status_code=303)


@app.post("/settings/searches/{search_id}/delete")
def delete_search(row: UserSearchDep, session: SessionDep):
    # Jobs found by this search outlive it, just without attribution.
    session.execute(update(Job).where(Job.search_id == row.id).values(search_id=None))
    session.delete(row)
    session.commit()
    return RedirectResponse("/settings?saved=searches", status_code=303)
