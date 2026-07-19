from __future__ import annotations

import awa
import pytest

from jobwatch.llm import RateLimited, Verdict
from jobwatch.models import Job
from jobwatch.rate_limit import MIN_JITTER, RateLimitGate
from jobwatch.tasks import run_assess_job
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

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        self.calls = 0

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        self.calls += 1
        raise RateLimited(self.retry_after)


@pytest.mark.asyncio
async def test_assesses_and_completes_when_not_rate_limited(session, scene: Scene):
    job = scene.job()

    result = await run_assess_job(session, ScoringLLM(), RateLimitGate(), job.id)

    assert result is None
    assert job.active_assessment is not None


@pytest.mark.asyncio
async def test_rate_limit_snoozes_past_the_reset_and_closes_the_gate(session, scene: Scene):
    job = scene.job()
    gate = RateLimitGate()

    result = await run_assess_job(session, RateLimitedLLM(retry_after=42.0), gate, job.id)

    assert isinstance(result, awa.Snooze)
    assert 42.0 <= result.seconds <= 42.0 + MIN_JITTER
    assert gate.seconds_until_open() == pytest.approx(42.0, abs=2.0)
    assert job.active_assessment is None


@pytest.mark.asyncio
async def test_closed_gate_snoozes_without_calling_the_llm(session, scene: Scene):
    job = scene.job()
    llm = RateLimitedLLM(retry_after=42.0)
    gate = RateLimitGate()
    gate.close_for(10.0)

    result = await run_assess_job(session, llm, gate, job.id)

    assert isinstance(result, awa.Snooze)
    assert 0.0 < result.seconds <= 10.0 + MIN_JITTER
    assert llm.calls == 0
