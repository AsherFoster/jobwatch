from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.job_sources.base import JobSource
from jobwatch.models import Job, UserSearch, utcnow
from jobwatch.pipeline.sync_jobs import hours_to_search, store_new_jobs, sync_jobs
from jobwatch.test_scene import Scene


def stored_external_ids(session: Session) -> list[str]:
    return sorted(session.scalars(select(Job.external_id)).all())


@pytest.mark.asyncio
async def test_store_new_jobs_persists_the_scrape(session, scene: Scene):
    scene.company_details()  # keeps ensure_company_details away from Gemini
    search = scene.user_search()
    item = scene.scraped_job(external_id="abc123")

    assert await store_new_jobs(session, search, [item]) == 1

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
async def test_store_new_jobs_skips_jobs_already_seen(session, scene: Scene):
    scene.company_details()
    search = scene.user_search()
    scraped = [scene.scraped_job(external_id="1"), scene.scraped_job(external_id="2")]
    assert await store_new_jobs(session, search, scraped) == 2

    # "2" was stored last round; only "3" is new.
    scraped = [scene.scraped_job(external_id="2"), scene.scraped_job(external_id="3")]
    assert await store_new_jobs(session, search, scraped) == 1
    assert stored_external_ids(session) == ["1", "2", "3"]


def test_hours_to_search_defaults_when_search_has_never_found_jobs(session, scene: Scene):
    assert hours_to_search(session, scene.user_search()) == 24


def test_hours_to_search_covers_the_gap_since_the_last_scrape(session, scene: Scene):
    search = scene.user_search()
    job = scene.job(search=search)
    job.scraped_at = utcnow() - timedelta(hours=5, minutes=30)
    session.flush()

    assert hours_to_search(session, search) == 6  # rounded up

    # Another search's jobs don't count.
    other = scene.user_search(user=search.user)
    assert hours_to_search(session, other) == 24


@pytest.mark.asyncio
async def test_sync_jobs_stores_from_working_sources_despite_failing_ones(
    session, scene: Scene, monkeypatch
):
    scene.company_details()
    scene.user_search()

    def broken(search: UserSearch, hours_old: int):
        raise RuntimeError("scrape failed")

    def working(search: UserSearch, hours_old: int):
        yield scene.scraped_job(external_id="1")
        yield scene.scraped_job(external_id="2")

    monkeypatch.setattr(
        "jobwatch.pipeline.sync_jobs.JOB_SOURCES",
        [
            JobSource(id="broken", name="Broken", search_function=broken),
            JobSource(id="working", name="Working", search_function=working),
        ],
    )

    await sync_jobs(session)
    assert stored_external_ids(session) == ["1", "2"]
