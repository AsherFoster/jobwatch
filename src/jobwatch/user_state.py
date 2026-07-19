"""Setters for the user's per-job state: rating, bookmark, applied.

Each takes the desired end state rather than toggling, so repeated calls
(e.g. a double-clicked bookmark button) are idempotent. Committing is the
caller's job.
"""

from __future__ import annotations

from jobwatch.models import Job, UserJobState, utcnow
from jobwatch.typing import unwrap


def _state(job: Job) -> UserJobState:
    """The job's user-state row, created on first touch."""
    if job.user_state is None:
        job.user_state = UserJobState()
    return unwrap(job.user_state)


def set_job_rating(job: Job, rating: int | None) -> None:
    """Set the 1-5 star rating; None clears it."""
    _state(job).rating = rating


def set_job_bookmarked(job: Job, bookmarked: bool) -> None:
    state = _state(job)
    if not bookmarked:
        state.bookmarked_at = None
    elif state.bookmarked_at is None:
        state.bookmarked_at = utcnow()


def set_job_applied(job: Job, applied: bool) -> None:
    state = _state(job)
    if not applied:
        state.applied_at = None
    elif state.applied_at is None:
        state.applied_at = utcnow()
