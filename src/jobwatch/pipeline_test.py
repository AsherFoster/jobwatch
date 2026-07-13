"""Pipeline behaviour with fake job source/LLM: dedup, re-assessment, notify-once."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

import jobwatch.pipeline as pipeline_module
from jobwatch.assess import Verdict
from jobwatch.criteria import set_criteria_text
from jobwatch.models import Assessment, Job, UserSearch, utcnow
from jobwatch.notify import NullNotifier
from jobwatch.pipeline import assess_single, hours_to_search, run_pipeline
from jobwatch.search_jobs import JobSource, ScrapedJob


def add_search(session, search_term: str = "engineer") -> UserSearch:
    search = session.scalar(select(UserSearch).where(UserSearch.search_term == search_term))
    if search is None:
        search = UserSearch(search_term=search_term, location="Denmark")
        session.add(search)
        session.commit()
    return search


def fake_source(search_function) -> JobSource:
    return JobSource(id="fake", name="Fake", search_function=search_function)


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

    def __init__(self, score: int = 4):
        self.score = score
        self.calls = 0

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        self.calls += 1
        return Verdict(score=self.score, reasoning="test")


def run(session, llm, jobs, monkeypatch, criteria="Positives: python"):
    set_criteria_text(session, criteria)
    add_search(session)
    monkeypatch.setattr(
        pipeline_module, "JOB_SOURCES", [fake_source(lambda search, hours_old: jobs)]
    )
    monkeypatch.setattr(pipeline_module, "make_notifier", NullNotifier)
    asyncio.run(run_pipeline(session, llm))


def all_jobs(session) -> list[Job]:
    return list(session.scalars(select(Job).order_by(Job.external_id)))


def test_new_jobs_are_stored_assessed_and_notified_once(session, monkeypatch):
    llm = FakeLLM(score=4)
    run(session, llm, [scraped("1"), scraped("2")], monkeypatch)

    jobs = all_jobs(session)
    assert [job.external_id for job in jobs] == ["1", "2"]
    assert all(job.search_id == add_search(session).id for job in jobs)
    assert all(job.active_assessment is not None for job in jobs)
    assert all(job.notified_at is not None for job in jobs)
    first_notified_at = [job.notified_at for job in jobs]

    # Second run with the same scrape results: nothing new, no repeat notification.
    run(session, llm, [scraped("1"), scraped("2")], monkeypatch)
    assert len(all_jobs(session)) == 2
    assert len(session.scalars(select(Assessment)).all()) == 2
    assert [job.notified_at for job in all_jobs(session)] == first_notified_at


def test_unmatched_jobs_do_not_notify(session, monkeypatch):
    run(session, FakeLLM(score=2), [scraped("1")], monkeypatch)

    job = session.scalars(select(Job)).one()
    assert job.active_assessment is not None
    assert not job.active_assessment.matched
    assert job.notified_at is None


def test_criteria_change_does_not_reassess_the_backlog(session, monkeypatch):
    """Editing the criteria only affects newly-scraped jobs; already-assessed
    jobs keep their old verdict until explicitly reevaluated (on-demand)."""
    llm = FakeLLM()
    run(session, llm, [scraped("1")], monkeypatch)
    assert llm.calls == 1

    # Criteria edited (what the web UI does), then the pipeline runs again.
    run(session, llm, [], monkeypatch, criteria="Completely new criteria")
    job = session.scalars(select(Job)).one()
    assert len(job.all_assessments) == 1  # job 1 already has a verdict; left alone
    assert llm.calls == 1


def test_reevaluating_a_job_invalidates_its_old_verdict_instead_of_deleting_it(
    session, monkeypatch
):
    llm = FakeLLM()
    run(session, llm, [scraped("1")], monkeypatch)
    job = session.scalars(select(Job)).one()
    first = job.active_assessment
    assert first is not None and first.invalidated_at is None
    first_id = first.id

    # Reevaluation: the caller invalidates the old verdict, then assesses anew.
    first.invalidated_at = utcnow()
    session.commit()
    asyncio.run(assess_single(session, llm, job, "Completely new criteria"))
    session.commit()

    assert len(job.all_assessments) == 2  # old verdict kept, not deleted
    first_reloaded = next(a for a in job.all_assessments if a.id == first_id)
    assert first_reloaded.invalidated_at is not None

    current = job.active_assessment
    assert current is not None
    assert current.id != first_id


def test_empty_criteria_skips_assessment(session, monkeypatch):
    run(session, FakeLLM(), [scraped("1")], monkeypatch, criteria="  \n ")

    job = session.scalars(select(Job)).one()
    assert job.active_assessment is None


def test_scrape_failure_does_not_abort_pipeline(session, monkeypatch):
    def boom(search, hours_old):
        raise RuntimeError("linkedin said no")

    add_search(session)
    monkeypatch.setattr(pipeline_module, "JOB_SOURCES", [fake_source(boom)])
    asyncio.run(run_pipeline(session, FakeLLM()))
    assert all_jobs(session) == []


def test_hours_to_search_defaults_to_24_when_search_has_no_jobs(session):
    assert hours_to_search(session, add_search(session)) == 24


def test_hours_to_search_covers_the_gap_since_the_last_scrape(session, monkeypatch):
    run(session, FakeLLM(), [scraped("1")], monkeypatch)
    search = add_search(session)
    assert hours_to_search(session, search) == 1  # just scraped; minimum lookback

    job = session.scalars(select(Job)).one()
    job.scraped_at = utcnow() - timedelta(hours=5, minutes=30)
    session.commit()
    assert hours_to_search(session, search) == 6  # rounded up, no gap

    # A different search's jobs don't count.
    assert hours_to_search(session, add_search(session, "something else")) == 24


def test_no_configured_searches_scrapes_nothing(session, monkeypatch):
    def boom(search, hours_old):
        raise AssertionError("no source should be searched")

    monkeypatch.setattr(pipeline_module, "JOB_SOURCES", [fake_source(boom)])
    asyncio.run(run_pipeline(session, FakeLLM()))
    assert all_jobs(session) == []
