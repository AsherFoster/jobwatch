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
    __table_args__ = (UniqueConstraint("site", "external_id", name="uq_job_site_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str]
    external_id: Mapped[str]
    # The search that found this job; null once that search is deleted.
    search_id: Mapped[int | None] = mapped_column(ForeignKey("user_searches.id"))
    title: Mapped[str]
    company: Mapped[str]
    location: Mapped[str]
    url: Mapped[str]
    description: Mapped[str]
    raw: Mapped[str]  # full scraped record as JSON
    posted_at: Mapped[datetime | None]
    scraped_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Set once a notification that includes this job has been sent, so a job is
    # never announced twice — even if changed criteria make it match again later.
    notified_at: Mapped[datetime | None]

    # Every verdict ever produced for this job, oldest first.
    all_assessments: Mapped[list[Assessment]] = relationship(
        back_populates="job", order_by="Assessment.created_at"
    )
    # The current verdict (may predate the latest criteria/model if this job
    # hasn't been reevaluated since they last changed).
    active_assessment: Mapped[Assessment | None] = relationship(
        primaryjoin=lambda: and_(Job.id == Assessment.job_id, Assessment.invalidated_at.is_(None)),
        viewonly=True,
        uselist=False,
    )
    # The user's rating/bookmark/applied state, if they've touched this job.
    user_state: Mapped[UserJobState | None] = relationship(back_populates="job")
    search: Mapped[UserSearch | None] = relationship()

    def latest_assessment(self) -> Assessment | None:
        return self.all_assessments[-1] if self.all_assessments else None


class UserJobState(Base):
    """The user's own take on a job: mutable current values, unlike the
    append-only assessment history. Single-user for now — gains a user_id
    (and a (user_id, job_id) unique) if multiple users arrive."""

    __tablename__ = "user_job_state"
    __table_args__ = (UniqueConstraint("job_id", name="uq_user_job_state_job_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    rating: Mapped[int | None]  # 1-5 stars; null = unrated
    bookmarked_at: Mapped[datetime | None]
    applied_at: Mapped[datetime | None]

    job: Mapped[Job] = relationship(back_populates="user_state")


class CompanyDetails(Base):
    """One row per company name, generated when the first job for that
    company is stored."""

    __tablename__ = "company_details"
    __table_args__ = (UniqueConstraint("name", name="uq_company_details_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    logo: Mapped[str | None]  # URL, when the job source provides one
    description: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class UserSearch(Base):
    """A saved job-board search the worker runs every cycle, and the parameters
    handed to each job source. Single-user for now — gains a user_id if
    multiple users arrive."""

    __tablename__ = "user_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_term: Mapped[str]
    location: Mapped[str]


class Setting(Base):
    """Key/value store for settings edited at runtime, e.g. the criteria text."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    score: Mapped[int]  # 1-5 stars (0 = response was unparseable)
    reasoning: Mapped[str]
    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Set when a newer assessment (reevaluation, or a criteria/model change)
    # supersedes this one. Invalidated rows are kept as history — never deleted
    # — but only the row with invalidated_at IS NULL is "the" current verdict.
    invalidated_at: Mapped[datetime | None]

    job: Mapped[Job] = relationship(back_populates="all_assessments")

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
