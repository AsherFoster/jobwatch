"""Turn a job description + user criteria into a scored verdict."""

from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

from jobwatch.llm import LLMClient, Verdict
from jobwatch.models import Assessment, Job

log = structlog.getLogger(__name__)


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
            job_id=job.id,
            score=verdict.score,
            reasoning=verdict.reasoning,
            model=llm.model,
        )
    )

    return verdict
