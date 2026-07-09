"""SQLAlchemy models: jobs are stored in full so they can be re-assessed later."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint
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


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("job_id", "criteria_fingerprint", name="uq_assessment_job_criteria"),
        Index("ix_assessments_fingerprint", "criteria_fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    criteria_fingerprint: Mapped[str]
    matched: Mapped[bool]
    score: Mapped[int]  # 0-10
    reasoning: Mapped[str]
    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    job: Mapped[Job] = relationship(back_populates="assessments")
