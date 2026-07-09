"""SQLAlchemy models: jobs are stored in full so they can be re-assessed later."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {
        str: Text,
        datetime: DateTime(timezone=True),
    }


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("site", "external_id", name="uq_job_site_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str]
    external_id: Mapped[str]
    search_name: Mapped[str]
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

    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="job", order_by="Assessment.created_at"
    )

    def latest_assessment(self) -> Assessment | None:
        return self.assessments[-1] if self.assessments else None

    def active_assessment(self) -> Assessment | None:
        """The current verdict for this job (may be from an older criteria
        fingerprint if it hasn't been reevaluated since the criteria changed)."""
        return next((a for a in self.assessments if a.invalidated_at is None), None)


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
    criteria_fingerprint: Mapped[str]
    matched: Mapped[bool]
    score: Mapped[int]  # 0-10
    reasoning: Mapped[str]
    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Set when a newer assessment (reevaluation, or a criteria/model change)
    # supersedes this one. Invalidated rows are kept as history — never deleted
    # — but only the row with invalidated_at IS NULL is "the" current verdict.
    invalidated_at: Mapped[datetime | None] = mapped_column(default=None)

    job: Mapped[Job] = relationship(back_populates="assessments")

    __table_args__ = (
        # At most one *active* verdict per job at a time; past verdicts stay
        # around invalidated instead of being deleted or blocking a new row.
        Index(
            "uq_assessment_job_active",
            "job_id",
            unique=True,
            sqlite_where=text("invalidated_at IS NULL"),
        ),
        Index("ix_assessments_fingerprint", "criteria_fingerprint"),
    )
