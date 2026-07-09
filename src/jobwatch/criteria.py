"""The criteria text lives in the DB so the web UI can edit it.

config.toml's [criteria] section only seeds the value on first run; after that
the settings table is the source of truth.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from jobwatch.config import Config
from jobwatch.models import Setting

CRITERIA_KEY = "criteria_text"


def criteria_fingerprint(text: str, model: str) -> str:
    """Identifies a (criteria, model) combination so jobs can be re-assessed
    when either changes."""
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()[:16]


def get_criteria_text(session: Session, seed: str = "") -> str:
    """Return the stored criteria text, seeding it on first use."""
    setting = session.get(Setting, CRITERIA_KEY)
    if setting is None:
        setting = Setting(key=CRITERIA_KEY, value=seed)
        session.add(setting)
        session.commit()
    return setting.value


def set_criteria_text(session: Session, text: str) -> None:
    setting = session.get(Setting, CRITERIA_KEY)
    if setting is None:
        session.add(Setting(key=CRITERIA_KEY, value=text))
    else:
        setting.value = text
    session.commit()


def current_criteria(session: Session, config: Config) -> tuple[str, str]:
    """(text, fingerprint) for the stored criteria, seeded from config."""
    text = get_criteria_text(session, seed=config.criteria.text if config.criteria else "")
    return text, criteria_fingerprint(text, config.llm.model)
