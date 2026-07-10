"""Pipeline behaviour with fake scraper/LLM/notifier: dedup, re-assessment, notify-once."""

from __future__ import annotations

import jobwatch.pipeline as pipeline_module
from jobwatch.criteria import set_criteria_text
from jobwatch.models import Job
from jobwatch.pipeline import assess_single, run_pipeline
from jobwatch.scraper import ScrapedJob


def scraped(external_id: str, title: str = "Backend Engineer") -> ScrapedJob:
    return ScrapedJob(
        site="linkedin",
        external_id=external_id,
        title=title,
        company="Acme",
        location="Copenhagen",
        url=f"https://example.com/{external_id}",
        description="Python things",
        posted_at=None,
        raw="{}",
    )


class FakeLLM:
    model = "fake"

    def __init__(self, matched: bool = True):
        self.matched = matched
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        return f'{{"matched": {str(self.matched).lower()}, "score": 7, "reasoning": "test"}}'


class FakeNotifier:
    def __init__(self):
        self.sent: list[list[Job]] = []

    def send_matches(self, jobs: list[Job], review_url: str) -> None:
        self.sent.append(list(jobs))


def run(session, llm, notifier, jobs, monkeypatch):
    monkeypatch.setattr(pipeline_module, "scrape_search", lambda search: jobs)
    return run_pipeline(session, llm, notifier)


def test_new_jobs_are_stored_assessed_and_notified_once(session, monkeypatch):
    llm, notifier = FakeLLM(matched=True), FakeNotifier()
    result = run(session, llm, notifier, [scraped("1"), scraped("2")], monkeypatch)

    assert result.new_jobs == 2
    assert result.assessed == 2
    assert len(notifier.sent) == 1 and len(notifier.sent[0]) == 2

    # Second run with the same scrape results: nothing new, no repeat notification.
    result = run(session, llm, notifier, [scraped("1"), scraped("2")], monkeypatch)
    assert result.new_jobs == 0
    assert result.assessed == 0
    assert len(notifier.sent) == 1


def test_unmatched_jobs_do_not_notify(session, monkeypatch):
    notifier = FakeNotifier()
    result = run(session, FakeLLM(matched=False), notifier, [scraped("1")], monkeypatch)
    assert result.assessed == 1
    assert notifier.sent == []


def test_criteria_change_does_not_reassess_the_backlog(session, monkeypatch):
    """Editing the criteria only affects newly-scraped jobs; already-assessed
    jobs keep their old verdict until explicitly reevaluated (on-demand)."""
    llm, notifier = FakeLLM(matched=True), FakeNotifier()
    run(session, llm, notifier, [scraped("1")], monkeypatch)
    assert llm.calls == 1

    set_criteria_text(session, "Completely new criteria")  # what the web UI does
    result = run(session, llm, notifier, [], monkeypatch)
    assert result.assessed == 0  # job 1 already has a verdict; left alone
    assert llm.calls == 1
    assert len(notifier.sent) == 1  # still only the original notification


def test_reevaluating_a_job_invalidates_its_old_verdict_instead_of_deleting_it(
    session, monkeypatch
):
    llm = FakeLLM(matched=True)
    run(session, llm, FakeNotifier(), [scraped("1")], monkeypatch)
    job = session.query(Job).one()
    first = job.active_assessment
    assert first is not None and first.invalidated_at is None

    first_id = first.id
    set_criteria_text(session, "Completely new criteria")
    assess_single(session, llm, job)

    session.expire(job, ["all_assessments", "active_assessment"])
    assert len(job.all_assessments) == 2  # old verdict kept, not deleted
    first_reloaded = next(a for a in job.all_assessments if a.id == first_id)
    assert first_reloaded.invalidated_at is not None

    current = job.active_assessment
    assert current is not None
    assert current.id != first_id


def test_empty_criteria_skips_assessment(session, monkeypatch):
    set_criteria_text(session, "  \n ")
    result = run(session, FakeLLM(), FakeNotifier(), [scraped("1")], monkeypatch)
    assert result.new_jobs == 1
    assert result.assessed == 0


def test_scrape_failure_does_not_abort_pipeline(session, monkeypatch):
    def boom(search):
        raise RuntimeError("linkedin said no")

    monkeypatch.setattr(pipeline_module, "scrape_search", boom)
    result = run_pipeline(session, FakeLLM(), FakeNotifier())
    assert result.new_jobs == 0
