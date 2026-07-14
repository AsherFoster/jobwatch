"""Declarative test-data builders.

Each method inserts one real row with sensible defaults (or, for
`scraped_job`, builds the plain value a job source would yield) and returns
it. Dependencies you don't pass in are built for you, so `Scene().job()`
alone is enough to get a fully wired Job -> UserSearch -> User chain.

Plain Python, no pytest: see the `scene` fixture in conftest.py for how
tests get one bound to the per-test session.
"""

from __future__ import annotations

import itertools

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
        self.session.commit()
        return user

    def user_search(
        self,
        *,
        user: User | None = None,
        search_term: str = "engineer",
        location: str = "Denmark",
    ) -> UserSearch:
        search = UserSearch(
            search_term=search_term, location=location, user_id=(user or self.user()).id
        )
        self.session.add(search)
        self.session.commit()
        return search

    def job(
        self, *, search: UserSearch | None = None, external_id: str | None = None, **fields
    ) -> Job:
        external_id = external_id or str(next(self._ids))
        job = Job(
            site="linkedin",
            external_id=external_id,
            search_id=(search or self.user_search()).id,
            title=f"Job {external_id}",
            company="Acme",
            location="Copenhagen",
            url=f"https://example.com/{external_id}",
            description="Python things",
            raw="{}",
            **fields,
        )
        self.session.add(job)
        self.session.commit()
        return job

    def assessment(
        self, *, job: Job | None = None, score: int = 5, notified: bool = False
    ) -> Assessment:
        job = job or self.job()
        assessment = Assessment(job_id=job.id, score=score, reasoning="good fit", model="fake")
        self.session.add(assessment)
        if notified:
            job.notified_at = utcnow()
        self.session.commit()
        return assessment

    def company_details(self, *, name: str = "Acme", **fields) -> CompanyDetails:
        details = CompanyDetails(name=name, description=f"{name} makes widgets", **fields)
        self.session.add(details)
        self.session.commit()
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
