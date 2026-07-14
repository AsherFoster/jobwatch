"""Criteria text lives on User rows, edited via the web UI at /settings.

The worker pipeline is still effectively single-user: it assesses against the
first user's criteria.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.models import User


def first_user(session: Session) -> User | None:
    return session.scalars(select(User).order_by(User.id)).first()


def get_criteria_text(session: Session) -> str:
    """Return the first user's criteria text ("" if there are no users)."""
    user = first_user(session)
    return user.criteria_text if user else ""


def set_criteria_text(session: Session, text: str, user: User | None = None) -> None:
    """Set criteria on the given user, defaulting to the first user — created
    if there are none yet, so a fresh install can save criteria right away."""
    if user is None:
        user = first_user(session)
    if user is None:
        user = User(name="Default")
        session.add(user)
    user.criteria_text = text
    session.commit()
