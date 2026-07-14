"""Turn a job description + user criteria into a scored verdict."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.llm import LLMClient, Verdict
from jobwatch.models import Assessment, Job

log = structlog.get_logger()


async def assess_single(session: Session, llm: LLMClient, job: Job, criteria_text: str) -> Verdict:
    """(Re-)assess one job under the current criteria.

    Any existing active verdict for this job is invalidated rather than
    deleted, so past verdicts stay visible as history on the job's page.
    """
    assert job.active_assessment is None

    with structlog.contextvars.bound_contextvars(job_id=job.id):
        verdict = await llm.assess_job(job, criteria_text)
        log.info("Assessed job", score=verdict.score)
    session.add(
        Assessment(
            job=job,
            score=verdict.score,
            reasoning=verdict.reasoning,
            model=llm.model,
        )
    )

    return verdict


def get_unassessed_job(session: Session) -> Job | None:
    return session.scalars(
        select(Job)
        .where(Job.active_assessment == None)  # noqa: E711 — relationship NOT EXISTS
        .order_by(Job.scraped_at)
    ).first()


async def assess_pending(session: Session, llm: LLMClient) -> int:
    """Assess every job that has no active verdict (never assessed, or invalidated).

    Editing the criteria does NOT invalidate existing verdicts, so it does NOT
    re-trigger this for jobs that already have one — their old verdict just
    stays displayed as-is. Use assess_single (the web UI's "Reevaluate"
    button, or `assess-jobs JOB_ID`) to refresh a specific job against the
    current criteria on demand.
    """

    job = get_unassessed_job(session)
    count = 0

    while job is not None:
        criteria_text = job.search.user.criteria_text

        await assess_single(session, llm, job, criteria_text)
        session.commit()

        count += 1
        job = get_unassessed_job(session)

    return count
