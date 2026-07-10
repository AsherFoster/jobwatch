"""The criteria text lives in the DB, edited via the web UI at /settings.

It's blank until configured there — there's no config.toml seed for it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from jobwatch.models import Setting

CRITERIA_KEY = "criteria_text"


def get_criteria_text(session: Session) -> str:
    """Return the stored criteria text ("" if never configured)."""
    setting = session.get(Setting, CRITERIA_KEY)
    return setting.value if setting else ""


def set_criteria_text(session: Session, text: str) -> None:
    setting = session.get(Setting, CRITERIA_KEY)
    if setting is None:
        session.add(Setting(key=CRITERIA_KEY, value=text))
    else:
        setting.value = text
    session.commit()
