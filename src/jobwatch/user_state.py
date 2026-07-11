"""Setters for the user's per-job state: rating, bookmark, applied.

Each takes the desired end state rather than toggling, so repeated calls
(e.g. a double-clicked bookmark button) are idempotent.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from jobwatch.models import Job, UserJobState, utcnow


def _state(job: Job) -> UserJobState:
    """The job's user-state row, created on first touch."""
    if job.user_state is None:
        job.user_state = UserJobState(job_id=job.id)
    return job.user_state


def set_job_rating(session: Session, job: Job, rating: int | None) -> None:
    """Set the 1-5 star rating; None clears it."""
    _state(job).rating = rating
    session.commit()


def set_job_bookmarked(session: Session, job: Job, bookmarked: bool) -> None:
    state = _state(job)
    if not bookmarked:
        state.bookmarked_at = None
    elif state.bookmarked_at is None:
        state.bookmarked_at = utcnow()
    session.commit()


def set_job_applied(session: Session, job: Job, applied: bool) -> None:
    state = _state(job)
    if not applied:
        state.applied_at = None
    elif state.applied_at is None:
        state.applied_at = utcnow()
    session.commit()
