from __future__ import annotations

import awa
import pytest

from jobwatch.llm import RateLimited, Verdict
from jobwatch.models import Job
from jobwatch.tasks import MIN_JITTER, backoff_delay, run_assess_job
from jobwatch.test_scene import Scene


class ScoringLLM:
    model = "fake"

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        return Verdict(
            score=4,
            reasoning="good fit",
            summary="good job",
            summary_positives="it's a job",
            summary_negatives="it's a job",
        )


class RateLimitedLLM:
    model = "fake"

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        raise RateLimited(retry_after=42.0)


@pytest.mark.asyncio
async def test_assesses_and_completes_when_not_rate_limited(session, scene: Scene):
    job = scene.job()

    result = await run_assess_job(session, ScoringLLM(), job.id)

    assert result is None
    assert job.active_assessment is not None


@pytest.mark.asyncio
async def test_rate_limit_snoozes_past_the_reset(session, scene: Scene):
    job = scene.job()

    result = await run_assess_job(session, RateLimitedLLM(), job.id)

    assert isinstance(result, awa.Snooze)
    assert 42.0 <= result.seconds <= 42.0 + MIN_JITTER
    assert job.active_assessment is None


def test_backoff_delay_adds_bounded_jitter():
    for _ in range(100):
        assert 10.0 <= backoff_delay(10.0) <= 10.0 + MIN_JITTER

    # Long waits get proportionally more spread than MIN_JITTER.
    for _ in range(100):
        assert 3600.0 <= backoff_delay(3600.0) <= 3600.0 + 1800.0
