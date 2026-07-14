"""Shared factories for pipeline tests. Everything writes real rows through the
per-test savepoint session from the root conftest."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from jobwatch.job_sources.base import ScrapedJob
from jobwatch.models import Job, User, UserSearch


@pytest.fixture
def user(session: Session) -> User:
    user = User(name="Test", criteria_text="Positives: python. Negatives: consultancies.")
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def search(session: Session, user: User) -> UserSearch:
    search = UserSearch(search_term="engineer", location="Denmark", user_id=user.id)
    session.add(search)
    session.commit()
    return search


@pytest.fixture
def scraped() -> Callable[..., ScrapedJob]:
    """Factory for a ScrapedJob as a source would yield it."""

    def make(external_id: str, *, company: str = "Acme", raw: str = "{}") -> ScrapedJob:
        return ScrapedJob(
            site="linkedin",
            external_id=external_id,
            title=f"Job {external_id}",
            company=company,
            location="Copenhagen",
            url=f"https://example.com/{external_id}",
            description="Python things",
            posted_at=None,
            raw=raw,
        )

    return make


@pytest.fixture
def add_job(session: Session, search: UserSearch) -> Callable[..., Job]:
    """Factory that persists a Job tied to the `search` fixture."""

    def make(external_id: str = "1", **fields) -> Job:
        job = Job(
            site="linkedin",
            external_id=external_id,
            search_id=search.id,
            title=f"Job {external_id}",
            company="Acme",
            location="Copenhagen",
            url=f"https://example.com/{external_id}",
            description="Python things",
            raw="{}",
            **fields,
        )
        session.add(job)
        session.commit()
        return job

    return make
