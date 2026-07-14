from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from jobwatch.llm import Verdict
from jobwatch.models import Assessment, Job, User, utcnow
from jobwatch.pipeline.assess import assess_pending, assess_single, get_unassessed_job
from jobwatch.typing import unwrap


class FakeLLM:
    model = "fake"

    def __init__(self, score: int = 5) -> None:
        self.score = score
        self.criteria_seen: list[str] = []

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        self.criteria_seen.append(criteria_text)
        return Verdict(score=self.score, reasoning="good fit")


@pytest.mark.asyncio
async def test_assess_single_stores_the_verdict(session, add_job):
    job = add_job("1")

    verdict = await assess_single(session, FakeLLM(score=4), job, "criteria")
    session.commit()

    assert verdict.score == 4
    assessment = session.scalars(select(Assessment)).one()
    assert assessment.job_id == job.id
    assert assessment.score == 4
    assert assessment.reasoning == "good fit"
    assert assessment.model == "fake"
    assert assessment.invalidated_at is None


@pytest.mark.asyncio
async def test_assess_pending_assesses_every_unassessed_job(session, add_job, user: User):
    jobs = [add_job(str(i)) for i in range(3)]
    llm = FakeLLM()

    assert await assess_pending(session, llm) == 3

    assert llm.criteria_seen == [user.criteria_text] * 3
    for job in jobs:
        assert job.active_assessment is not None

    # Everything now has an active verdict, so a second run does nothing.
    assert await assess_pending(session, llm) == 0
    assert len(llm.criteria_seen) == 3


@pytest.mark.asyncio
async def test_invalidated_verdict_is_reassessed_and_kept_as_history(session, add_job):
    job = add_job("1")
    await assess_pending(session, FakeLLM(score=2))
    job.active_assessment.invalidated_at = utcnow()
    session.commit()

    assert await assess_pending(session, FakeLLM(score=5)) == 1

    assert len(job.all_assessments) == 2
    assert job.active_assessment.score == 5


def test_get_unassessed_job_picks_the_oldest_scrape_first(session, add_job):
    add_job("newer", scraped_at=utcnow())
    older = add_job("older", scraped_at=utcnow() - timedelta(hours=2))

    assert unwrap(get_unassessed_job(session)).id == older.id
