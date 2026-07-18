"""Declarative test-data builders.

Each method inserts one real row with sensible defaults (or, for
`scraped_job`, builds the plain value a job source would yield) and returns
it. Dependencies you don't pass in are built for you, so `Scene().job()`
alone is enough to get a fully wired Job -> UserSearch -> User chain.

"""

from __future__ import annotations

import itertools

import awa
import pytest
from sqlalchemy import column, select, table
from sqlalchemy.orm import Session

from jobwatch.job_sources.base import ScrapedJob
from jobwatch.models import Assessment, CompanyDetails, Job, User, UserSearch, utcnow


class Scene:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._ids = itertools.count(1)
        self._default_company: CompanyDetails | None = None

    def user(self, *, criteria_text: str = "Positives: python. Negatives: consultancies.") -> User:
        user = User(name=f"User {next(self._ids)}", criteria_text=criteria_text)
        self.session.add(user)
        self.session.flush()
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
        self.session.flush()
        return search

    def job(
        self,
        *,
        title: str | None = None,
        search: UserSearch | None = None,
        external_id: str | None = None,
        company: CompanyDetails | None = None,
    ) -> Job:
        external_id = external_id or str(next(self._ids))
        if company is None:
            if self._default_company is None:
                self._default_company = self.company_details()
            company = self._default_company
        job = Job(
            site="linkedin",
            external_id=external_id,
            search=search or self.user_search(),
            title=title or f"Job {external_id}",
            company=company,
            location="Copenhagen",
            url=f"https://example.com/{external_id}",
            description="Python things",
            raw="{}",
        )
        self.session.add(job)
        self.session.flush()
        return job

    def assessment(
        self, *, job: Job | None = None, score: int = 5, notified: bool = False
    ) -> Assessment:
        job = job or self.job()
        assessment = Assessment(
            job=job,
            score=score,
            reasoning="good fit",
            model="fake",
            summary="good job",
            summary_positives="it's a job",
            summary_negatives="it's a job",
        )
        self.session.add(assessment)
        if notified:
            job.notified_at = utcnow()
        self.session.flush()
        return assessment

    def company_details(self, *, name: str = "Acme", **fields) -> CompanyDetails:
        fields.setdefault("description", f"{name} makes widgets")
        details = CompanyDetails(name=name, **fields)
        self.session.add(details)
        self.session.flush()
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


def queued_task_args(session: Session, kind: type) -> list[dict]:
    """Args of every queued awa task of the given kind.

    There's no SQLAlchemy model for awa.jobs — it's owned by awa's own
    migration, not ours — so query it with core constructs instead of the
    ORM. Reading through `session` (rather than a separate awa.Client
    connection) is what lets this see the current test's uncommitted rows.
    """
    jobs = table("jobs", column("kind"), column("args"), schema="awa")
    rows = session.execute(select(jobs.c.args).where(jobs.c.kind == awa.derive_kind(kind.__name__)))
    return [row.args for row in rows]
