"""Searches live in the DB as a settings row holding a JSON list.

There's no UI for them yet: migration 0003 seeds the row from a pre-existing
config.toml, otherwise set it with `set_searches` (or SQL by hand).
"""

from __future__ import annotations

from pydantic import BaseModel, TypeAdapter
from sqlalchemy.orm import Session

from jobwatch.models import Setting

SEARCHES_KEY = "searches"


class SearchConfig(BaseModel):
    name: str
    search_term: str
    location: str
    results_wanted: int = 100
    hours_old: int = 24


_searches_json = TypeAdapter(list[SearchConfig])


def get_searches(session: Session) -> list[SearchConfig]:
    """Return the configured searches ([] if never configured)."""
    setting = session.get(Setting, SEARCHES_KEY)
    return _searches_json.validate_json(setting.value) if setting else []


def set_searches(session: Session, searches: list[SearchConfig]) -> None:
    value = _searches_json.dump_json(searches).decode()
    setting = session.get(Setting, SEARCHES_KEY)
    if setting is None:
        session.add(Setting(key=SEARCHES_KEY, value=value))
    else:
        setting.value = value
    session.commit()
