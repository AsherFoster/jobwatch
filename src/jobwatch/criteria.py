"""Criteria text lives on User rows, edited via the web UI at /settings.

The worker pipeline is still effectively single-user: it assesses against the
first user's criteria.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.models import User


def get_criteria_text(session: Session) -> str:
    """Return the first user's criteria text ("" if there are no users)."""
    user = session.scalars(select(User).order_by(User.id)).first()
    return user.criteria_text if user else ""
