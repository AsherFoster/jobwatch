"""SQLAlchemy models: jobs are stored in full so they can be re-assessed later."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, and_, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


# Assessments scoring at least this many stars count as a match.
MATCHED_MIN_SCORE = 4


class Base(DeclarativeBase):
    type_annotation_map = {
        str: Text,
        datetime: DateTime(timezone=True),
    }


class User(Base):
    """A person using jobwatch, with their own assessment criteria."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    criteria_text: Mapped[str] = mapped_column(default="")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("site", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    search_id: Mapped[int] = mapped_column(ForeignKey("user_searches.id"))
    search: Mapped[UserSearch] = relationship()
    """The search that found this job"""

    site: Mapped[str]
    external_id: Mapped[str]
    title: Mapped[str]

    company_id: Mapped[int] = mapped_column(ForeignKey("company_details.id"))
    company: Mapped[CompanyDetails] = relationship()

    location: Mapped[str]
    url: Mapped[str]
    description: Mapped[str]
    raw: Mapped[str]
    """Full scraped record as JSON."""
    posted_at: Mapped[datetime | None]
    scraped_at: Mapped[datetime] = mapped_column(default=utcnow)
    notified_at: Mapped[datetime | None]
    """Set once a notification that includes this job has been sent, so a job is
    never announced twice — even if changed criteria make it match again later."""

    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="job", order_by="Assessment.created_at"
    )
    """Every verdict ever produced for this job, oldest first."""
    active_assessment: Mapped[Assessment | None] = relationship(
        primaryjoin=lambda: and_(Job.id == Assessment.job_id, Assessment.invalidated_at.is_(None)),
        viewonly=True,
        uselist=False,
    )
    """The current verdict (may predate the latest criteria/model if this job
    hasn't been reevaluated since they last changed)."""

    past_assessments: Mapped[list[Assessment]] = relationship(
        primaryjoin=lambda: and_(
            Job.id == Assessment.job_id, Assessment.invalidated_at.isnot(None)
        ),
        viewonly=True,
    )
    user_state: Mapped[UserJobState | None] = relationship(back_populates="job")
    """The user's rating/bookmark/applied state, if they've touched this job."""


class UserJobState(Base):
    """The user's own take on a job: mutable current values, unlike the
    append-only assessment history. Single-user for now — gains a user_id
    (and a (user_id, job_id) unique) if multiple users arrive."""

    __tablename__ = "user_job_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    rating: Mapped[int | None]
    """1-5 stars; null = unrated."""
    bookmarked_at: Mapped[datetime | None]
    applied_at: Mapped[datetime | None]

    job: Mapped[Job] = relationship(back_populates="user_state")


class CompanyDetails(Base):
    """One row per company name, generated when the first job for that
    company is stored."""

    __tablename__ = "company_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    linkedin_slug: Mapped[str | None] = mapped_column(unique=True)
    """Slug from the company's LinkedIn URL (e.g. "too-good-to-go"), the most
    reliable identifier we get from scraped jobs."""
    logo: Mapped[str | None]
    """URL, when the job source provides one."""
    description: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    generated_at: Mapped[datetime | None]
    """Set once `load_company_details` has filled in the description; null
    while the row is a blank placeholder waiting for that task to run."""


class UserSearch(Base):
    """A saved job-board search the worker runs every cycle, and the parameters
    handed to each job source."""

    __tablename__ = "user_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_term: Mapped[str]
    location: Mapped[str]
    deleted_at: Mapped[datetime | None]
    """Set when the user removes this search. Kept around (not deleted) so
    jobs it already found keep a valid search_id."""

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped[User] = relationship()


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    score: Mapped[int]
    """1-5 stars (0 = response was unparseable)."""

    reasoning: Mapped[str]
    summary: Mapped[str]
    summary_positives: Mapped[str]
    summary_negatives: Mapped[str]

    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    invalidated_at: Mapped[datetime | None]
    """Set when a newer assessment (reevaluation, or a criteria/model change)
    supersedes this one. Invalidated rows are kept as history — never deleted
    — but only the row with invalidated_at IS NULL is "the" current verdict."""

    job: Mapped[Job] = relationship(back_populates="assessments")

    @property
    def matched(self) -> bool:
        return self.score >= MATCHED_MIN_SCORE

    __table_args__ = (
        # At most one *active* verdict per job at a time; past verdicts stay
        # around invalidated instead of being deleted or blocking a new row.
        Index(
            "uq_assessment_job_active",
            "job_id",
            unique=True,
            postgresql_where=text("invalidated_at IS NULL"),
        ),
    )
