from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.job_sources.base import JobSource
from jobwatch.models import CompanyDetails, Job, UserSearch, utcnow
from jobwatch.pipeline.sync_jobs import hours_to_search, store_new_jobs, sync_jobs


def add_company(session: Session, name: str = "Acme") -> None:
    """Pre-seeding the company keeps ensure_company_details away from Gemini."""
    session.add(CompanyDetails(name=name, description="A company"))
    session.commit()


def stored_external_ids(session: Session) -> list[str]:
    return sorted(session.scalars(select(Job.external_id)).all())


@pytest.mark.asyncio
async def test_store_new_jobs_persists_the_scrape(session, search, scraped):
    add_company(session)
    item = scraped("abc123")

    assert await store_new_jobs(session, search, [item]) == 1
    session.commit()

    job = session.scalars(select(Job)).one()
    assert job.site == item.site
    assert job.external_id == item.external_id
    assert job.search_id == search.id
    assert job.title == item.title
    assert job.company == item.company
    assert job.url == item.url
    assert job.description == item.description
    assert job.raw == item.raw
    assert job.scraped_at is not None


@pytest.mark.asyncio
async def test_store_new_jobs_skips_jobs_already_seen(session, search, scraped):
    add_company(session)
    assert await store_new_jobs(session, search, [scraped("1"), scraped("2")]) == 2
    session.commit()

    # "2" was stored last round; only "3" is new.
    assert await store_new_jobs(session, search, [scraped("2"), scraped("3")]) == 1
    session.commit()
    assert stored_external_ids(session) == ["1", "2", "3"]


def test_hours_to_search_defaults_when_search_has_never_found_jobs(session, search):
    assert hours_to_search(session, search) == 24


def test_hours_to_search_covers_the_gap_since_the_last_scrape(session, search, add_job, user):
    add_job("1", scraped_at=utcnow() - timedelta(hours=5, minutes=30))
    assert hours_to_search(session, search) == 6  # rounded up

    # Another search's jobs don't count.
    other = UserSearch(search_term="other", location="Denmark", user_id=user.id)
    session.add(other)
    session.commit()
    assert hours_to_search(session, other) == 24


@pytest.mark.asyncio
async def test_sync_jobs_stores_from_working_sources_despite_failing_ones(
    session, search, scraped, monkeypatch
):
    add_company(session)

    def broken(search: UserSearch, hours_old: int):
        raise RuntimeError("scrape failed")

    def working(search: UserSearch, hours_old: int):
        yield scraped("1")
        yield scraped("2")

    monkeypatch.setattr(
        "jobwatch.pipeline.sync_jobs.JOB_SOURCES",
        [
            JobSource(id="broken", name="Broken", search_function=broken),
            JobSource(id="working", name="Working", search_function=working),
        ],
    )

    await sync_jobs(session)
    assert stored_external_ids(session) == ["1", "2"]
