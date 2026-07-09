"""SQLAlchemy models: jobs are stored in full so they can be re-assessed later."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("site", "external_id", name="uq_job_site_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str] = mapped_column(String(32), default="linkedin")
    external_id: Mapped[str] = mapped_column(String(64))
    search_name: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    company: Mapped[str] = mapped_column(String(256), default="")
    location: Mapped[str] = mapped_column(String(256), default="")
    url: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[str] = mapped_column(Text, default="{}")  # full scraped record as JSON
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Set once a notification that includes this job has been sent, so a job is
    # never announced twice — even if changed criteria make it match again later.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="Assessment.created_at"
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
    criteria_fingerprint: Mapped[str] = mapped_column(String(16))
    matched: Mapped[bool] = mapped_column()
    score: Mapped[int] = mapped_column(default=0)  # 0-10
    reasoning: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[Job] = relationship(back_populates="assessments")
