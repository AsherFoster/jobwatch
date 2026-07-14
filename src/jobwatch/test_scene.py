"""Declarative test-data builders.

Each method inserts one real row with sensible defaults (or, for
`scraped_job`, builds the plain value a job source would yield) and returns
it. Dependencies you don't pass in are built for you, so `Scene().job()`
alone is enough to get a fully wired Job -> UserSearch -> User chain.

"""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy.orm import Session

from jobwatch.job_sources.base import ScrapedJob
from jobwatch.models import Assessment, CompanyDetails, Job, User, UserSearch, utcnow


class Scene:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._ids = itertools.count(1)

    def user(self, *, criteria_text: str = "Positives: python. Negatives: consultancies.") -> User:
        user = User(name=f"User {next(self._ids)}", criteria_text=criteria_text)
        self.session.add(user)
        return user

    def user_search(
        self,
        *,
        user: User | None = None,
        search_term: str = "engineer",
        location: str = "Denmark",
    ) -> UserSearch:
        search = UserSearch(search_term=search_term, location=location, user=user or self.user())
        self.session.add(search)
        return search

    def job(
        self,
        *,
        title: str | None = None,
        search: UserSearch | None = None,
        external_id: str | None = None,
    ) -> Job:
        external_id = external_id or str(next(self._ids))
        job = Job(
            site="linkedin",
            external_id=external_id,
            search=search or self.user_search(),
            title=title or f"Job {external_id}",
            company="Acme",
            location="Copenhagen",
            url=f"https://example.com/{external_id}",
            description="Python things",
            raw="{}",
        )
        self.session.add(job)
        return job

    def assessment(
        self, *, job: Job | None = None, score: int = 5, notified: bool = False
    ) -> Assessment:
        job = job or self.job()
        assessment = Assessment(job=job, score=score, reasoning="good fit", model="fake")
        self.session.add(assessment)
        if notified:
            job.notified_at = utcnow()
        return assessment

    def company_details(self, *, name: str = "Acme", **fields) -> CompanyDetails:
        details = CompanyDetails(name=name, description=f"{name} makes widgets", **fields)
        self.session.add(details)
        return details

    def scraped_job(
        self, *, external_id: str | None = None, company: str = "Acme", raw: str = "{}"
    ) -> ScrapedJob:
        """Not a DB row: the payload a job source hands to the pipeline."""
        external_id = external_id or str(next(self._ids))
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


@pytest.fixture
def scene(session: Session) -> Scene:
    return Scene(session)
